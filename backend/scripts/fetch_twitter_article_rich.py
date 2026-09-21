#!/usr/bin/env python3
"""Fetch an X Article's rich Draft.js content using the local twitter-cli session."""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from twitter_cli.auth import get_cookies  # noqa: E402
from twitter_cli.client import TwitterClient  # noqa: E402
from twitter_cli.parser import _deep_get  # noqa: E402

from app.services.fetchers.twitter_article_rich import render_twitter_article_result  # noqa: E402


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: fetch_twitter_article_rich.py TWEET_ID")

    cookies = get_cookies()
    client = TwitterClient(
        cookies["auth_token"],
        cookies["ct0"],
        cookie_string=cookies.get("cookie_string"),
    )
    data = client._graphql_get(
        "TweetResultByRestId",
        variables={
            "tweetId": sys.argv[1],
            "withCommunity": False,
            "includePromotedContent": False,
            "withVoice": False,
        },
        features={
            "longform_notetweets_consumption_enabled": True,
            "responsive_web_twitter_article_tweet_consumption_enabled": True,
            "longform_notetweets_rich_text_read_enabled": True,
            "longform_notetweets_inline_media_enabled": True,
            "articles_preview_enabled": True,
            "responsive_web_graphql_exclude_directive_enabled": True,
            "verified_phone_label_enabled": False,
        },
        field_toggles={
            "withArticleRichContentState": True,
            "withArticlePlainText": True,
        },
    )
    article_result = _deep_get(data, "data", "tweetResult", "result", "article", "article_results", "result")
    if not isinstance(article_result, dict):
        raise RuntimeError("twitter-cli 未返回 X 长文富文本数据。")

    print(json.dumps(render_twitter_article_result(article_result), ensure_ascii=False))


if __name__ == "__main__":
    main()
