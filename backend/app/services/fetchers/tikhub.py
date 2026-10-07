"""TikHub 第三方接口客户端：X/Twitter、微信公众号、Bilibili 数据获取。

统一入口 https://api.tikhub.io，认证: Authorization: Bearer <token>
（用户控制台 https://user.tikhub.io 创建）。

Twitter 线上返回扁平化结构（author/text 顶层键），与文档示例的 GraphQL
结构不同，两种均已适配；X 长文在扁平结构下直接提供纯文本全文。
Token 未配置或请求失败时抛出异常，由调用方处理。
"""

from __future__ import annotations

import html
import re
import math
from datetime import datetime, timezone
from typing import Any

import httpx

from app.services.fetchers.social import URL_PATTERN, _normalize_external_url, extract_x_tweet_id
from app.services.fetchers.twitter_article_rich import _deep_get, _find_image_url

TIKHUB_API_BASE = "https://api.tikhub.io"  # 出厂默认端点，可在后台「TikHub 数据服务」页覆盖
_api_base = TIKHUB_API_BASE  # 进程内当前生效端点；resolve token 时由配置刷新

TWEET_DETAIL_PATH = "/api/v1/twitter/web/fetch_tweet_detail"
WECHAT_ARTICLE_PATH = "/api/v1/wechat_mp/v2/fetch_article_detail_h5"
WECHAT_ARTICLE_DETAIL_PATH = "/api/v1/wechat_mp/v2/fetch_article_detail"
BILIBILI_PARTS_PATH = "/api/v1/bilibili/web/fetch_video_parts"
BILIBILI_BV_TO_AID_PATH = "/api/v1/bilibili/web/bv_to_aid"
BILIBILI_PLAYER_PATH = "/api/v1/bilibili/web/fetch_one_video_v2"
TIKHUB_USER_INFO_PATH = "/api/v1/tikhub/user/get_user_info"
TIKHUB_DAILY_USAGE_PATH = "/api/v1/tikhub/user/get_user_daily_usage"

BILIBILI_BVID_PATTERN = re.compile(r"BV[0-9A-Za-z]{10}")

_VISIBILITY_WRAPPER_TYPES = {"TweetWithVisibility", "TweetWithVisibilityResults"}


class TikHubError(RuntimeError):
    """TikHub 接口调用失败（网络、鉴权、余额、数据缺失等）。"""

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


class TikHubNotConfiguredError(TikHubError):
    """未配置 TikHub API Token，调用方应直接回退其他数据源。"""


def resolve_tikhub_base(config: Any = None) -> str:
    """从配置对象刷新并返回 API 端点（留空回官方地址）。

    进程内单端点策略：所有 TikHub 调用共享 _api_base，
    resolve_tikhub_token 顺带刷新，任务链路无需逐层传端点。
    """
    global _api_base
    base = ""
    if isinstance(config, dict):
        base = str(config.get("tikhubApiBase") or "").strip()
    elif config is not None:
        base = str(getattr(config, "tikhubApiBase", "") or "").strip()
    _api_base = base.rstrip("/") or TIKHUB_API_BASE
    return _api_base


def resolve_tikhub_token(config: Any = None) -> str:
    """从配置对象读取 TikHub API Token（配置来自 SQLite app_settings 表）。"""
    resolve_tikhub_base(config)
    token = ""
    if isinstance(config, dict):
        token = str(config.get("tikhubApiKey") or "").strip()
    elif config is not None:
        token = str(getattr(config, "tikhubApiKey", "") or "").strip()
    if not token:
        raise TikHubNotConfiguredError("未配置 TikHub API Token，请在管理后台的 TikHub 页面设置。")
    return token


