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


def test_render_twitter_article_applies_inline_styles_and_links():
    article_result = {
        "title": "行内样式",
        "content_state": {
            "blocks": [
                {
                    "type": "unstyled",
                    "text": "普通加粗斜体删除线下划线代码普通",
                    "inlineStyleRanges": [
                        {"offset": 2, "length": 2, "style": "BOLD"},
                        {"offset": 4, "length": 2, "style": "ITALIC"},
                        {"offset": 6, "length": 3, "style": "STRIKETHROUGH"},
                        {"offset": 9, "length": 3, "style": "UNDERLINE"},
                        {"offset": 12, "length": 2, "style": "CODE"},
                    ],
                },
                {
                    "type": "header-two",
                    "text": "深入解读",
                    "entityRanges": [{"offset": 0, "length": 4, "key": 1}],
                },
                {
                    "type": "blockquote",
                    "text": "看这篇好文",
                    "entityRanges": [{"offset": 2, "length": 4, "key": 1}],
                    "inlineStyleRanges": [
                        {"offset": 2, "length": 2, "style": "BOLD"},
                        {"offset": 4, "length": 2, "style": "ITALIC"},
                    ],
                },
            ],
            "entityMap": [
                {"key": "1", "value": {"type": "LINK", "data": {"url": "https://example.com/docs"}}},
            ],
        },
    }

    result = render_twitter_article_result(article_result)

    assert result["content_md"] == (
        "普通**加粗***斜体*~~删除线~~<u>下划线</u>`代码`普通\n\n"
        "## [深入解读](https://example.com/docs)\n\n"
        "> 看这[**篇好***文*](https://example.com/docs)"
    )


def test_render_inline_styles_merge_overlaps_and_trim_boundary_whitespace():
    article_result = {
        "title": "重叠样式",
        "content_state": {
            "blocks": [
                {
                    "type": "unstyled",
                    "text": "重点 粗斜体 段落结束",
                    "inlineStyleRanges": [
                        {"offset": 3, "length": 4, "style": "BOLD"},
                        {"offset": 3, "length": 3, "style": "ITALIC"},
                    ],
                },
                {
                    "type": "unstyled",
                    "text": "一条含空格 URL 的 引用",
                    "entityRanges": [{"offset": 1, "length": 11, "key": "link"}],
                },
            ],
            "entityMap": [
                {"key": "link", "value": {"type": "LINK", "data": {"url": "https://example.com/a b"}}},
            ],
        },
    }

    result = render_twitter_article_result(article_result)

    assert result["content_md"] == (
        "重点 ***粗斜体*** 段落结束\n\n"
        "一[条含空格 URL 的 ](<https://example.com/a b>)引用"
    )


def test_render_inline_styles_ignore_invalid_and_out_of_range_ranges():
    article_result = {
        "title": "异常数据",
        "content_state": {
            "blocks": [
                {
                    "type": "unstyled",
                    "text": "保持原样",
                    "inlineStyleRanges": [
                        {"offset": "x", "length": 2, "style": "BOLD"},
                        {"offset": 100, "length": 5, "style": "BOLD"},
                        {"offset": 0, "length": -3, "style": "ITALIC"},
                        {"offset": 0, "length": 2, "style": "UNKNOWN_STYLE"},
                    ],
                    "entityRanges": [
                        {"offset": 0, "length": 4, "key": 9},  # entityMap 中不存在的 key
                        {"offset": 0, "length": 4, "key": 2},  # 非 LINK 实体
                    ],
                },
            ],
            "entityMap": [
                {"key": "2", "value": {"type": "MEDIA", "data": {}}},
            ],
        },
    }

    result = render_twitter_article_result(article_result)

    assert result["content_md"] == "保持原样"
