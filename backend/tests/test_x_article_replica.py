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


def test_preserves_shiki_css_custom_properties_for_syntax_colors():
    # 实测（xueyu1125/status/2111023511603188071）：X 代码块语法高亮靠 inline 的
    # --shiki-light/--shiki-dark 自定义属性，不在白名单会被整段剥掉，代码全部失去颜色。
    page = PAGE.replace(
        '<figure><img src="https://pbs.twimg.com/media/a.jpg" alt="原图"></figure>',
        '<div class="x-article-code"><div><span class="x-article-code-font">bash</span></div>'
        '<div class="x-article-code-body"><pre class="shiki" style="--shiki-light:#0a0a0a;--shiki-dark:#e5e5e5;--shiki-light-bg:#fffffe;--shiki-dark-bg:#1e1e1e"><code>'
        '<span class="line"><span style="--shiki-light:#009FFF;--shiki-dark:#08C0EF">brew</span> install uv</span>'
        '</code></pre></div></div>',
    )
    body = parse_x_article_page(page, URL)['body_html']
    assert '--shiki-light:#0a0a0a' in body and '--shiki-dark-bg:#1e1e1e' in body
    assert '--shiki-light:#009FFF;--shiki-dark:#08C0EF' in body
    # 危险值仍被拒绝：含 url()/expression/尖括号的自定义属性不保留
    evil = PAGE.replace('<p class="leading-relaxed">', '<p style="--evil:url(https://evil/x);--ok:#fff">')
    body2 = parse_x_article_page(evil, URL)['body_html']
    assert '--evil' not in body2 and '--ok:#fff' in body2


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


def test_tikhub_text_missing_half_the_article_still_matches():
    # 实测（xueyu1125/status/2111023511603188071）：TikHub 纯文本全文丢失全部代码块，
    # 全文 3932 字 vs 原页 7950 字，整体相似度仅 0.64，被误判为不同文章导致补采整体失败。
    paragraphs = '我要用 mlx-lm 对 Qwen2.5-1.5B-Instruct 做 LoRA 微调，请把目录下的文件清洗成问答对。' * 30
    code_blocks = 'bash#用Homebrew安装uvbrewinstalluv' + 'toml[project]name="qwen2-5-1-5b-x"version="0.1.0"requires-python=">=3.13"' + 'bash#验证MLX是否识别AppleGPU，输出应为Metal:True' * 10
    page_text = paragraphs + code_blocks + paragraphs  # 原页：正文 + 大量代码块
    tikhub_text = paragraphs + paragraphs  # TikHub：只剩段落，代码块全丢
    assert _text_matches(tikhub_text, page_text)


def test_unrelated_article_text_is_rejected():
    expected = '第一篇文章讲大模型微调的完整流程' * 30
    captured = '第二篇文章完全在讲另一个话题的内容' * 30
    assert not _text_matches(expected, captured)


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