def _tikhub_request(path: str, token: str, params: dict | None = None, json_body: Any = None, unwrap_data: bool = True, method: str | None = None) -> dict:
    """调用 TikHub 接口；unwrap_data=False 用于无 data 包装的接口（如用户信息）。"""
    request_url = f"{_api_base}{path}"
    try:
        response = httpx.request(
            method or ("POST" if json_body is not None else "GET"),
            request_url,
            params=params,
            json=json_body,
            headers={"Authorization": f"Bearer {token}"},
            timeout=45,
        )
    except httpx.TimeoutException as exc:
        raise TikHubError("TikHub 请求超时，请稍后重试。", 504) from exc
    except httpx.HTTPError as exc:
        raise TikHubError("TikHub 请求失败：网络连接异常，请稍后重试。") from exc

    status = response.status_code
    if status == 401:
        raise TikHubError("TikHub Token 无效、缺失或未激活 (401)。", 401)
    if status == 403:
        raise TikHubError("TikHub Key 无权访问此接口 (403)，请检查端点权限。", 403)
    if status == 402:
        raise TikHubError("TikHub 账户余额不足 (402)，请前往 user.tikhub.io 充值。", 402)
    if status == 404:
        raise TikHubError(f"TikHub 未找到数据 (404): {request_url}")
    if status == 429:
        raise TikHubError("TikHub 请求过于频繁 (429)，请稍后重试。", 429)
    if status != 200:
        raise TikHubError(f"TikHub 接口异常 (HTTP {status}): {request_url}")

    try:
        payload = response.json()
    except ValueError as exc:
        raise TikHubError("TikHub 返回了非 JSON 数据。") from exc

    if not isinstance(payload, dict):
        raise TikHubError("TikHub 返回的数据格式错误。")

    # Some upstream errors arrive as HTTP 200. Never echo credentials in messages.
    if payload.get("detail"):
        detail = payload["detail"]
        message = (detail.get('message_zh') or detail.get('message') or '请求被拒绝') if isinstance(detail, dict) else str(detail)
        raise TikHubError(f"TikHub 接口错误: {message.replace(token, '[已隐藏]')[:250]}")

    code = payload.get("code")
    if code not in (200, 0, None, '200', '0'):
        message = str(payload.get("message_zh") or payload.get("message") or "请求失败").replace(token, '[已隐藏]')[:250]
        error_status = int(code) if str(code) in ('401', '402', '403', '429') else 502
        raise TikHubError(f"TikHub 接口返回错误 (code={code}): {message}", error_status)

    if not unwrap_data:
        return payload if isinstance(payload, dict) else {}

    data = payload.get("data")
    if not isinstance(data, dict):
        raise TikHubError("TikHub 返回的数据为空。")
    return data


def fetch_tweet_detail(tweet_id: str, token: str) -> dict:
    return _tikhub_request(TWEET_DETAIL_PATH, token, params={"tweet_id": tweet_id})


def _is_flat_tweet_data(data: dict) -> bool:
    """TikHub 当前将推文数据扁平化：author/text 为顶层键。"""
    return isinstance(data.get("author"), dict) and isinstance(data.get("text"), str)


def _unwrap_tweet_result(data: dict) -> dict | None:
    """从 GraphQL 风格响应 data 中取出推文 result（旧版结构兼容）。"""
    result = None
    for key in ("tweet_result_by_rest_id", "tweetResult"):
        container = data.get(key)
        if isinstance(container, dict) and isinstance(container.get("result"), dict):
            result = container["result"]
            break
    if result is None and isinstance(data.get("result"), dict):
        result = data["result"]
    if not isinstance(result, dict):
        return None

    if result.get("__typename") in _VISIBILITY_WRAPPER_TYPES and isinstance(result.get("tweet"), dict):
        result = result["tweet"]

    retweeted = _deep_get(result, "legacy", "retweeted_status_result", "result")
    if isinstance(retweeted, dict):
        if retweeted.get("__typename") in _VISIBILITY_WRAPPER_TYPES and isinstance(retweeted.get("tweet"), dict):
            retweeted = retweeted["tweet"]
        if retweeted.get("legacy") or retweeted.get("article"):
            result = retweeted

    return result if result.get("legacy") or result.get("article") else None


def _collect_media_urls(legacy: dict) -> list[str]:
    media_urls: list[str] = []
    media_items = legacy.get("extended_entities", {}).get("media") or legacy.get("entities", {}).get("media") or []
    for media in media_items:
        if not isinstance(media, dict):
            continue
        url = media.get("media_url_https") or media.get("media_url") or ""
        if url:
            media_urls.append(url)
    return media_urls


