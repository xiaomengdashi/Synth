from app.services.fetchers.x_twitter_cli import extract_x_article_id, parse_twitter_article_markdown


def test_extract_x_article_id_from_tweet_text():
    text = "这是一条长文 https://x.com/i/article/2077719644425670656"

    assert extract_x_article_id(text) == "2077719644425670656"


def test_parse_twitter_article_markdown_extracts_metadata_and_body():
    markdown = """# 一篇 X 长文

- Author: @author
- Published: Thu Jul 16 11:53:26 +0000 2026
- URL: https://x.com/author/status/123
- Likes: 10

这是正文第一段。

## 第二节

这是正文第二段。
"""

    result = parse_twitter_article_markdown(markdown)

    assert result["title"] == "一篇 X 长文"
    assert result["original_url"] == "https://x.com/author/status/123"
    assert result["content_md"] == "这是正文第一段。\n\n## 第二节\n\n这是正文第二段。"
