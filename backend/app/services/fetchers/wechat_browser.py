"""Read a public WeChat article through a real browser when HTTP is challenged."""

import asyncio
import shutil
from pathlib import Path

from bs4 import BeautifulSoup

from app.config import settings


BLOCKED_PAGE_MARKERS = (
    "环境异常",
    "访问过于频繁",
    "操作频繁",
    "安全验证",
    "完成验证",
    "请在微信客户端打开",
    "内容可能因违规无法查看",
)

CONTENT_READY_SCRIPT = """() => {
  const el = document.querySelector('#js_content');
  return !!el && ((el.innerText || el.textContent || '').trim().length >= 120);
}"""
MIN_WECHAT_CONTENT_CHARS = 180


def _resolve_browser_executable() -> str | None:
    """Use an installed browser when the Python package cache is out of sync."""
    configured = str(getattr(settings, "WECHAT_BROWSER_EXECUTABLE_PATH", "") or "").strip()
    candidates = [Path(configured)] if configured else []
    candidates.extend(
        [
            Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            Path.home()
            / "Library/Caches/ms-playwright/chromium-1223/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
        ]
    )
    for command in ("google-chrome", "chromium", "chromium-browser"):
        resolved = shutil.which(command)
        if resolved:
            candidates.append(Path(resolved))

    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


def is_wechat_blocked_page(url: str, html: str) -> bool:
    page_url = (url or "").lower()
    if "/mp/wappoc_appmsgcaptcha" in page_url:
        return True
    return any(marker in (html or "") for marker in BLOCKED_PAGE_MARKERS)


async def _wait_for_wechat_content(context, initial_page, timeout_ms: int) -> str:
    """Follow the article page when WeChat closes or replaces the captcha tab."""
    deadline = asyncio.get_running_loop().time() + timeout_ms / 1000

    while asyncio.get_running_loop().time() < deadline:
        pages = list(getattr(context, "pages", []))
        if initial_page not in pages:
            pages.append(initial_page)

        for candidate in reversed(pages):
            if getattr(candidate, "is_closed", lambda: False)():
                continue
            try:
                html = await candidate.content()
            except Exception:
                continue

            if is_wechat_blocked_page(getattr(candidate, "url", ""), html):
                continue
            soup = BeautifulSoup(html, "html.parser")
            content = soup.find("div", {"id": "js_content"})
            content_text = content.get_text(" ", strip=True) if content else ""
            if len(content_text) >= MIN_WECHAT_CONTENT_CHARS:
                return html

        advance = getattr(context, "advance", None)
        if advance is not None:
            await advance()
        else:
            await asyncio.sleep(0.25)

    from playwright.async_api import TimeoutError as PlaywrightTimeoutError

    raise PlaywrightTimeoutError("Timed out waiting for WeChat article content")


async def fetch_wechat_article_html(url: str, update_step) -> str:
    """Use an app-owned persistent browser profile for WeChat verification."""
    try:
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError
        from playwright.async_api import async_playwright
    except Exception as exc:
        raise RuntimeError("微信页面需要浏览器读取，但 Python Playwright 不可用。") from exc

    profile_dir = Path(settings.WECHAT_BROWSER_PROFILE_DIR).expanduser()
    profile_dir.mkdir(parents=True, exist_ok=True)
    timeout = settings.WECHAT_BROWSER_TIMEOUT_MS
    verify_timeout = settings.WECHAT_BROWSER_VERIFY_TIMEOUT_MS
    executable_path = _resolve_browser_executable()

    async with async_playwright() as playwright:
        try:
            launch_options = {
                "headless": settings.WECHAT_BROWSER_HEADLESS,
                "viewport": {"width": 1280, "height": 1100},
            }
            if executable_path:
                launch_options["executable_path"] = executable_path
            context = await playwright.chromium.launch_persistent_context(
                str(profile_dir),
                **launch_options,
            )
        except Exception as exc:
            raise RuntimeError(f"无法启动微信浏览器读取器：{exc}") from exc

        page = await context.new_page()
        page.set_default_timeout(timeout)
        page.set_default_navigation_timeout(timeout)
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            page_html = await page.content()
            blocked = is_wechat_blocked_page(page.url, page_html)

            if blocked:
                update_step("微信触发安全验证，请在弹出的浏览器中完成验证后继续...")
                wait_timeout = verify_timeout
            else:
                wait_timeout = min(timeout, 12000)

            try:
                page_html = await _wait_for_wechat_content(context, page, wait_timeout)
            except PlaywrightTimeoutError as exc:
                if blocked:
                    raise RuntimeError("微信安全验证未完成，未获取到正文。请完成验证后重试。") from exc
                raise

            if "id=\"js_content\"" not in page_html and "id='js_content'" not in page_html:
                raise RuntimeError("浏览器页面没有找到微信公众号正文节点。")
            soup = BeautifulSoup(page_html, "html.parser")
            content = soup.find("div", {"id": "js_content"})
            content_text = content.get_text(" ", strip=True) if content else ""
            if len(content_text) < MIN_WECHAT_CONTENT_CHARS:
                raise RuntimeError(f"微信正文过短（{len(content_text)} 字），未保存不完整内容。")
            return page_html
        finally:
            await context.close()
