from __future__ import annotations

from typing import Any


def _deep_get(value: Any, *keys: Any) -> Any:
    current = value
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
        elif isinstance(current, list) and isinstance(key, int) and 0 <= key < len(current):
            current = current[key]
        else:
            return None
    return current


def _normalize_entity_map(entity_map: Any) -> dict[str, Any]:
    if isinstance(entity_map, dict):
        return {str(key): value for key, value in entity_map.items()}
    if isinstance(entity_map, list):
        normalized: dict[str, Any] = {}
        for item in entity_map:
            if not isinstance(item, dict) or item.get("key") is None:
                continue
            if item.get("value") is not None:
                normalized[str(item["key"])] = item["value"]
        return normalized
    return {}


def _find_image_url(value: Any) -> str:
    if isinstance(value, dict):
        for key in (
            "original_img_url",
            "originalImgUrl",
            "original_url",
            "originalUrl",
            "media_url_https",
            "mediaUrlHttps",
            "media_url",
            "mediaUrl",
            "url",
            "src",
            "uri",
        ):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                lowered = candidate.lower()
                if lowered.startswith("https://pbs.twimg.com/") or any(
                    extension in lowered
                    for extension in (".jpg", ".jpeg", ".png", ".gif", ".webp")
                ):
                    return candidate.strip()
        for nested in value.values():
            found = _find_image_url(nested)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_image_url(item)
            if found:
                return found
    return ""


def _find_caption(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("caption", "alt", "alt_text", "altText", "title", "name"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        for nested in value.values():
            found = _find_caption(nested)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_caption(item)
            if found:
                return found
    return ""


def _article_media_url_map(article_result: dict[str, Any]) -> dict[str, str]:
    media_url_map: dict[str, str] = {}
    for media in article_result.get("media_entities") or []:
        if not isinstance(media, dict):
            continue
        image_url = _find_image_url(media.get("media_info") or {}) or _find_image_url(media)
        if not image_url:
            continue
        for key in ("media_id", "media_key", "id"):
            candidate = media.get(key)
            if candidate is not None:
                media_url_map[str(candidate)] = image_url
    return media_url_map


def _render_atomic_block(block: dict[str, Any], entity_map: dict[str, Any], media_url_map: dict[str, str]) -> list[str]:
    parts: list[str] = []
    for entity_range in block.get("entityRanges") or []:
        if not isinstance(entity_range, dict):
            continue
        entity_key = entity_range.get("key")
        entity = entity_map.get(str(entity_key)) if entity_key is not None else None
        if not isinstance(entity, dict):
            continue

        entity_type = str(entity.get("type") or "").upper()
        if entity_type == "MARKDOWN":
            markdown = _deep_get(entity, "data", "markdown")
            if isinstance(markdown, str) and markdown.strip():
                parts.append(markdown.strip())
            continue

        image_urls: list[str] = []
        direct_image_url = _find_image_url(entity)
        if direct_image_url:
            image_urls.append(direct_image_url)
        else:
            for media_item in _deep_get(entity, "data", "mediaItems") or []:
                media_id = media_item.get("mediaId") if isinstance(media_item, dict) else None
                if media_id is not None and str(media_id) in media_url_map:
                    image_urls.append(media_url_map[str(media_id)])
        caption = _find_caption(entity) or "X 文章配图"
        parts.extend(f"![{caption}]({image_url})" for image_url in image_urls)
    return parts


def render_twitter_article_result(article_result: dict[str, Any]) -> dict[str, Any]:
    content_state = article_result.get("content_state") or {}
    entity_map = _normalize_entity_map(content_state.get("entityMap"))
    media_url_map = _article_media_url_map(article_result)
    parts: list[str] = []
    media_urls: list[str] = []
    ordered_counter = 0

    for block in content_state.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type", "unstyled")
        if block_type == "atomic":
            atomic_parts = _render_atomic_block(block, entity_map, media_url_map)
            parts.extend(atomic_parts)
            for part in atomic_parts:
                if part.startswith("![") and "](" in part and part.endswith(")"):
                    media_urls.append(part.rsplit("](", 1)[1][:-1])
            ordered_counter = 0
            continue

        text = str(block.get("text") or "")
        if not text:
            continue
        if block_type != "ordered-list-item":
            ordered_counter = 0
        if block_type == "header-one":
            parts.append(f"# {text}")
        elif block_type == "header-two":
            parts.append(f"## {text}")
        elif block_type == "header-three":
            parts.append(f"### {text}")
        elif block_type == "blockquote":
            parts.append(f"> {text}")
        elif block_type == "unordered-list-item":
            parts.append(f"- {text}")
        elif block_type == "ordered-list-item":
            ordered_counter += 1
            parts.append(f"{ordered_counter}. {text}")
        elif block_type == "code-block":
            parts.append(f"```\n{text}\n```")
        else:
            parts.append(text)

    return {
        "title": article_result.get("title") or "未知 X 长文",
        "content_md": "\n\n".join(parts).strip(),
        "media_urls": list(dict.fromkeys(media_urls)),
        "cover_image_url": _find_image_url(article_result.get("cover_media") or {}),
    }
