import json
import re
import subprocess
from urllib.parse import urlsplit


PRIMARY_TWEET_MIRROR = "api.vxtwitter.com"
TWEET_MIRRORS = (PRIMARY_TWEET_MIRROR, "api.fxtwitter.com", "api.twittpr.com")
SUPPORTED_TWEET_HOSTS = {
    "x.com",
    "www.x.com",
    "twitter.com",
    "www.twitter.com",
    "mobile.twitter.com",
    "mobile.x.com",
    *TWEET_MIRRORS,
}
SHORT_URL_HOSTS = {
    "t.co",
    "pic.twitter.com",
    "x.com",
    "www.x.com",
    "mobile.x.com",
    "twitter.com",
    "www.twitter.com",
    "mobile.twitter.com",
    *TWEET_MIRRORS,
}
URL_PATTERN = re.compile(r"https?://[^\s<>\"]+", re.IGNORECASE)


def _extract_url_strings(value) -> list[str]:
    results: list[str] = []
    if isinstance(value, str):
        results.append(value)
    elif isinstance(value, list):
        for item in value:
            results.extend(_extract_url_strings(item))
    elif isinstance(value, dict):
        for key in (
            "expanded_url",
            "expandedUrl",
            "unwound_url",
            "unwoundUrl",
            "article_url",
            "articleUrl",
            "url",
            "href",
            "link",
        ):
            if key in value:
                results.extend(_extract_url_strings(value[key]))
    return results


def _normalize_external_url(value: str) -> str | None:
    candidate = str(value or "").strip().rstrip(".,;:!?)]}）】»”")
    parsed = urlsplit(candidate)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not host or host in SHORT_URL_HOSTS:
        return None
    if parsed.username or parsed.password or parsed.port not in {None, 80, 443}:
        return None
    if parsed.path.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp", ".mp4", ".mov", ".mp3", ".m4a", ".pdf")):
        return None
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}" + (f"?{parsed.query}" if parsed.query else "")


def extract_external_urls(tweet_data: dict) -> list[str]:
    candidates: list[str] = []
    tweet_info = tweet_data.get("tweet", {}) if isinstance(tweet_data.get("tweet"), dict) else {}
    article_preview = tweet_data.get("article") if isinstance(tweet_data.get("article"), dict) else {}

    for container in (
        tweet_data.get("entities"),
        tweet_info.get("entities"),
        tweet_data.get("urls"),
        tweet_info.get("urls"),
        tweet_data.get("url_entities"),
        tweet_info.get("url_entities"),
        article_preview,
    ):
        candidates.extend(_extract_url_strings(container))

    for text in (tweet_data.get("text"), tweet_info.get("text")):
        if isinstance(text, str):
            candidates.extend(URL_PATTERN.findall(text))

    external_urls: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = _normalize_external_url(candidate)
        if normalized and normalized not in seen:
            external_urls.append(normalized)
            seen.add(normalized)
    return external_urls


def build_tweet_api_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    host = parsed.netloc.lower()
    path = parsed.path.rstrip("/")

    if not host or not path:
        raise RuntimeError(f"无效推文链接: {url}")

    if host not in SUPPORTED_TWEET_HOSTS:
        raise RuntimeError(f"暂不支持的推文域名: {parsed.netloc}")

    return f"https://{PRIMARY_TWEET_MIRROR}{path}"


def fetch_tweet_data(url: str) -> dict:
    api_url = build_tweet_api_url(url)

    failures: list[str] = []
    for host in TWEET_MIRRORS:
        current_url = api_url.replace(PRIMARY_TWEET_MIRROR, host, 1)
        try:
            result = subprocess.run(["curl", "-s", "-k", "-L", current_url], capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                raise RuntimeError(f"{host} curl 失败: {result.stderr}")
            payload = json.loads(result.stdout)
            if "error" in payload or ("code" in payload and payload["code"] != 200):
                raise RuntimeError(f"{host} API 返回错误: {payload}")
            return payload
        except Exception as exc:
            failures.append(str(exc))

    raise RuntimeError("无法获取推文信息 (所有节点均失败): " + " | ".join(failures))


def normalize_tweet_payload(tweet_data: dict) -> dict:
    author_name = tweet_data.get("user_name", "未知作者")
    author_handle = tweet_data.get("user_screen_name", "")
    author_avatar_url = tweet_data.get("user_profile_image_url", "")
    article_preview = tweet_data.get("article") or None
    likes = tweet_data.get("likes", 0)
    retweets = tweet_data.get("retweets", 0)
    replies = tweet_data.get("replies", 0)
    created_at = tweet_data.get("date", "")
    tweet_url = tweet_data.get("tweetURL", "")

    if "tweet" in tweet_data:
        tweet_info = tweet_data["tweet"]
        author_name = tweet_info.get("author", {}).get("name", author_name)
        author_handle = tweet_info.get("author", {}).get("screen_name", author_handle)
        author_avatar_url = tweet_info.get("author", {}).get("avatar_url", author_avatar_url)
        tweet_text = tweet_info.get("text", "")
        media = tweet_info.get("media", {})
        media_urls = [m.get("url") for m in media.get("photos", [])] + [m.get("url") for m in media.get("videos", [])]
        likes = tweet_info.get("favorite_count", likes)
        retweets = tweet_info.get("retweet_count", retweets)
        replies = tweet_info.get("reply_count", replies)
        created_at = tweet_info.get("created_at", created_at)
        tweet_url = tweet_info.get("url", tweet_url)
    else:
        tweet_text = tweet_data.get("text", "")
        media_urls = tweet_data.get("mediaURLs", [])

    title = f"{author_name} 的推文"
    if article_preview:
        title = article_preview.get("title", title) or title

    cover_image_url = media_urls[0] if media_urls else ""
    if article_preview and article_preview.get("image"):
        cover_image_url = article_preview["image"]
    external_urls = extract_external_urls(tweet_data)

    return {
        "author_name": author_name,
        "author_handle": author_handle,
        "author_avatar_url": author_avatar_url,
        "tweet_text": tweet_text,
        "media_urls": [url for url in media_urls if url],
        "article_preview": article_preview,
        "title": title or "推文内容",
        "cover_image_url": cover_image_url,
        "likes": likes,
        "retweets": retweets,
        "replies": replies,
        "created_at": created_at,
        "tweet_url": tweet_url,
        "external_urls": external_urls,
    }
