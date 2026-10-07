"""Bilibili 音频转写链路：TikHub playurl 拿直链 → 下载音频 → MiniMax 云端转写。

B 站 CC 字幕覆盖率极低（热门视频几乎全无），音频转写是文稿的可靠来源。
直链指向 B 站 CDN（upos-*.bilivideo.com 等），个别镜像直连会被重置，
因此对 baseUrl + backupUrl 逐个尝试；全部失败且设置了 BILIBILI_PROXY
环境变量时走该代理重试。MiniMax 单次转写上限 500s，超长按 480s 切片拼接。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable

import httpx

from app.services.fetchers.tikhub import (
    BILIBILI_PARTS_PATH,
    TikHubNotConfiguredError,
    _extract_bilibili_bvid,
    _resolve_b23_short_url,
    _tikhub_request,
    resolve_tikhub_token,
)

BILIBILI_PLAYURL_PATH = "/api/v1/bilibili/web/fetch_video_playurl"
MINIMAX_STT_PATH = "/v1/speech_to_text"
DEFAULT_MINIMAX_BASES = ("https://api.minimax.cn", "https://api-bj.minimaxi.com")
CHUNK_SECONDS = 480  # MiniMax 单次上限 500s，切片留余量避免边界 400
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
REFERER = "https://www.bilibili.com/"


class TranscribeError(RuntimeError):
    """音频下载或转写失败（调用方应降级为基础保存，不阻断任务）。"""


def resolve_minimax_key(config: Any = None) -> str:
    token = ""
    if isinstance(config, dict):
        token = str(config.get("minimaxApiKey") or "").strip()
    elif config is not None:
        token = str(getattr(config, "minimaxApiKey", "") or "").strip()
    if not token:
        raise TranscribeError("未配置 MiniMax 转写 Key，请在管理后台「模型设置」页填写。")
    return token


def _resolve_minimax_bases(config: Any = None) -> tuple[str, ...]:
    """MiniMax 端点：后台填一个自定义地址（自建中转/代理场景）；
    留空用官方双域名依次尝试容灾。误填逗号分隔时取第一个。"""
    raw = ""
    if isinstance(config, dict):
        raw = str(config.get("minimaxApiBase") or "").strip()
    elif config is not None:
        raw = str(getattr(config, "minimaxApiBase", "") or "").strip()
    first = raw.split(",")[0].strip().rstrip("/")
    return (first,) if first.startswith("http") else DEFAULT_MINIMAX_BASES


def _resolve_bilibili_proxies(config: Any = None) -> list[str | None]:
    """音频下载代理：后台配置优先，BILIBILI_PROXY 环境变量兜底；直连始终首先尝试。"""
    proxies: list[str | None] = [None]
    configured = ""
    if isinstance(config, dict):
        configured = str(config.get("bilibiliProxy") or "").strip()
    elif config is not None:
        configured = str(getattr(config, "bilibiliProxy", "") or "").strip()
    for candidate in (configured, os.environ.get("BILIBILI_PROXY", "").strip()):
        if candidate and candidate not in proxies:
            proxies.append(candidate)
    return proxies


def _fetch_audio_candidates(bvid: str, cid: str, token: str) -> list[str]:
    """按码率从高到低收集音频直链（每档取 baseUrl + backupUrl）。"""
    payload = _tikhub_request(BILIBILI_PLAYURL_PATH, token, params={"bv_id": bvid, "cid": str(cid)})
    data = payload.get("data", payload)
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        data = data["data"]  # playurl 是双层信封
    dash = (data or {}).get("dash") or {}
    flac = dash.get("flac") if isinstance(dash.get("flac"), dict) else None
    entries = ([flac] if flac and (flac.get("baseUrl") or flac.get("base_url")) else []) + list(dash.get("audio") or [])
    urls: list[str] = []
    for entry in sorted(entries, key=lambda item: item.get("bandwidth") or 0, reverse=True):
        for key in ("baseUrl", "base_url"):
            if entry.get(key):
                urls.append(str(entry[key]))
        urls.extend(str(u) for u in (entry.get("backupUrl") or entry.get("backup_url") or []))
    return urls


def _download_one(url: str, dest: Path, proxy: str | None = None) -> bool:
    """单条直链下载，断点续传重试 3 轮；支持 200/206 两种响应。"""
    headers = {"User-Agent": UA, "Referer": REFERER}
    client_kwargs: dict = {"timeout": httpx.Timeout(30.0, read=120.0)}
    if proxy:
        client_kwargs["proxy"] = proxy
    try:
        with httpx.Client(verify=False, follow_redirects=True, **client_kwargs) as client:
            for _ in range(3):
                offset = dest.stat().st_size if dest.exists() else 0
                attempt_headers = dict(headers)
                if offset:
                    attempt_headers["Range"] = f"bytes={offset}-"
                try:
                    with client.stream("GET", url, headers=attempt_headers) as resp:
                        if resp.status_code not in (200, 206):
                            return False
                        append = resp.status_code == 206 and offset > 0
                        with dest.open("ab" if append else "wb") as fh:
                            for chunk in resp.iter_bytes(1 << 16):
                                fh.write(chunk)
                    return True
                except httpx.HTTPError:
                    continue
    except httpx.HTTPError:
        return False
    return False


def _download_audio(urls: list[str], dest: Path, update_step: Callable[[str], None], proxies: list[str | None] | None = None) -> None:
    if proxies is None:
        proxies = [None]
    total = len(urls)
    for proxy in proxies:
        label = "代理" if proxy else "直连"
        for index, url in enumerate(urls, 1):
            update_step(f"正在下载音频（{label}镜像 {index}/{total}）...")
            if _download_one(url, dest, proxy) and dest.stat().st_size > 1024:
                return
    raise TranscribeError(
        "所有音频直链下载失败。可在管理后台「TikHub 数据服务 → 接口与网络」配置 B 站下载代理（如 http://127.0.0.1:7890）后重试。"
    )


def _require_ffmpeg() -> None:
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        raise TranscribeError("服务器缺少 ffmpeg，无法进行音频转写。")


def _audio_to_chunks(source: Path, workdir: Path) -> list[Path]:
    """统一转成 mp3 单声道 16k，再按 480s 切片（≤480s 时只有一片）。"""
    _require_ffmpeg()
    mp3 = workdir / "audio.mp3"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(source), "-vn", "-ac", "1", "-ar", "16000", "-b:a", "64k", str(mp3)],
        check=True,
    )
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp3), "-f", "segment", "-segment_time", str(CHUNK_SECONDS),
         "-reset_timestamps", "1", str(workdir / "chunk_%03d.mp3")],
        check=True,
    )
    return sorted(workdir.glob("chunk_*.mp3"))


def _minimax_stt(mp3: Path, api_key: str, bases: tuple[str, ...] = DEFAULT_MINIMAX_BASES) -> str:
    last_error = ""
    for base in bases:
        try:
            response = httpx.post(
                base + MINIMAX_STT_PATH,
                data={"model": "asr-1.0", "response_format": "json"},
                files={"file": (mp3.name, mp3.read_bytes())},
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=300,
            )
        except httpx.HTTPError as exc:
            last_error = f"{base}: {exc}"
            continue
        if response.status_code == 401:
            raise TranscribeError("MiniMax 转写 Key 鉴权失败，请检查是否为 Token Plan 订阅 Key（sk-cp- 开头）。")
        if response.status_code != 200:
            detail = " ".join(response.text.split())[:200]
            raise TranscribeError(f"MiniMax 转写接口返回 HTTP {response.status_code}：{detail}")
        result = response.json()
        base_resp = result.get("base_resp") or {}
        if base_resp.get("status_code", 0) != 0:
            raise TranscribeError(f"MiniMax 转写失败 {base_resp.get('status_code')}：{base_resp.get('status_msg')}")
        return str(result.get("text") or "")
    raise TranscribeError(f"MiniMax 转写端点均不可达：{last_error}")


def fetch_bilibili_transcript_via_asr(
    url: str,
    config: Any = None,
    update_step: Callable[[str], None] | None = None,
    bvid: str = "",
    cid: str = "",
) -> dict:
    """字幕拿不到时的兜底：下载音频 → MiniMax 云端转写。

    bvid/cid 可由调用方传入（抓取阶段已拿过），缺省时自行解析（会多消耗 TikHub 额度）。
    """
    step = update_step or (lambda message: None)
    try:
        token = resolve_tikhub_token(config)
    except TikHubNotConfiguredError as exc:
        raise TranscribeError(str(exc)) from exc
    api_key = resolve_minimax_key(config)

    if not bvid:
        resolved_url = _resolve_b23_short_url(str(url or "").strip())
        bvid = _extract_bilibili_bvid(resolved_url)

    if not cid:
        step("正在获取视频分P信息...")
        parts_data = _tikhub_request(BILIBILI_PARTS_PATH, token, params={"bv_id": bvid})
        inner = parts_data.get("data") if isinstance(parts_data.get("data"), dict) else {}
        parts = inner.get("data") if isinstance(inner.get("data"), list) else parts_data.get("data")
        if not isinstance(parts, list) or not parts:
            raise TranscribeError("TikHub 未返回视频分P数据（视频可能不存在或已下架）。")
        cid = str(next((p.get("cid") for p in parts if isinstance(p, dict) and p.get("cid")), "") or "")
    if not cid:
        raise TranscribeError("未能获取视频 cid，无法下载音频。")

    step("正在获取音频直链...")
    urls = _fetch_audio_candidates(bvid, cid, token)
    if not urls:
        raise TranscribeError("TikHub playurl 未返回音频流。")

    workdir = Path(tempfile.mkdtemp(prefix="bilibili_asr_"))
    try:
        raw = workdir / "audio.m4s"
        _download_audio(urls, raw, step, _resolve_bilibili_proxies(config))
        size_mb = raw.stat().st_size / 1024 / 1024
        step(f"音频下载完成（{size_mb:.1f}MB），正在切片...")
        chunks = _audio_to_chunks(raw, workdir)
        bases = _resolve_minimax_bases(config)
        texts: list[str] = []
        for index, chunk in enumerate(chunks, 1):
            step(f"MiniMax 云端转写中（第 {index}/{len(chunks)} 片）...")
            texts.append(_minimax_stt(chunk, api_key, bases))
        transcript = "\n".join(part for part in texts if part).strip()
        if not transcript:
            raise TranscribeError("转写结果为空（音频可能没有有效人声）。")
        return {"transcript_text": transcript, "bvid": bvid, "cid": str(cid), "engine": "minimax-asr"}
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