def _pick_best_video_url(item: dict) -> str:
    """从 video variants 里选最高码率的 mp4 直链（X 的 GIF 本质也是无音频 mp4）。"""
    variants = item.get("variants") if isinstance(item.get("variants"), list) else []
    mp4s = [
        v for v in variants
        if isinstance(v, dict) and str(v.get("content_type", "")).lower() == "video/mp4" and v.get("url")
    ]
    if not mp4s:
        return ""
    return str(max(mp4s, key=lambda v: v.get("bitrate") or 0)["url"])


def _extract_flat_media_urls(media: Any) -> list[str]:
    """从扁平结构的 media 字段容错提取图片/封面 URL。

    线上实测结构为 {"photo": [...], "video": [...]}；旧容错键（all/photos/videos）保留。
    """
    if isinstance(media, dict):
        items = (
            media.get("photo")
            or media.get("photos")
            or media.get("all")
            or []
        )
        if not items:
            items = media.get("video") or media.get("videos") or media.get("gif") or media.get("animated_gif") or []
    else:
        items = media if isinstance(media, list) else []
    media_urls: list[str] = []
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                url = (
                    item.get("media_url_https")
                    or item.get("media_url")
                    or item.get("url")
                    or item.get("preview_image_url")
                    or item.get("thumbnail_url")
                    or ""
                )
                if url:
                    media_urls.append(url)
            elif isinstance(item, str) and item.startswith("http"):
                media_urls.append(item)
    return media_urls


def _extract_flat_media_items(media: Any) -> list[dict]:
    """提取带类型的媒体列表：[{type: photo|gif|video, url, poster}]，供前端区分渲染。"""
    if not isinstance(media, dict):
        return []
    items: list[dict] = []

    def add(kind: str, url: str, poster: str = "") -> None:
        if url and url.startswith("http"):
            entry = {"type": kind, "url": url}
            if poster:
                entry["poster"] = poster
            items.append(entry)

    for photo in media.get("photo") or media.get("photos") or []:
        if isinstance(photo, dict):
            add("photo", str(photo.get("media_url_https") or photo.get("url") or ""))
    for video in media.get("video") or media.get("videos") or media.get("gif") or media.get("animated_gif") or []:
        if isinstance(video, dict):
            best = _pick_best_video_url(video)
            kind = "gif" if "gif" in str(video.get("type") or "").lower() else "video"
            add(kind, best, str(video.get("media_url_https") or ""))
    return items


def _collect_external_urls(legacy: dict, note_result: dict, tweet_text: str) -> list[str]:
    candidates: list[str] = []
    for entity in legacy.get("entities", {}).get("urls") or []:
        if isinstance(entity, dict):
            candidates.append(entity.get("expanded_url") or entity.get("url") or "")
    note_entities = note_result.get("entity_set") or note_result.get("entities") or {}
    for entity in note_entities.get("urls") or []:
        if isinstance(entity, dict):
            candidates.append(entity.get("expanded_url") or entity.get("url") or "")
    candidates.extend(URL_PATTERN.findall(tweet_text or ""))

    external_urls: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = _normalize_external_url(candidate)
        if normalized and normalized not in seen:
            external_urls.append(normalized)
            seen.add(normalized)
    return external_urls


def _normalize_avatar_url(url: str) -> str:
    if "_normal." in url:
        return url.replace("_normal.", "_400x400.")
    return url


def _build_article_text(article: dict) -> dict | None:
    """扁平结构的长文：TikHub 直接提供纯文本全文。"""
    article_text = {
        "title": str(article.get("title") or ""),
        "preview_text": str(article.get("preview_text") or ""),
        "full_text": str(article.get("full_text") or ""),
        "cover_image_url": str(article.get("cover_media") or ""),
    }
    if not (article_text["full_text"] or article_text["title"]):
        return None
    return article_text


def _build_article_preview(article: dict) -> dict | None:
    preview = article.get("preview") if isinstance(article.get("preview"), dict) else {}
    rich_result = _deep_get(article, "article_results", "result")
    if not isinstance(rich_result, dict):
        rich_result = {}
    cover = _find_image_url(preview) or _find_image_url(rich_result.get("cover_media") or {})
    article_preview = {
        "title": preview.get("title") or rich_result.get("title") or "",
        "preview_text": preview.get("excerpt") or preview.get("preview_text") or "",
        "image": cover or "",
    }
    if not any(article_preview.values()):
        return None
    return article_preview


