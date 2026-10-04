import asyncio
import os
from datetime import datetime, timedelta, timezone

import httpx
import yt_dlp

from app.config import settings
from app.services.fetchers.tikhub import TikHubNotConfiguredError, fetch_bilibili_video

BILIBILI_VIEW_URL = "https://api.bilibili.com/x/web-interface/view"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
# B 站图床拦截外部 Referer（前端 <img> 必 403），封面必须下载进本地 /media 再引用
CN_TZ = timezone(timedelta(hours=8))


async def fetch_video_content(url: str, config, update_step):
    if "bilibili.com" in url or "b23.tv" in url:
        return await _fetch_bilibili_via_tikhub(url, config, update_step)
    return await fetch_generic_video(url, update_step)


def _fetch_bilibili_official_view(bvid: str) -> dict:
    """官方 view 接口（匿名、免费、不耗 TikHub 额度）：封面、简介、UP主、发布时间。"""
    response = httpx.get(
        BILIBILI_VIEW_URL,
        params={"bvid": bvid},
        headers={"User-Agent": UA},
        timeout=15,
        verify=False,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != 0:
        raise RuntimeError(f"官方接口返回 code={payload.get('code')}")
    return payload.get("data") or {}


def _localize_bilibili_cover(pic_url: str, bvid: str) -> str:
    """封面下载到本地 /media，返回站内相对路径；下载失败返回空串（不用热链，会 403）。"""
    if not pic_url:
        return ""
    target_dir = settings.MEDIA_DIR.rstrip("/") + "/bilibili"
    os.makedirs(target_dir, exist_ok=True)
    local_path = f"{target_dir}/{bvid}.jpg"
    if not (os.path.exists(local_path) and os.path.getsize(local_path) > 1024):
        response = httpx.get(
            pic_url.replace("http://", "https://"),
            headers={"User-Agent": UA},
            timeout=20,
            verify=False,
            follow_redirects=True,
        )
        response.raise_for_status()
        with open(local_path, "wb") as fh:
            fh.write(response.content)
    return f"/media/bilibili/{bvid}.jpg"


async def _fetch_bilibili_via_tikhub(url: str, config, update_step):
    update_step("正在通过 TikHub 接口解析 Bilibili 视频信息...")
    try:
        payload = await asyncio.to_thread(fetch_bilibili_video, url, config)
    except TikHubNotConfiguredError as exc:
        raise RuntimeError(
            "未配置 TikHub API Token，无法抓取 Bilibili 视频。请在管理后台 TikHub 抓取页填写 Token。"
        ) from exc
    try:
        update_step("正在通过官方接口补齐封面与元数据...")
        view = await asyncio.to_thread(_fetch_bilibili_official_view, payload.get("bvid") or "")
        if str(view.get("title") or "").strip():
            payload["title"] = str(view["title"]).strip()
        if str(view.get("desc") or "").strip():
            payload["description"] = str(view["desc"]).strip()
        if str((view.get("owner") or {}).get("name") or "").strip():
            payload["uploader"] = str(view["owner"]["name"]).strip()
        if isinstance(view.get("pic"), str) and view["pic"]:
            payload["cover_image_url"] = await asyncio.to_thread(
                _localize_bilibili_cover, view["pic"], payload.get("bvid") or "cover"
            )
        if isinstance(view.get("pubdate"), int):
            payload["publish_time"] = datetime.fromtimestamp(view["pubdate"], tz=CN_TZ).strftime("%Y-%m-%d")
    except Exception:
        update_step("官方元数据不可用，继续使用 TikHub 解析结果。")
    update_step(f"解析成功: {payload['title']}。正在整理视频信息...")
    return payload


async def fetch_generic_video(url: str, update_step):
    update_step("正在通过 yt-dlp 解析视频信息...")
    ydl_opts = {
        "quiet": True,
        "simulate": True,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        },
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return {
        "title": info.get("title", "未知标题"),
        "description": info.get("description", ""),
        "uploader": info.get("uploader", "未知作者"),
        "transcript_text": "",
        "cover_image_url": info.get("thumbnail", ""),
        "bvid": "",
        "chapter_info": "",
    }
