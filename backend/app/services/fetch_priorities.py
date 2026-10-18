"""Supported fetching methods and per-platform persisted ordering.

Only listed providers can run. Adding a provider requires registering its
capabilities here and implementing the corresponding platform handler.
"""
import json

SETTINGS_KEY = "fetchProviderPriorities"
PROVIDERS = {
    "tikhub": {"label": "TikHub", "description": "使用后台保存的 TikHub API Key。"},
    "content_downloader": {
        "label": "Content Downloader",
        "description": "使用 Content Downloader 的平台专用获取方法，无需 TikHub Key；空正文或不支持的内容自动回退。",
    },
    "direct": {"label": "网页直取", "description": "直接获取网页并解析正文。"},
    "yt_dlp": {"label": "yt-dlp", "description": "获取视频与字幕；无字幕时使用已配置的 MiniMax 转写，需服务器安装 ffmpeg。"},
    "twitter_cli": {"label": "twitter-cli", "description": "使用 X 登录态获取正文和长文富文本；在后台「X 登录配置」中保存 auth_token 与 ct0，后端需已安装 twitter-cli。"},
}
PLATFORMS = {
    "x": {"label": "X / Twitter", "providers": ["tikhub", "content_downloader", "twitter_cli"]},
    "wechat": {"label": "微信公众号", "providers": ["tikhub", "content_downloader"]},
    "bilibili": {"label": "Bilibili", "providers": ["tikhub"]},
    "youtube": {"label": "YouTube", "providers": ["yt_dlp", "tikhub"]},
    "csdn": {"label": "CSDN", "providers": ["direct"]},
    "cnblogs": {"label": "博客园", "providers": ["direct"]},
    "web": {"label": "其他网页", "providers": ["direct"]},
}


def resolve_priorities(config: dict | None = None) -> dict[str, list[str]]:
    """Missing/corrupt/obsolete stored values never break existing imports."""
    try:
        stored = json.loads((config or {}).get(SETTINGS_KEY) or "{}")
    except (ValueError, TypeError):
        stored = {}
    if not isinstance(stored, dict):
        stored = {}
    result = {}
    for platform, info in PLATFORMS.items():
        supported = info["providers"]
        saved = stored.get(platform, [])
        order = []
        if isinstance(saved, list):
            for provider in saved:
                if provider in supported and provider not in order:
                    order.append(provider)
        result[platform] = order + [provider for provider in supported if provider not in order]
    return result


def validate_priorities(priorities: dict[str, list[str]]) -> None:
    for platform, order in priorities.items():
        if platform not in PLATFORMS:
            raise ValueError(f"不支持的平台：{platform}")
        supported = PLATFORMS[platform]["providers"]
        if len(order) != len(supported) or set(order) != set(supported):
            raise ValueError(f"{PLATFORMS[platform]['label']} 的获取方式必须各出现一次，不可缺少或重复")


def priority_view(config: dict) -> dict:
    from app.services.fetchers.x_twitter_cli import twitter_cli_status
    providers = {key: dict(value) for key, value in PROVIDERS.items()}
    providers["twitter_cli"].update(twitter_cli_status(config))
    return {"platforms": PLATFORMS, "providers": providers, "priorities": resolve_priorities(config)}
