from app.services.fetchers.article import parse_article_html


def test_parse_saved_wechat_html_preserves_title_cover_and_body():
    html = """
    <html>
      <head>
        <meta property="og:title" content="C++ 设计模式全解析" />
        <meta property="og:image" content="https://example.com/cover.jpg" />
      </head>
      <body>
        <div id="activity-name">备用标题</div>
        <div id="js_content">
          <p>第一段正文。</p>
          <p><img data-src="https://example.com/article.jpg" /></p>
          <p>第二段正文，内容足够长用于验证导入。</p>
        </div>
      </body>
    </html>
    """

    result = parse_article_html("https://mp.weixin.qq.com/s/imported", html)

    assert result["title"] == "C++ 设计模式全解析"
    assert result["cover_image_url"] == "https://example.com/cover.jpg"
    assert "第一段正文" in result["html_content"]
    assert 'src="https://example.com/article.jpg"' in result["html_content"]


def test_parse_saved_html_rejects_missing_wechat_body():
    try:
        parse_article_html("https://mp.weixin.qq.com/s/imported", "<html><body>验证页</body></html>")
    except ValueError as exc:
        assert "js_content" in str(exc)
    else:
        raise AssertionError("expected saved WeChat HTML without #js_content to be rejected")