def normalize_flat_tweet_data(data: dict) -> dict:
    """normalize TikHub 扁平化推文数据（实测的当前线上结构）。"""
    author = data.get("author") or {}
    article = data.get("article") if isinstance(data.get("article"), dict) else None

    author_name = str(author.get("name") or "未知作者")
    author_handle = str(author.get("screen_name") or "")
    avatar_url = _normalize_avatar_url(str(author.get("image") or ""))
    tweet_text = str(data.get("text") or "")
    media_urls = _extract_flat_media_urls(data.get("media"))
    media_items = _extract_flat_media_items(data.get("media"))

    article_preview = None
    if article:
        article_preview = {
            "title": str(article.get("title") or ""),
            "preview_text": str(article.get("preview_text") or ""),
            "image": str(article.get("cover_media") or ""),
        }
        if not any(article_preview.values()):
            article_preview = None

    title = f"{author_name} 的推文"
    if article_preview and article_preview.get("title"):
        title = article_preview["title"]

    cover_image_url = media_urls[0] if media_urls else ""
    if article_preview and article_preview.get("image"):
        cover_image_url = article_preview["image"]

    tweet_id = str(data.get("id") or data.get("conversation_id") or "")
    tweet_url = f"https://x.com/{author_handle}/status/{tweet_id}" if author_handle and tweet_id else ""

    external_urls: list[str] = []
    seen: set[str] = set()
    candidates: list[str] = []
    for entity in data.get("urls") or []:
        if isinstance(entity, dict):
            candidates.append(entity.get("expanded_url") or entity.get("url") or "")
    for entity in _deep_get(data, "entities", "urls") or []:
        if isinstance(entity, dict):
            candidates.append(entity.get("expanded_url") or entity.get("url") or "")
    candidates.extend(URL_PATTERN.findall(tweet_text))
    for candidate in candidates:
        normalized = _normalize_external_url(candidate)
        if normalized and normalized not in seen:
            external_urls.append(normalized)
            seen.add(normalized)

    return {
        "author_name": author_name,
        "author_handle": author_handle,
        "author_avatar_url": avatar_url,
        "tweet_text": tweet_text,
        "media_urls": media_urls,
        "media_items": media_items,
        "article_preview": article_preview,
        "title": title or "推文内容",
        "cover_image_url": cover_image_url,
        "likes": data.get("likes", 0),
        "retweets": data.get("retweets", 0),
        "replies": data.get("replies", 0),
        "created_at": data.get("created_at", ""),
        "tweet_url": tweet_url,
        "external_urls": external_urls,
    }


def normalize_tikhub_tweet_result(result: dict) -> dict:
    """把 GraphQL 风格的 TweetResultByRestId 结构转换为与 normalize_tweet_payload 同构的 payload（旧版兼容）。"""
    user_legacy = _deep_get(result, "core", "user_results", "result", "legacy") or {}
    legacy = result.get("legacy") or {}
    note_result = _deep_get(result, "note_tweet", "note_tweet_results", "result") or {}
    article = result.get("article") if isinstance(result.get("article"), dict) else {}

    author_name = user_legacy.get("name", "未知作者")
    author_handle = user_legacy.get("screen_name", "")
    avatar_url = _normalize_avatar_url(str(user_legacy.get("profile_image_url_https") or ""))

    tweet_text = str(note_result.get("text") or legacy.get("full_text") or "")
    media_urls = _collect_media_urls(legacy)
    article_preview = _build_article_preview(article) if article else None

    title = f"{author_name} 的推文"
    if article_preview and article_preview.get("title"):
        title = article_preview["title"]

    cover_image_url = media_urls[0] if media_urls else ""
    if article_preview and article_preview.get("image"):
        cover_image_url = article_preview["image"]

    tweet_id = str(result.get("rest_id") or "")
    tweet_url = f"https://x.com/{author_handle}/status/{tweet_id}" if author_handle and tweet_id else ""

    return {
        "author_name": author_name,
        "author_handle": author_handle,
        "author_avatar_url": avatar_url,
        "tweet_text": tweet_text,
        "media_urls": media_urls,
        "article_preview": article_preview,
        "title": title or "推文内容",
        "cover_image_url": cover_image_url,
        "likes": legacy.get("favorite_count", 0),
        "retweets": legacy.get("retweet_count", 0),
        "replies": legacy.get("reply_count", 0),
        "created_at": legacy.get("created_at", ""),
        "tweet_url": tweet_url,
        "external_urls": _collect_external_urls(legacy, note_result, tweet_text),
    }


