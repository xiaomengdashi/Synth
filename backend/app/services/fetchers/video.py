import re

import httpx
import yt_dlp


def build_bilibili_cookies(config) -> dict:
    cookies = {}
    if getattr(config, "biliSessdata", None):
        cookies["SESSDATA"] = config.biliSessdata
    if getattr(config, "biliJct", None):
        cookies["bili_jct"] = config.biliJct
    if getattr(config, "biliBuvid3", None):
        cookies["buvid3"] = config.biliBuvid3
    return cookies


async def fetch_video_content(url: str, config, update_step):
    if "bilibili.com" in url or "b23.tv" in url:
        return await fetch_bilibili_video(url, config, update_step)
    return await fetch_generic_video(url, update_step)


async def fetch_bilibili_video(url: str, config, update_step):
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }
    cookies = build_bilibili_cookies(config)
    async with httpx.AsyncClient(headers=headers, cookies=cookies, verify=False, follow_redirects=True, timeout=30.0) as http_client:
        bvid_match = re.search(r"BV[0-9A-Za-z]{10}", url)
        if not bvid_match:
            raise RuntimeError("无法从链接中提取 BVID")
        bvid = bvid_match.group(0)

        api_url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
        res = await http_client.get(api_url)
        data = res.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Bilibili API 错误: {data.get('message')}")

        video_data = data["data"]
        title = video_data.get("title", "未知标题")
        description = video_data.get("desc", "")
        uploader = video_data.get("owner", {}).get("name", "未知作者")
        pages = video_data.get("pages") or []
        chapter_lines = []
        for page in pages:
            part = (page.get("part") or "").strip()
            duration = page.get("duration")
            if not part:
                continue
            if isinstance(duration, int) and duration > 0:
                minutes, seconds = divmod(duration, 60)
                chapter_lines.append(f"- P{page.get('page', len(chapter_lines) + 1)} [{minutes:02d}:{seconds:02d}] {part}")
            else:
                chapter_lines.append(f"- P{page.get('page', len(chapter_lines) + 1)} {part}")
        chapter_info = "\n".join(chapter_lines)

        transcript_text = ""
        cid = video_data.get("cid")
        if cid:
            update_step("正在尝试获取视频文稿/字幕...")
            subtitle_api_url = f"https://api.bilibili.com/x/player/v2?bvid={bvid}&cid={cid}"
            sub_res = await http_client.get(subtitle_api_url)
            sub_data = sub_res.json()
            if sub_data.get("code") == 0:
                subtitles = sub_data.get("data", {}).get("subtitle", {}).get("subtitles", [])
                if subtitles:
                    target_sub = next((s for s in subtitles if s.get("lan") == "zh-CN"), subtitles[0])
                    sub_url = target_sub.get("subtitle_url")
                    if sub_url:
                        if sub_url.startswith("//"):
                            sub_url = "https:" + sub_url
                        sub_content_res = await http_client.get(sub_url)
                        sub_content_data = sub_content_res.json()
                        if "body" in sub_content_data:
                            transcript_text = " ".join(item.get("content", "") for item in sub_content_data["body"])

        return {
            "title": title,
            "description": description,
            "uploader": uploader,
            "transcript_text": transcript_text,
            "cover_image_url": video_data.get("pic", ""),
            "bvid": bvid,
            "chapter_info": chapter_info,
        }


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
