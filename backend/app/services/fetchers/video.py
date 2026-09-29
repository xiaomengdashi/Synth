import asyncio

import yt_dlp

from app.services.fetchers.tikhub import TikHubNotConfiguredError, fetch_bilibili_video


async def fetch_video_content(url: str, config, update_step):
    if "bilibili.com" in url or "b23.tv" in url:
        return await _fetch_bilibili_via_tikhub(url, config, update_step)
    return await fetch_generic_video(url, update_step)


async def _fetch_bilibili_via_tikhub(url: str, config, update_step):
    update_step("正在通过 TikHub 接口解析 Bilibili 视频信息...")
    try:
        payload = await asyncio.to_thread(fetch_bilibili_video, url, config)
    except TikHubNotConfiguredError as exc:
        raise RuntimeError(
            "未配置 TikHub API Token，无法抓取 Bilibili 视频。请在管理后台 TikHub 抓取页填写 Token。"
        ) from exc
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