def fetch_tikhub_tweet(url_or_tweet_id: str, config: Any = None) -> dict:
    """通过 TikHub 获取推文数据。

    返回:
        payload:       normalize 后的推文数据（与镜像接口的 normalize_tweet_payload 同构）
        article_result: GraphQL 结构下的 X 长文 Draft.js 数据（用于富文本渲染），或 None
        article_text:  扁平结构下的 X 长文纯文本全文，或 None
    """
    identifier = str(url_or_tweet_id or "").strip()
    tweet_id = identifier if identifier.isdigit() else (extract_x_tweet_id(identifier) or "")
    if not tweet_id.isdigit():
        raise TikHubError("无法从链接中提取推文 ID。")

    token = resolve_tikhub_token(config)
    data = fetch_tweet_detail(tweet_id, token)

    if _is_flat_tweet_data(data):
        article = data.get("article") if isinstance(data.get("article"), dict) else {}
        return {
            "payload": normalize_flat_tweet_data(data),
            "article_result": None,
            "article_text": _build_article_text(article) if article else None,
        }

    result = _unwrap_tweet_result(data)
    if result is None:
        raise TikHubError("TikHub 未返回有效推文数据（推文可能已被删除或不可见）。")

    article_result = _deep_get(result, "article", "article_results", "result")
    if not isinstance(article_result, dict) or not article_result.get("content_state"):
        article_result = None

    return {
        "payload": normalize_tikhub_tweet_result(result),
        "article_result": article_result,
        "article_text": None,
    }


# ---------------------------------------------------------------------------
# 微信公众号文章
# ---------------------------------------------------------------------------

def fetch_wechat_article(url: str, config: Any = None) -> dict:
    """通过 TikHub 接口获取公众号文章（绕过微信安全验证）。

    优先 H5 接口（普通图文返回官方正文 HTML）。H5 端拿不到正文时（新版
    沉浸式页面 / 图片消息等）回落非 H5 接口：图片消息（item_show_type=8）
    正文是长图，按微信原生输出形态构造 js_content HTML（摘要段落 +
    data-src/data-w/data-ratio 图片），由前端复刻视图按官方 CSS 渲染；
    非 H5 只给纯文本时同样构造段落 HTML。

    返回 {title, author, account_name, digest, html_content, content_text,
          cover_image_url, publish_time, original_url, content_type}
    """
    token = resolve_tikhub_token(config)
    article_url = str(url or "").strip()
    data = _tikhub_request(
        WECHAT_ARTICLE_PATH,
        token,
        json_body={"url": article_url, "raw": False},
    )
    content = data.get("content") if isinstance(data.get("content"), dict) else {}
    html_content, content_type = _wechat_content_html(content)
    if not html_content:
        fallback_content, fallback_url = _fetch_wechat_article_fallback(article_url, token)
        html_content, content_type = _wechat_content_html(fallback_content)
        if html_content:
            content = fallback_content
            if fallback_url:
                data["url"] = fallback_url
    if not html_content:
        raise TikHubError("TikHub 未返回公众号文章内容（文章可能已被删除）。")

    return {
        "title": str(content.get("title") or "").strip() or "未知文章标题",
        "author": str(content.get("author") or content.get("nick_name") or "").strip(),
        "account_name": str(content.get("nick_name") or "").strip(),
        "digest": str(content.get("desc") or "").strip(),
        "html_content": html_content,
        "content_text": str(content.get("content_text") or content.get("desc") or ""),
        "cover_image_url": str(content.get("cdn_url") or "").strip(),
        "publish_time": str(content.get("create_time") or "").strip(),
        "original_url": str(data.get("url") or url or "").strip(),
        "content_type": content_type,
    }


