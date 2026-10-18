"""WeChat fetching must preserve rich HTML and never save challenge pages."""
import asyncio
import json
import httpx
import pytest
from app.services.fetchers import article

URL = 'https://mp.weixin.qq.com/s/article-id'
PRIORITY = {'fetchProviderPriorities': json.dumps({'wechat': ['content_downloader', 'tikhub']})}
HTML = '''<html><head><meta property="og:title" content="微信技术文章"><meta property="og:image" content="https://mmbiz.qpic.cn/cover.jpg"></head>
<body><h1 id="activity-name">微信技术文章</h1><a id="js_name">技术公众号</a><em id="publish_time">2026-10-18</em>
<div id="js_content" style="color:#333"><section><div><p>第一段完整正文。</p><p>第二段说明。</p></div></section>
<p><img data-src="https://mmbiz.qpic.cn/image.png?wx_fmt=png"></p><pre><code style="white-space:nowrap">a();<br>b();</code></pre><mpvoice voice_encode_fileid="audio-id"></mpvoice></div></body></html>'''
TIKHUB = {'title': 'TikHub 后备正文', 'html_content': '<div id="js_content"><p>后备完整正文。</p></div>',
          'content_text': '后备完整正文。', 'cover_image_url': '', 'account_name': '后备公众号', 'publish_time': ''}


def mock_page(monkeypatch, html=HTML, status=200):
    original = httpx.AsyncClient
    def handler(request):
        assert request.url.host == 'mp.weixin.qq.com'
        assert 'Chrome/' in request.headers['user-agent']
        return httpx.Response(status, text=html, headers={'Content-Type': 'text/html; charset=utf-8'})
    monkeypatch.setattr(article.httpx, 'AsyncClient', lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handler)))


def fail_if_tikhub(*args):
    raise AssertionError('首选成功后不应访问付费方式')


def test_wechat_direct_fetch_preserves_rich_body_and_metadata(monkeypatch):
    mock_page(monkeypatch)
    monkeypatch.setattr(article, 'fetch_wechat_article', fail_if_tikhub)
    result = asyncio.run(article.fetch_article_content(URL, lambda step: None, PRIORITY))
    assert result['title'] == '微信技术文章'
    assert result['account_name'] == '技术公众号'
    assert result['publish_time'] == '2026-10-18'
    assert result['cover_image_url'] == 'https://mmbiz.qpic.cn/cover.jpg'
    assert '第一段完整正文' in result['extracted_md']
    assert '第二段说明' in result['html_content']
    assert '<br/>' in result['html_content'] and 'white-space:nowrap' in result['html_content']
    assert 'wx_fmt=png' in result['html_content'] and 'audio-id' in result['html_content']


@pytest.mark.parametrize('html,status', [
    ('<html><body>环境异常，请完成验证</body></html>', 200),
    ('<div id="js_content"></div>', 200), ('<div id="js_content"><img src=""></div>', 200), ('<div id="js_content"> </div>', 200),
    ('<html><body>文章已被删除</body></html>', 404),
])
def test_invalid_direct_content_falls_back_to_tikhub(monkeypatch, html, status):
    mock_page(monkeypatch, html, status)
    monkeypatch.setattr(article, 'fetch_wechat_article', lambda *args: dict(TIKHUB))
    steps = []
    result = asyncio.run(article.fetch_article_content(URL, steps.append, PRIORITY))
    assert result['title'] == 'TikHub 后备正文'
    assert '后备完整正文' in result['html_content']
    assert any('回退' in step and 'TikHub' in step for step in steps)


def test_tikhub_first_success_does_not_access_direct_page(monkeypatch):
    monkeypatch.setattr(article, 'fetch_wechat_article', lambda *args: dict(TIKHUB))
    def unexpected(*args, **kwargs):
        raise AssertionError('TikHub 成功时不应直连')
    monkeypatch.setattr(article.httpx, 'AsyncClient', unexpected)
    assert asyncio.run(article.fetch_article_content(URL, lambda step: None, {}))['title'] == 'TikHub 后备正文'


def test_no_tikhub_key_still_fetches_public_article(monkeypatch):
    from app.services.fetchers.tikhub import TikHubNotConfiguredError
    mock_page(monkeypatch)
    def unconfigured(*args):
        raise TikHubNotConfiguredError('未配置 TikHub API Token')
    monkeypatch.setattr(article, 'fetch_wechat_article', unconfigured)
    assert asyncio.run(article.fetch_article_content(URL, lambda step: None, {}))['title'] == '微信技术文章'


def test_empty_tikhub_response_is_also_retried_using_direct_method(monkeypatch):
    mock_page(monkeypatch)
    monkeypatch.setattr(article, 'fetch_wechat_article', lambda *args: {**TIKHUB, 'html_content': '', 'content_text': ''})
    assert asyncio.run(article.fetch_article_content(URL, lambda step: None, {}))['title'] == '微信技术文章'


def test_all_failures_report_both_providers_without_leaking_key(monkeypatch):
    mock_page(monkeypatch, '<html>环境异常，请完成验证</html>')
    def broken(*args):
        raise RuntimeError('凭据 secret-wechat-key 无效')
    monkeypatch.setattr(article, 'fetch_wechat_article', broken)
    with pytest.raises(RuntimeError) as caught:
        asyncio.run(article.fetch_article_content(URL, lambda step: None, {**PRIORITY, 'tikhubApiKey': 'secret-wechat-key'}))
    assert 'TikHub' in str(caught.value) and 'Content Downloader' in str(caught.value)
    assert 'secret-wechat-key' not in str(caught.value)


def test_image_only_article_is_valid_with_caption_fallback(monkeypatch):
    mock_page(monkeypatch, '<h1 id="activity-name">图片文章</h1><div id="js_content"><img data-src="https://mmbiz.qpic.cn/a.png"></div>')
    monkeypatch.setattr(article, 'fetch_wechat_article', fail_if_tikhub)
    result = asyncio.run(article.fetch_article_content(URL, lambda step: None, PRIORITY))
    assert result['title'] == '图片文章'
    assert 'https://mmbiz.qpic.cn/a.png' in result['html_content']
    assert result['cover_image_url'] == 'https://mmbiz.qpic.cn/a.png'


def test_direct_metadata_fallbacks_handle_single_quoted_timestamp(monkeypatch):
    mock_page(monkeypatch, "<meta property='og:title' content='文章'><script>var ct = '1720000000';</script><span class='rich_media_meta_text'>公众号名称</span><div id='js_content'><p>实际正文内容。</p></div>")
    monkeypatch.setattr(article, 'fetch_wechat_article', fail_if_tikhub)
    result = asyncio.run(article.fetch_article_content(URL, lambda step: None, PRIORITY))
    assert result['publish_time'] == '1720000000' and result['account_name'] == '公众号名称'
