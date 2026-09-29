"""X/Twitter 链接解析工具。

数据获取统一走 TikHub（tikhub.py），本模块只保留 URL/ID 解析与外链过滤。
"""

import re
from urllib.parse import urlsplit


X_ARTICLE_URL_PATTERN = re.compile(
    r"https?://(?:www\.)?(?:x\.com|twitter\.com)/i/article/(?P<id>\d+)",
    re.IGNORECASE,
)
X_TWEET_URL_PATTERN = re.compile(
    r"https?://(?:www\.)?(?:x\.com|twitter\.com)/[^/]+/(?:status|statuses)/(?P<id>\d+)",
    re.IGNORECASE,
)

TWEET_HOSTS = {
    "x.com",
    "www.x.com",
    "twitter.com",
    "www.twitter.com",
    "mobile.twitter.com",
    "mobile.x.com",
}
# 站内短链域名：不属于外部文章，需要从外链中排除
SHORT_URL_HOSTS = TWEET_HOSTS | {"t.co", "pic.twitter.com", "t.cn"}
URL_PATTERN = re.compile(r"https?://[^\s<>\"]+", re.IGNORECASE)


def extract_x_article_id(text: str) -> str | None:
    if not text:
        return None

    match = X_ARTICLE_URL_PATTERN.search(text.strip())
    return match.group("id") if match else None


def extract_x_tweet_id(text: str) -> str | None:
    if not text:
        return None

    match = X_TWEET_URL_PATTERN.search(text.strip())
    return match.group("id") if match else None


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