_WECHAT_HTML_HINT_RE = re.compile(r"<(p|div|img|section|span|br|blockquote|h[1-6])\b", re.IGNORECASE)


def _wechat_content_html(content: dict) -> tuple[str, str]:
    """把接口的 content 字典转为 (正文 HTML, 内容类型)。

    content_noencode 通常是官方正文 HTML；图片消息/纯文本场景它是纯文字
    （此时摘要即全文），配合长图列表构造微信同构 HTML。类型供调用方决定
    摘要提取方式：image/text 直接用纯文本，rich_text 走 trafilatura。
    """
    if not isinstance(content, dict):
        return "", ""
    raw = str(content.get("content_noencode") or "").strip()
    if _WECHAT_HTML_HINT_RE.search(raw):
        html_content = re.sub(r"data-src\s*=", "src=", raw, flags=re.IGNORECASE)
        html_content = re.sub(r"visibility:\s*hidden;?", "visibility: visible;", html_content, flags=re.IGNORECASE)
        return html_content, "rich_text"
    if content.get("picture_page_info_list"):
        return _build_wechat_image_message_html(content), "image"
    if raw:
        return _build_wechat_text_message_html(raw), "text"
    return "", ""


def _fetch_wechat_article_fallback(url: str, token: str) -> tuple[dict, str]:
    """H5 接口正文为空时回落非 H5 接口。返回 (content, 最终文章链接)。"""
    try:
        data = _tikhub_request(
            WECHAT_ARTICLE_DETAIL_PATH,
            token,
            json_body={"url": url, "raw": False},
        )
    except TikHubError:
        return {}, ""
    content = data.get("content") if isinstance(data.get("content"), dict) else {}
    final_url = url
    link = str(content.get("link") or "").strip()
    if link:
        # TikHub 返回的 link 带 HTML 转义（&amp;），还原为可直接访问的长链
        final_url = html.unescape(link)
    return content, final_url


def _wechat_paragraphs_html(text: str) -> str:
    """纯文本按换行拆为微信正文段落（H5 端摘要里的字面 \\x0a 一并归一）。"""
    return "".join(
        f"<p>{html.escape(part.strip())}</p>"
        for part in str(text or "").replace("\\x0a", "\n").split("\n")
        if part.strip()
    )


def _wrap_wechat_content(body: str) -> str:
    return (
        '<div class="rich_media_content js_underline_content defaultNoSetting" id="js_content">'
        f"{body}</div>"
    )


def _build_wechat_text_message_html(text: str) -> str:
    return _wrap_wechat_content(_wechat_paragraphs_html(text))


def _build_wechat_image_message_html(content: dict) -> str:
    """按微信图片消息的原生输出形态构造正文 HTML。

    微信对图片消息（item_show_type=8）输出的正文同样是 #js_content 容器：
    摘要文字为 <p> 段落，图片为 <img data-src data-w data-ratio>（高/宽比），
    与普通图文共用了前端复刻视图的懒加载转正和定宽逻辑。
    """
    paragraphs = _wechat_paragraphs_html(content.get("desc") or content.get("content_text") or "")
    images = []
    for pic in content.get("picture_page_info_list") or []:
        if not isinstance(pic, dict):
            continue
        img_url = html.unescape(str(pic.get("cdn_url") or "")).strip()
        if not img_url:
            continue
        attrs = f'data-src="{img_url}"'
        try:
            width = float(pic.get("width") or 0)
            height = float(pic.get("height") or 0)
        except (TypeError, ValueError):
            width = height = 0
        if width > 0:
            attrs += f' data-w="{int(width)}"'
            if height > 0:
                attrs += f' data-ratio="{height / width:.6f}"'
        images.append(f'<img class="rich_pages wxw-img" {attrs}>')
    return _wrap_wechat_content(f"{paragraphs}{''.join(images)}")


# ---------------------------------------------------------------------------
# Bilibili 视频
# ---------------------------------------------------------------------------

