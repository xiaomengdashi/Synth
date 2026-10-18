import pytest

from app.services.fetchers.article import parse_article_html


@pytest.mark.parametrize('url,root', [
    ('https://blog.csdn.net/u/article/details/123', 'id="article_content"'),
    ('https://www.cnblogs.com/u/p/123.html', 'id="cnblogs_post_body"'),
    ('https://example.com/post', 'id="content"'),
])
def test_article_body_and_relative_media_are_preserved(url, root):
    result = parse_article_html(url, f'<html><title>文章</title><meta name="author" content="作者"><article {root}><h2>正文</h2><p>真实文章内容。</p><img src="/cover.png"><a href="./next">后续内容</a></article></html>')
    assert '真实文章内容' in result['extracted_md']
    assert result['account_name'] == '作者'
    assert 'src="https://' in result['html_content']


def test_error_page_is_not_saved_as_a_placeholder_article():
    with pytest.raises(ValueError, match='正文'):
        parse_article_html('https://example.com/not-found', '<html><title>404</title><body>Not found</body></html>')
