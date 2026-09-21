from app.services.fetchers.twitter_article_rich import render_twitter_article_result


def test_render_twitter_article_preserves_blocks_and_inline_images():
    article_result = {
        "title": "测试长文标题",
        "media_entities": [
            {
                "media_id": "42",
                "media_info": {
                    "original_img_url": "https://pbs.twimg.com/media/test.jpg",
                },
            },
            {
                "media_id": "43",
                "media_info": {
                    "original_img_url": "https://pbs.twimg.com/media/test-2.jpg",
                },
            },
        ],
        "content_state": {
            "blocks": [
                {"type": "unstyled", "text": "第一段"},
                {"type": "atomic", "text": "", "entityRanges": [{"key": 0}]},
                {"type": "header-two", "text": "第二节"},
            ],
            "entityMap": [
                {
                    "key": "0",
                    "value": {
                        "type": "MEDIA",
                        "data": {"mediaItems": [{"mediaId": "42"}, {"mediaId": "43"}]},
                    },
                }
            ],
        },
    }

    result = render_twitter_article_result(article_result)

    assert result["title"] == "测试长文标题"
    assert result["media_urls"] == [
        "https://pbs.twimg.com/media/test.jpg",
        "https://pbs.twimg.com/media/test-2.jpg",
    ]
    assert result["content_md"] == (
        "第一段\n\n"
        "![X 文章配图](https://pbs.twimg.com/media/test.jpg)\n\n"
        "![X 文章配图](https://pbs.twimg.com/media/test-2.jpg)\n\n"
        "## 第二节"
    )