def _extract_bilibili_bvid(url: str) -> str:
    match = BILIBILI_BVID_PATTERN.search(str(url or ""))
    if not match:
        raise TikHubError("无法从链接中提取 BVID（BV 号）。")
    return match.group(0)


def _resolve_b23_short_url(url: str) -> str:
    """b23.tv 短链解析为最终地址（免费直连重定向，不消耗 TikHub 额度）。"""
    if "b23.tv" not in url:
        return url
    try:
        response = httpx.get(url, follow_redirects=True, timeout=15, verify=False)
        return str(response.url)
    except httpx.HTTPError as exc:
        raise TikHubError(f"b23.tv 短链解析失败: {exc}") from exc


def _download_bilibili_subtitle(subtitles: list, token: str) -> str:
    """优先中文字幕，下载字幕 JSON 拼接为纯文本文稿。"""
    if not subtitles:
        return ""
    target = next((s for s in subtitles if s.get("lan") == "zh-CN"), subtitles[0])
    sub_url = str(target.get("subtitle_url") or "")
    if not sub_url:
        return ""
    if sub_url.startswith("//"):
        sub_url = "https:" + sub_url
    try:
        response = httpx.get(
            sub_url,
            headers={"User-Agent": "Mozilla/5.0", "Authorization": f"Bearer {token}"},
            timeout=20,
            verify=False,
        )
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        return ""
    body = payload.get("body") if isinstance(payload, dict) else None
    if not isinstance(body, list):
        return ""
    return " ".join(str(item.get("content") or "") for item in body).strip()


def fetch_bilibili_video(url: str, config: Any = None) -> dict:
    """通过 TikHub 获取 Bilibili 视频信息与字幕文稿。

    TikHub 的 view 类元数据接口（fetch_one_video/v3/detail/app）当前均不可用，
    稳定组合为：fetch_video_parts（分P/cid）→ bv_to_aid → fetch_one_video_v2
    （player/v2 结构，含字幕列表）。视频主标题缺失时回退分P标题。

    返回与原官方 API 抓取同构的 video payload。
    """
    token = resolve_tikhub_token(config)
    resolved_url = _resolve_b23_short_url(str(url or "").strip())
    bvid = _extract_bilibili_bvid(resolved_url)

    parts_data = _tikhub_request(BILIBILI_PARTS_PATH, token, params={"bv_id": bvid})
    inner = parts_data.get("data") if isinstance(parts_data.get("data"), dict) else {}
    parts = inner.get("data") if isinstance(inner.get("data"), list) else parts_data.get("data")
    if not isinstance(parts, list) or not parts:
        raise TikHubError("TikHub 未返回视频分P数据（视频可能不存在或已下架）。")

    chapter_lines = []
    first_cid = None
    for page in parts:
        if not isinstance(page, dict):
            continue
        part = str(page.get("part") or "").strip()
        duration = page.get("duration")
        cid = page.get("cid")
        if first_cid is None and cid:
            first_cid = cid
        if not part:
            continue
        if isinstance(duration, int) and duration > 0:
            minutes, seconds = divmod(duration, 60)
            chapter_lines.append(f"- P{page.get('page', len(chapter_lines) + 1)} [{minutes:02d}:{seconds:02d}] {part}")
        else:
            chapter_lines.append(f"- P{page.get('page', len(chapter_lines) + 1)} {part}")

    transcript_text = ""
    aid = ""
    if first_cid:
        try:
            aid_data = _tikhub_request(BILIBILI_BV_TO_AID_PATH, token, params={"bv_id": bvid})
            aid = str(aid_data.get("aid") or aid_data.get("data", {}).get("aid") or "")
        except TikHubError:
            aid = ""
        if aid:
            # 字幕是可选增强：player 接口抽风（如间歇 400）时跳过，不拖垮整个抓取任务
            try:
                player_data = _tikhub_request(BILIBILI_PLAYER_PATH, token, params={"a_id": aid, "c_id": str(first_cid)})
                player_inner = player_data.get("data") if isinstance(player_data.get("data"), dict) else {}
                subtitles = _deep_get(player_inner, "subtitle", "subtitles") or []
                transcript_text = _download_bilibili_subtitle(subtitles, token)
            except TikHubError:
                transcript_text = ""

    title = str((parts[0] or {}).get("part") or "").strip() or bvid
    return {
        "title": title,
        "description": "",
        "uploader": "",
        "transcript_text": transcript_text,
        "cover_image_url": "",
        "bvid": bvid,
        "cid": str(first_cid or ""),
        "chapter_info": "\n".join(chapter_lines),
    }


