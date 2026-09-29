"""TikHub 第三方接口客户端：X/Twitter 推文与长文数据获取。

接口: GET https://api.tikhub.io/api/v1/twitter/web/fetch_tweet_detail?tweet_id=<id>
认证: Authorization: Bearer <token>（用户控制台 https://user.tikhub.io 创建）

返回的 data 与 Twitter GraphQL TweetResultByRestId 同构，因此 X 长文的
Draft.js content_state 可以直接交给 twitter_article_rich 渲染。
Token 未配置或请求失败时抛出异常，由调用方回退到镜像接口 / twitter-cli。
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from app.services.fetchers.social import URL_PATTERN, _normalize_external_url
from app.services.fetchers.twitter_article_rich import _deep_get, _find_image_url
from app.services.fetchers.x_twitter_cli import extract_x_tweet_id

TIKHUB_API_BASE = "https://api.tikhub.io"
TWEET_DETAIL_PATH = "/api/v1/twitter/web/fetch_tweet_detail"

_VISIBILITY_WRAPPER_TYPES = {"TweetWithVisibility", "TweetWithVisibilityResults"}


class TikHubError(RuntimeError):
    """TikHub 接口调用失败（网络、鉴权、余额、数据缺失等）。"""


class TikHubNotConfiguredError(TikHubError):
    """未配置 TikHub API Token，调用方应直接回退其他数据源。"""


def resolve_tikhub_token(config: Any = None) -> str:
    """按 config.tikhubApiKey → 环境变量 TIKHUB_API_TOKEN 的顺序解析 Token。"""
    token = ""
    if isinstance(config, dict):
        token = str(config.get("tikhubApiKey") or "").strip()
    elif config is not None:
        token = str(getattr(config, "tikhubApiKey", "") or "").strip()
    if not token:
        token = os.environ.get("TIKHUB_API_TOKEN", "").strip()
    if not token:
        raise TikHubNotConfiguredError(
            "未配置 TikHub API Token（config.tikhubApiKey 或环境变量 TIKHUB_API_TOKEN）。"
        )
    return token


def fetch_tweet_detail(tweet_id: str, token: str) -> dict:
    request_url = f"{TIKHUB_API_BASE}{TWEET_DETAIL_PATH}"
    try:
        response = httpx.get(
            request_url,
            params={"tweet_id": tweet_id},
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
            verify=False,
        )
    except httpx.HTTPError as exc:
        raise TikHubError(f"TikHub 请求失败: {exc}") from exc

    status = response.status_code
    if status == 401:
        raise TikHubError("TikHub Token 无效、缺失或未激活 (401)。")
    if status == 402:
        raise TikHubError("TikHub 账户余额不足 (402)。")
    if status == 404:
        raise TikHubError(f"TikHub 未找到推文 {tweet_id} (404)。")
    if status == 429:
        raise TikHubError("TikHub 请求过于频繁 (429)，请稍后重试。")
    if status != 200:
        raise TikHubError(f"TikHub 接口异常 (HTTP {status})。")

    try:
        payload = response.json()
    except ValueError as exc:
        raise TikHubError("TikHub 返回了非 JSON 数据。") from exc

    code = payload.get("code")
    if code not in (200, 0, None):
        message = payload.get("message") or payload.get("message_zh") or str(payload)[:200]
        raise TikHubError(f"TikHub 接口返回错误 (code={code}): {message}")

    data = payload.get("data")
    if not isinstance(data, dict):
        raise TikHubError("TikHub 返回的数据为空。")
    return data


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


def _extract_flat_media_urls(media: Any) -> list[str]:
    """从扁平结构的 media 字段容错提取图片/封面 URL。"""
    if isinstance(media, dict):
        media = media.get("all") or media.get("photos") or media.get("videos") or []
    media_urls: list[str] = []
    if isinstance(media, list):
        for item in media:
            if isinstance(item, dict):
                url = (
                    item.get("url")
                    or item.get("media_url_https")
                    or item.get("preview_image_url")
                    or item.get("thumbnail_url")
                    or ""
                )
                if url:
                    media_urls.append(url)
            elif isinstance(item, str) and item.startswith("http"):
                media_urls.append(item)
    return media_urls


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
