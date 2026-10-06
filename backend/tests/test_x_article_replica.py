import asyncio
from pathlib import Path

import httpx
import pytest
from bs4 import BeautifulSoup

from app.services.fetchers.x_article import _read, _text_matches, parse_x_article_page, fetch_x_article_replica

URL = 'https://x.com/author/status/123'
PAGE = '''<html><head><link rel="preload" as="font" href="https://abs.twimg.com/fonts/Chirp-Regular.woff2"></head>
<body><h1 itemprop="headline">原文标题</h1><img itemprop="image" src="https://pbs.twimg.com/media/cover.jpg">
<div class="x-article-body"><style>.leading-relaxed{line-height:1.625}</style><div class="contents">
<p class="leading-relaxed">正文<strong>加粗</strong><em>斜体</em><a href="https://example.com/reference">链接</a></p>
<figure><img src="https://pbs.twimg.com/media/a.jpg" alt="原图"></figure>
<h3>小标题</h3><ul><li>列表项</li></ul><figure><video src="https://video.twimg.com/tweet_video/a.mp4" poster="https://pbs.twimg.com/tweet_video_thumb/a.jpg" autoplay muted loop playsinline></video></figure>
<p>最后一段</p></div></div><article>不应收录的评论</article></body></html>'''


def test_extracts_article_only_preserving_order_and_rich_format():
    result = parse_x_article_page(PAGE, URL)
    soup = BeautifulSoup(result['body_html'], 'html.parser')
    assert soup.strong.text == '加粗'
    assert soup.em.text == '斜体'
    assert soup.h3.text == '小标题'
    assert soup.ul.li.text == '列表项'
    assert soup.video.has_attr('loop')
    assert '不应收录的评论' not in result['body_html']
    assert result['body_html'].index('原图') < result['body_html'].index('小标题') < result['body_html'].index('<video')
    assert result['title'] == '原文标题'
    assert result['font_urls'] == ['https://abs.twimg.com/fonts/Chirp-Regular.woff2']


def test_rejects_login_or_missing_article_and_removes_active_content():
    with pytest.raises(ValueError, match='正文'):
        parse_x_article_page('<h1>登录</h1>', URL)
    attack = PAGE.replace('正文<strong>', '''<script>alert(1)</script><iframe src="http://localhost"></iframe><img src="http://127.0.0.1/private" onerror="alert(1)"><a href="javascript:alert(1)">链接</a>正文<strong>''')
    body = parse_x_article_page(attack, URL)['body_html']
    assert '<script' not in body and '<iframe' not in body
    assert 'onerror' not in body and 'javascript:' not in body and '127.0.0.1' not in body


def test_saves_media_and_fonts_and_checks_tikhub_text(tmp_path):
    requests = []
    def handle(request):
        requests.append(str(request.url))
        if request.url.host == 'x.com': return httpx.Response(200, text=PAGE)
        if request.url.path.endswith('.mp4'): return httpx.Response(200, content=b'\x00\x00\x00\x18ftypmp42', headers={'Content-Type':'video/mp4'})
        if request.url.path.endswith('.woff2'): return httpx.Response(200, content=b'wOF2font', headers={'Content-Type':'font/woff2'})
        return httpx.Response(200, content=b'\xff\xd8\xffimage', headers={'Content-Type':'image/jpeg'})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            return await fetch_x_article_replica(URL, {'full_text':'正文加粗斜体链接小标题列表项最后一段'}, lambda _:None, client=client, media_dir=tmp_path)
    result = asyncio.run(run())
    assert result['status'] == 'complete'
    assert result['text_verified'] is True
    assert len(result['assets']) == 5
    assert 'https://video.twimg.com' not in result['body_html']
    assert '/media/x/' in result['body_html']
    assert len(list(tmp_path.rglob('*.mp4'))) == 1
    assert all(Path(tmp_path / a['local_url'].removeprefix('/media/')).exists() for a in result['assets'])
    assert 'Authorization' not in str(requests)


def test_incomplete_assets_report_partial_and_bad_redirect_is_not_fetched(tmp_path):
    called = []
    def handle(request):
        called.append(request.url.host)
        if request.url.host == 'x.com': return httpx.Response(200, text=PAGE)
        return httpx.Response(302, headers={'Location':'http://127.0.0.1/private'})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            return await fetch_x_article_replica(URL, {}, lambda _:None, client=client, media_dir=tmp_path)
    result = asyncio.run(run())
    assert result['status'] == 'partial'
    assert result['warnings']
    assert '127.0.0.1' not in called


def test_wrong_article_text_is_not_silently_accepted(tmp_path):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200,text=PAGE))) as client:
            return await fetch_x_article_replica(URL, {'full_text':'完全不同的正文'}, lambda _:None, client=client,media_dir=tmp_path)
    with pytest.raises(ValueError, match='不一致'):
        asyncio.run(run())


def test_tikhub_text_missing_diagram_blocks_still_matches():
    # 实测：TikHub 全文会丢失正文里的 ASCII 示意图与文末对照表文字，逐字校验会把这类长文误降级为纯文本。
    body = '编程 Agent 向 LLM 发出的第一次请求包含初始上下文，以及用户的第一条消息。' * 20
    captured = body + 'text请求1：[系统][工具][用户]' + 'text压缩后：[系统][工具][摘要]' + '概念主要作用上下文窗口限制模型一次能够处理的内容范围'
    assert _text_matches(body, captured)


def test_read_retries_transport_errors_before_giving_up():
    calls = {'n': 0}

    def handler(request):
        calls['n'] += 1
        if calls['n'] == 1:
            raise httpx.ConnectError('闪断', request=request)
        return httpx.Response(200, content=b'ok', headers={'content-type': 'text/html; charset=utf-8'})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await _read(client, URL, {'x.com'}, 1024)

    data, mime = asyncio.run(run())
    assert data == b'ok' and mime == 'text/html'
    assert calls['n'] == 2


def test_read_does_not_retry_http_status_errors():
    calls = {'n': 0}

    def handler(request):
        calls['n'] += 1
        return httpx.Response(404)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await _read(client, URL, {'x.com'}, 1024)

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(run())
    assert calls['n'] == 1
