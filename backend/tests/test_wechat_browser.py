import asyncio

from app.config import settings
from app.services.fetchers.wechat_browser import (
    _wait_for_wechat_content,
    is_wechat_blocked_page,
)


def test_wechat_captcha_redirect_is_blocked():
    assert is_wechat_blocked_page(
        "https://mp.weixin.qq.com/mp/wappoc_appmsgcaptcha?poc_token=redacted",
        "<h2>环境异常</h2>",
    )


def test_normal_wechat_article_is_not_blocked():
    assert not is_wechat_blocked_page(
        "https://mp.weixin.qq.com/s/example",
        '<div id="js_content">文章正文</div>',
    )


def test_wechat_browser_is_disabled_for_link_imports():
    assert settings.WECHAT_BROWSER_ENABLED is False


class _FakePage:
    def __init__(self, url: str, html: str):
        self.url = url
        self.html = html
        self.closed = False

    def is_closed(self):
        return self.closed

    async def content(self):
        if self.closed:
            raise RuntimeError("page closed")
        return self.html


class _FakeContext:
    def __init__(self, pages):
        self.pages = pages
        self._swapped = False

    async def advance(self):
        if not self._swapped:
            self.pages[0].closed = True
            self.pages.append(
                _FakePage(
                    "https://mp.weixin.qq.com/s/article",
                    '<div id="js_content">' + ("正文" * 100) + "</div>",
                )
            )
            self._swapped = True
        await asyncio.sleep(0)


def test_wechat_fetch_uses_new_article_page_after_captcha_page_closes():
    captcha_page = _FakePage(
        "https://mp.weixin.qq.com/mp/wappoc_appmsgcaptcha",
        "<h2>环境异常</h2>",
    )
    context = _FakeContext([captcha_page])

    html = asyncio.run(_wait_for_wechat_content(context, captcha_page, timeout_ms=1000))

    assert 'id="js_content"' in html
    assert len(html) > 180
