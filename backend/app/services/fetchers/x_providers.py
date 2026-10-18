"""Try supported X providers in saved order, sharing the existing reader format."""
import asyncio

from app.services.fetch_priorities import PROVIDERS, resolve_priorities
from app.services.fetchers.content_downloader_x import fetch_content_downloader_tweet
from app.services.fetchers.x_twitter_cli import fetch_x_via_twitter_cli


def _has_content(result: dict) -> bool:
    if not isinstance(result, dict) or not isinstance(result.get("payload"), dict):
        return False
    payload = result["payload"]
    return bool(str(payload.get("tweet_text") or "").strip() or payload.get("media_items")
                or payload.get("media_urls") or result.get("article_result")
                or (result.get("article_text") or {}).get("full_text"))


async def fetch_x_with_priority(url: str, config: dict, update_step, *, tikhub_fetcher) -> dict:
    errors = []
    for index, provider in enumerate(resolve_priorities(config)["x"]):
        label = PROVIDERS[provider]["label"]
        prefix = "正在回退到" if index else "正在通过"
        update_step(f"{prefix} {label} 获取 X 内容...")
        try:
            if provider == "content_downloader":
                result = await fetch_content_downloader_tweet(url)
            elif provider == "twitter_cli":
                result = await fetch_x_via_twitter_cli(url, update_step, config)
            else:
                result = await asyncio.to_thread(tikhub_fetcher, url, config)
            if not _has_content(result):
                raise RuntimeError("未返回有效正文或媒体")
            update_step(f"{label} 获取成功，正在整理正文...")
            return {**result, "provider_label": label}
        except Exception as exc:
            message = str(exc)
            for key in ("tikhubApiKey", "apiKey", "minimaxApiKey", "imapPassword", "twitterAuthToken", "twitterCt0"):
                secret = str((config or {}).get(key) or "")
                if secret:
                    message = message.replace(secret, "[已隐藏]")
            errors.append(f"{label}：{message[:180]}")
    raise RuntimeError("X 内容获取失败；" + "；".join(errors))