# ---------------------------------------------------------------------------
# TikHub 账户信息（TikHub-User-API）
# ---------------------------------------------------------------------------

def _number(value: Any, integer: bool = False) -> float | int | None:
    try:
        number = float(value)
        if not math.isfinite(number):
            return None
        return int(number) if integer else number
    except (ValueError, TypeError, OverflowError):
        return None


def _boolean(value: Any) -> bool:
    return value is True or value == 1 or str(value).lower() == "true"


def _account_summary(payload: dict) -> dict:
    # Both top-level user responses and standard data envelopes exist upstream.
    payload = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    user = payload.get("user_data")
    key = payload.get("api_key_data")
    if not isinstance(user, dict) or not isinstance(key, dict) or "api_key_status" not in key or "is_active" not in user:
        raise TikHubError("TikHub 账户信息不完整，无法验证 Key。")
    scopes = key.get("api_key_scopes")
    scopes = [str(scope) for scope in scopes] if isinstance(scopes, list) else []
    return {
        "api_key": {
            "name": str(key.get("api_key_name") or ""),
            "created_at": key.get("created_at"),
            "expires_at": key.get("expires_at"),
            "status": _number(key.get("api_key_status"), integer=True),
            "scopes": scopes,
            "scopes_count": len(scopes),
        },
        "user": {
            "email": str(user.get("email") or ""),
            "balance": _number(user.get("balance")),
            "free_credit": _number(user.get("free_credit")),
            "is_active": _boolean(user.get("is_active")),
            "email_verified": _boolean(user.get("email_verified")),
            "account_disabled": _boolean(user.get("account_disabled")),
        },
    }


def verify_tikhub_token(token: str) -> dict:
    summary = _account_summary(_tikhub_request(TIKHUB_USER_INFO_PATH, token, unwrap_data=False))
    if summary["api_key"]["status"] != 1 or not summary["user"]["is_active"] or summary["user"]["account_disabled"]:
        raise TikHubError("TikHub Key 或账户未激活、已禁用。", 401)
    expiry = summary["api_key"]["expires_at"]
    if expiry:
        try:
            expires = datetime.fromisoformat(str(expiry).replace("Z", "+00:00"))
            if expires.replace(tzinfo=expires.tzinfo or timezone.utc) <= datetime.now(timezone.utc):
                raise TikHubError("TikHub Key 已过期，请更换 Key。", 401)
        except ValueError:
            raise TikHubError("TikHub Key 有效期格式异常，无法验证。")
    return summary


def fetch_tikhub_account(config: Any = None) -> dict:
    token = resolve_tikhub_token(config)
    summary = _account_summary(_tikhub_request(TIKHUB_USER_INFO_PATH, token, unwrap_data=False))
    usage = None
    warnings = []
    try:
        raw = _tikhub_request(TIKHUB_DAILY_USAGE_PATH, token, unwrap_data=False)
        daily = raw.get("data", raw)
        if not isinstance(daily, dict) or not any(k in daily for k in ("usage", "total_request_per_day", "date")):
            raise TikHubError("TikHub 每日用量数据格式错误。")
        counts = daily.get("uri_counts")
        counts = counts if isinstance(counts, dict) else {}
        usage = {
            "date": str(daily.get("date") or ""),
            "usage": _number(daily.get("usage")),
            "total_request_per_day": _number(daily.get("total_request_per_day"), integer=True),
            "paid_request_per_day": _number(daily.get("paid_request_per_day"), integer=True),
            "uri_counts": {str(k): _number(v, integer=True) for k, v in counts.items() if _number(v, integer=True) is not None},
        }
    except TikHubError as exc:
        warnings.append(f"每日用量暂不可用：{exc}")
    return {**summary, "daily_usage": usage, "warnings": warnings}
