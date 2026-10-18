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
        "description": "使用微信公众号公开网页获取方法，无需 TikHub Key；验证页或空正文自动回退。",
    },
    "x_graphql": {"label": "X GraphQL", "description": "通过 TweetResultByRestId 获取完整 JSON，将 Draft.js 渲染为文章库正文，图片和 GIF/视频保存到本地；复用「X 登录配置」中的登录态，无需安装 twitter-cli。"},
    "direct": {"label": "网页直取", "description": "直接获取网页并解析正文。"},
    "yt_dlp": {"label": "yt-dlp", "description": "获取视频与字幕；无字幕时使用已配置的 MiniMax 转写，需服务器安装 ffmpeg。"},
    "twitter_cli": {"label": "twitter-cli", "description": "使用 X 登录态获取正文和长文富文本；在后台「X 登录配置」中保存 auth_token 与 ct0，后端需已安装 twitter-cli。"},
}
PLATFORMS = {
    "x": {"label": "X / Twitter", "providers": ["tikhub", "x_graphql", "twitter_cli"]},
    "wechat": {"label": "微信公众号", "providers": ["tikhub", "content_downloader"]},
    "bilibili": {"label": "Bilibili", "providers": ["tikhub"]},
    "youtube": {"label": "YouTube", "providers": ["yt_dlp", "tikhub"]},
    "csdn": {"label": "CSDN", "providers": ["direct"]},
    "cnblogs": {"label": "博客园", "providers": ["direct"]},
    "web": {"label": "其他网页", "providers": ["direct"]},
}

# Requirements describe server-side deployment, not whether the current host has
# been probed. Keep conditional video/browser dependencies scoped to platforms.
FFMPEG_REQUIREMENT = {
    "name": "ffmpeg / ffprobe",
    "summary": "音频转写需 ffmpeg",
    "condition": "仅在没有可用字幕、需要下载音频转写时",
    "description": "安装 ffmpeg（包含 ffprobe），并配置后台「语音转写」的 MiniMax Key。有字幕时不需要音频转写。",
    "commands": [{"label": "Ubuntu / Debian", "command": "sudo apt update\nsudo apt install -y ffmpeg"}],
    "config_link": {"label": "语音转写配置", "href": "/admin/model?section=transcription"},
}
DEPLOYMENT_REQUIREMENTS = {
    "x": [{
        "name": "twitter-cli",
        "summary": "twitter-cli 需单独安装",
        "condition": "仅选择 twitter-cli 方式时",
        "description": "不包含在项目 requirements.txt 中。安装后，运行后端的用户需能执行 twitter；找不到时可在「X 登录配置」填写绝对路径。还需配置 auth_token 与 ct0。",
        "commands": [{"label": "安装（需要 uv）", "command": "uv tool install twitter-cli"},
                     {"label": "检查命令是否可用", "command": "twitter --version"}],
        "docs_url": "https://github.com/public-clis/twitter-cli#installation",
        "config_link": {"label": "X 登录配置", "href": "/admin/tikhub?section=twitter-cli"},
    }],
    "bilibili": [FFMPEG_REQUIREMENT],
    "youtube": [{
        "name": "Node.js 22+ 或 Deno 2.3+",
        "summary": "yt-dlp 需 Node.js / Deno",
        "condition": "yt-dlp 解析 YouTube；也包括 TikHub 无字幕时的音频下载回退",
        "description": "在后端服务器安装其中一种 JS 运行时，并加入运行用户的 PATH。项目会自动启用可用的 Node.js，Deno 由 yt-dlp 默认启用；yt-dlp 与 EJS 随 requirements.txt 安装。",
        "commands": [{"label": "检查已安装的运行时（任选一种）", "command": "node --version\n# 或\ndeno --version"}],
        "docs_url": "https://github.com/yt-dlp/yt-dlp/wiki/EJS",
    }, FFMPEG_REQUIREMENT],
    "csdn": [{
        "name": "Playwright Chromium",
        "summary": "浏览器抓取需 Chromium",
        "condition": "CSDN 浏览器抓取路径",
        "description": "Playwright Python 包随项目安装，Chromium 浏览器和 Linux 运行库需额外安装。使用运行后端的同一 Python 环境执行；缺少浏览器时会退回直接请求，部分页面可能无法获取。",
        "commands": [{"label": "Ubuntu / Debian（含系统运行库）", "command": "python -m playwright install --with-deps chromium"},
                     {"label": "其他系统", "command": "python -m playwright install chromium"}],
        "docs_url": "https://playwright.dev/python/docs/browsers",
    }],
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
                if platform == "x" and provider == "content_downloader":
                    provider = "x_graphql"
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
    from app.services.twitter_cli_settings import resolve_twitter_cli
    providers = {key: dict(value) for key, value in PROVIDERS.items()}
    providers["twitter_cli"].update(twitter_cli_status(config))
    credentials = resolve_twitter_cli(config)
    providers["x_graphql"]["status"] = "已配置 X 登录态" if credentials["auth"] and credentials["csrf"] else "未配置 X 登录态"
    platforms = {key: {**value, "requirements": DEPLOYMENT_REQUIREMENTS.get(key, [])}
                 for key, value in PLATFORMS.items()}
    return {"platforms": platforms, "providers": providers, "priorities": resolve_priorities(config)}
