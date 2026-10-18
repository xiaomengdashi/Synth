"""X metadata via the yt-dlp subprocess approach used by content-downloader.

Adapted from content_downloader/adapters/x/fetcher.py (MIT, copyright 2026
zinan92; license in content_downloader_LICENSE.txt). Kept inside this app so
production deployments do not depend on a developer's ~/content-downloader.
Only metadata is requested: article imports do not download full videos.
"""
from __future__ import annotations

import asyncio
import datetime
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

from app.services.fetchers.social import TWEET_HOSTS, extract_x_article_id, extract_x_tweet_id
from app.services.fetchers.tikhub import normalize_flat_tweet_data

FETCH_TIMEOUT_SECONDS = 60


def _http_url(value) -> str:
    text = str(value or "")
    return text if urlsplit(text).scheme in {"http", "https"} else ""


def normalize_metadata(info: dict, url: str) -> dict:
    """Map real tweet metadata, never a no-media placeholder or linked video."""
    tweet_id = extract_x_tweet_id(url)
    if not isinstance(info, dict) or str(info.get("display_id") or info.get("id")) != tweet_id:
        raise RuntimeError("Content Downloader 返回的内容与原推文不一致")
    if info.get("extractor_key") != "Twitter":
        raise RuntimeError("Content Downloader 返回了外链内容，未获取到原推文")
    text = str(info.get("description") or "").strip()
    expanded_url = _http_url(info.get("url")) if info.get("_type") in {"url", "url_transparent"} else ""
    # A title/thumbnail does not establish that the full article was retrieved.
    without_short_links = re.sub(r"https?://t\.co/\S+", "", text).strip()
    ambiguous_short_link = ("https://t.co/" in text and not expanded_url
                            and not info.get("formats") and not info.get("entries"))
    if (not text or extract_x_article_id(text) or extract_x_article_id(expanded_url)
            or without_short_links.endswith(("…", "...")) or ambiguous_short_link
            or (not without_short_links and not expanded_url)):
        raise RuntimeError("Content Downloader 未返回完整推文正文，需尝试其他获取方式")

    entries = info.get("entries") or [info]
    photos, videos = [], []
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        thumbnails = entry.get("thumbnails") or []
        poster = _http_url(entry.get("thumbnail")) or next(
            (_http_url(item.get("url")) for item in reversed(thumbnails) if isinstance(item, dict) and _http_url(item.get("url"))), "",
        )
        formats = [item for item in entry.get("formats") or [] if isinstance(item, dict)]
        # Raw Twitter variants precede yt-dlp's ext/vcodec normalization.
        formats = [item for item in formats if item.get("vcodec") != "none" and _http_url(item.get("url"))
                   and (item.get("ext") == "mp4" or urlsplit(item["url"]).path.lower().endswith(".mp4"))]
        if formats:
            best = max(formats, key=lambda item: item.get("tbr") or 0)
            video_url = _http_url(best["url"])
            if video_url not in seen:
                seen.add(video_url)
                videos.append({"variants": [{"url": video_url, "content_type": "video/mp4"}],
                               "media_url_https": poster})
        elif poster and poster not in seen:
            seen.add(poster)
            photos.append({"url": poster})

    created_at = ""
    if info.get("timestamp") is not None:
        try:
            created_at = datetime.datetime.fromtimestamp(float(info["timestamp"]), datetime.UTC).isoformat()
        except (ValueError, TypeError, OverflowError, OSError):
            pass
    payload = normalize_flat_tweet_data({
        "id": tweet_id, "text": text,
        "author": {"name": info.get("uploader") or info.get("uploader_id") or "未知作者",
                   "screen_name": info.get("uploader_id") or ""},
        "media": {"photo": photos, "video": videos},
        "likes": info.get("like_count") or 0, "retweets": info.get("repost_count") or 0,
        "replies": info.get("comment_count") or 0, "created_at": created_at,
        "urls": [{"expanded_url": expanded_url}] if expanded_url else [],
    })
    payload["tweet_url"] = url
    return {"payload": payload, "article_result": None, "article_text": None}


async def fetch_content_downloader_tweet(url: str) -> dict:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in TWEET_HOSTS or not extract_x_tweet_id(url):
        raise RuntimeError("Content Downloader 仅支持 X / Twitter 宿主推文链接")
    # Use the application's installed dependency; no PATH or sibling repo dependency.
    process = await asyncio.create_subprocess_exec(
        sys.executable, str(Path(__file__).with_name("content_downloader_runner.py")), "--", url,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, _stderr = await asyncio.wait_for(process.communicate(), timeout=FETCH_TIMEOUT_SECONDS)
    except (TimeoutError, asyncio.CancelledError) as exc:
        if process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
        await process.communicate()
        if isinstance(exc, asyncio.CancelledError):
            raise
        raise RuntimeError("Content Downloader 获取超时") from exc
    if process.returncode != 0:
        # Do not expose raw subprocess errors (proxy credentials, huge upstream output).
        raise RuntimeError("Content Downloader 获取失败；请检查 yt-dlp 安装、网络或原推文可见性")
    try:
        info = json.loads(stdout)
    except (ValueError, TypeError) as exc:
        raise RuntimeError("Content Downloader 未返回有效 JSON 正文") from exc
    return normalize_metadata(info, url)
