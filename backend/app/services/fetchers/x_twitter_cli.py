import asyncio
import os
import re
import shutil
from pathlib import Path
from typing import Any


X_ARTICLE_URL_PATTERN = re.compile(
    r"https?://(?:www\.)?(?:x\.com|twitter\.com)/i/article/(?P<id>\d+)",
    re.IGNORECASE,
)
X_TWEET_URL_PATTERN = re.compile(
    r"https?://(?:www\.)?(?:x\.com|twitter\.com)/[^/]+/(?:status|statuses)/(?P<id>\d+)",
    re.IGNORECASE,
)


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


def parse_twitter_article_markdown(markdown: str) -> dict[str, Any]:
    lines = markdown.splitlines()
    title = "未知 X 长文"
    original_url = ""

    if lines and lines[0].startswith("# "):
        title = lines[0][2:].strip() or title

    metadata_end = 0
    for index, line in enumerate(lines[1:], start=1):
        if line.startswith("- URL:"):
            original_url = line.removeprefix("- URL:").strip()
        if line.startswith("- ") or not line.strip():
            metadata_end = index
            continue
        if metadata_end and line.strip():
            break

    content_md = "\n".join(lines[metadata_end + 1:]).strip()
    if not content_md:
        raise RuntimeError("twitter-cli 未返回 X 长文正文。")

    return {
        "title": title,
        "original_url": original_url,
        "content_md": content_md,
        "plain_text": content_md,
        "cover_image_url": "",
    }


def _twitter_command() -> str:
    configured = os.environ.get("SYNTHAI_TWITTER_BIN", "").strip()
    if configured:
        return configured

    command = shutil.which("twitter")
    if command:
        return command

    raise RuntimeError(
        "未找到 twitter-cli。请先安装 Agent-Reach Twitter 渠道，或设置 SYNTHAI_TWITTER_BIN。"
    )


def _twitter_python(command: str) -> str | None:
    try:
        first_line = Path(command).read_text(encoding="utf-8").splitlines()[0]
    except (OSError, IndexError):
        return None

    if first_line.startswith("#!"):
        interpreter = first_line[2:].strip().split()[0]
        if interpreter and shutil.which(interpreter):
            return interpreter
        if interpreter and Path(interpreter).exists():
            return interpreter
    return None


def _twitter_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in (
        "PYTHONHOME",
        "PYTHONPATH",
        "__PYVENV_LAUNCHER__",
    ):
        env.pop(key, None)
    return env


async def _fetch_rich_article(url: str, command: str) -> dict[str, Any] | None:
    tweet_id = extract_x_tweet_id(url)
    interpreter = _twitter_python(command)
    script = Path(__file__).resolve().parents[3] / "scripts" / "fetch_twitter_article_rich.py"
    if not tweet_id or not interpreter or not script.exists():
        return None

    process = await asyncio.create_subprocess_exec(
        interpreter,
        str(script),
        tweet_id,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=_twitter_subprocess_env(),
    )
    try:
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=90)
    except asyncio.TimeoutError:
        process.kill()
        await process.communicate()
        return None

    if process.returncode != 0:
        return None

    try:
        payload = __import__("json").loads(stdout.decode("utf-8", errors="replace"))
    except ValueError:
        return None
    return payload if isinstance(payload, dict) and payload.get("content_md") else None


async def fetch_x_article_via_twitter_cli(url: str, update_step) -> dict[str, Any]:
    update_step("正在使用本机 X 登录态读取长文...")
    command = _twitter_command()
    process = await asyncio.create_subprocess_exec(
        command,
        "article",
        url,
        "--markdown",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=_twitter_subprocess_env(),
    )

    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=90)
    except asyncio.TimeoutError as exc:
        process.kill()
        await process.communicate()
        raise RuntimeError("twitter-cli 读取 X 长文超时。") from exc

    output = stdout.decode("utf-8", errors="replace")
    error_output = stderr.decode("utf-8", errors="replace").strip()
    if process.returncode != 0:
        detail = error_output or output.strip() or f"退出码 {process.returncode}"
        raise RuntimeError(f"twitter-cli 读取 X 长文失败: {detail[-1000:]}")

    article = parse_twitter_article_markdown(output)
    rich_article = await _fetch_rich_article(url, command)
    if rich_article:
        article.update(rich_article)
        update_step(
            f"X 长文读取成功: {article['title']}，已恢复 {len(article.get('media_urls', []))} 张内嵌图片。正在整理排版..."
        )
        return article

    update_step(f"X 长文读取成功: {article['title']}。正在整理排版...")
    return article
