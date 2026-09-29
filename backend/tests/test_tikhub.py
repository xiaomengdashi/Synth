import httpx
import pytest

from app.services.fetchers import tikhub
from app.services.fetchers.tikhub import (
    TikHubError,
    TikHubNotConfiguredError,
    fetch_tikhub_tweet,
    fetch_tweet_detail,
    normalize_flat_tweet_data,
    normalize_tikhub_tweet_result,
    resolve_tikhub_token,
    _unwrap_tweet_result,
)


def _flat_tweet_data(**overrides) -> dict:
    """TikHub 线上实测的扁平化推文结构（2026-09 抓包）。"""
    data = {
        "id": "2098945504289669481",
        "text": "https://t.co/1Zp3Skkv39",
        "display_text": "x.com/i/article/2098…",
        "lang": "zxx",
        "status": "active",
        "likes": 623,
        "retweets": 113,
        "replies": 6,
        "views": "195413",
        "created_at": "Sun Sep 13 01:22:59 +0000 2026",
        "author": {
            "rest_id": "1477948736156454913",
            "name": "Dongxi 东锡 NLP",
            "screen_name": "dongxi_nlp",
            "image": "https://pbs.twimg.com/profile_images/2089337602436444161/F8lWtWJZ_normal.jpg",
        },
        "media": None,
        "urls": [
            {
                "display_url": "x.com/i/article/2098…",
                "expanded_url": "https://x.com/i/article/2098863329817051136",
                "url": "https://t.co/1Zp3Skkv39",
            }
        ],
        "entities": {
            "urls": [
                {
                    "expanded_url": "https://x.com/i/article/2098863329817051136",
                    "url": "https://t.co/1Zp3Skkv39",
                }
            ]
        },
        "article": {
            "title": "LLM 为什么缓存 K 和 V，却通常不缓存 Q？",
            "preview_text": "你把一份很长的项目文档交给 AI，让它帮你总结。",
            "full_text": "你把一份很长的项目文档交给 AI，让它帮你总结。\n\n回答开始出现，一个 token 接着一个 token 生成。",
            "cover_media": "https://pbs.twimg.com/media/HSCpc8MboAAmzdC.jpg",
        },
    }
    data.update(overrides)
    return data


def _tweet_result(
    *,
    text: str = "普通推文正文",
    note_text: str | None = None,
    article: dict | None = None,
    urls: list[dict] | None = None,
    media: list[dict] | None = None,
) -> dict:
    legacy = {
        "full_text": text,
        "favorite_count": 12,
        "retweet_count": 3,
        "reply_count": 4,
        "created_at": "Wed Sep 23 08:00:00 +0000 2026",
        "entities": {"urls": urls or []},
    }
    if media:
        legacy["extended_entities"] = {"media": media}
    result = {
        "__typename": "Tweet",
        "rest_id": "1799000000000000001",
        "core": {
            "user_results": {
                "result": {
                    "legacy": {
                        "name": "测试作者",
                        "screen_name": "test_author",
                        "profile_image_url_https": "https://pbs.twimg.com/profile_images/1/test_normal.jpg",
                    }
                }
            }
        },
        "legacy": legacy,
    }
    if note_text is not None:
        result["note_tweet"] = {"note_tweet_results": {"result": {"text": note_text}}}
    if article is not None:
        result["article"] = article
    return result


def _tikhub_payload(result: dict) -> dict:
    return {"code": 200, "data": {"tweet_result_by_rest_id": {"result": result}}}


class TestResolveToken:
    def test_reads_token_from_dict_config(self):
        assert resolve_tikhub_token({"tikhubApiKey": " dict-token "}) == "dict-token"

    def test_reads_token_from_object_config(self):
        class Config:
            tikhubApiKey = "object-token"

        assert resolve_tikhub_token(Config()) == "object-token"

    def test_falls_back_to_env_variable(self, monkeypatch):
        monkeypatch.delenv("TIKHUB_API_TOKEN", raising=False)
        monkeypatch.setenv("TIKHUB_API_TOKEN", "env-token")
        assert resolve_tikhub_token({}) == "env-token"
        assert resolve_tikhub_token(None) == "env-token"

    def test_config_takes_priority_over_env(self, monkeypatch):
        monkeypatch.setenv("TIKHUB_API_TOKEN", "env-token")
        assert resolve_tikhub_token({"tikhubApiKey": "dict-token"}) == "dict-token"

    def test_raises_when_not_configured(self, monkeypatch):
        monkeypatch.delenv("TIKHUB_API_TOKEN", raising=False)
        with pytest.raises(TikHubNotConfiguredError):
            resolve_tikhub_token({})


class TestFetchTweetDetail:
    def _patch_get(self, monkeypatch, response: httpx.Response):
        calls = {}

        def fake_get(url, **kwargs):
            calls["url"] = url
            calls["kwargs"] = kwargs
            return response

        monkeypatch.setattr(tikhub.httpx, "get", fake_get)
        return calls

    def test_success_returns_data(self, monkeypatch):
        self._patch_get(monkeypatch, httpx.Response(200, json=_tikhub_payload(_tweet_result())))
        data = fetch_tweet_detail("123", "token")
        assert data["tweet_result_by_rest_id"]["result"]["rest_id"] == "1799000000000000001"

    def test_request_includes_bearer_token_and_tweet_id(self, monkeypatch):
        calls = self._patch_get(monkeypatch, httpx.Response(200, json=_tikhub_payload(_tweet_result())))
        fetch_tweet_detail("123456", "secret-token")
        assert calls["url"] == f"{tikhub.TIKHUB_API_BASE}{tikhub.TWEET_DETAIL_PATH}"
        assert calls["kwargs"]["params"] == {"tweet_id": "123456"}
        assert calls["kwargs"]["headers"]["Authorization"] == "Bearer secret-token"

    @pytest.mark.parametrize(
        "status,fragment",
        [
            (401, "401"),
            (402, "402"),
            (404, "404"),
            (429, "429"),
            (500, "500"),
        ],
    )
    def test_http_errors_are_wrapped(self, monkeypatch, status, fragment):
        self._patch_get(monkeypatch, httpx.Response(status, json={}))
        with pytest.raises(TikHubError, match=fragment):
            fetch_tweet_detail("123", "token")

    def test_payload_error_code_is_wrapped(self, monkeypatch):
        self._patch_get(
            monkeypatch,
            httpx.Response(200, json={"code": 404, "message": "tweet not found"}),
        )
        with pytest.raises(TikHubError, match="tweet not found"):
            fetch_tweet_detail("123", "token")

    def test_network_error_is_wrapped(self, monkeypatch):
        def fake_get(url, **kwargs):
            raise httpx.ConnectError("connection refused")

        monkeypatch.setattr(tikhub.httpx, "get", fake_get)
        with pytest.raises(TikHubError, match="TikHub 请求失败"):
            fetch_tweet_detail("123", "token")


class TestUnwrapTweetResult:
    def test_extracts_plain_result(self):
        result = _unwrap_tweet_result(_tikhub_payload(_tweet_result())["data"])
        assert result["rest_id"] == "1799000000000000001"

    def test_unwraps_visibility_wrapper(self):
        data = {
            "tweet_result_by_rest_id": {
                "result": {
                    "__typename": "TweetWithVisibility",
                    "tweet": _tweet_result(),
                }
            }
        }
        assert _unwrap_tweet_result(data)["rest_id"] == "1799000000000000001"

    def test_prefers_retweeted_original(self):
        original = _tweet_result(text="被转推的原文")
        data = {
            "tweet_result_by_rest_id": {
                "result": _tweet_result(
                    text="RT @test_author: 被转推的原文",
                )
            }
        }
        data["tweet_result_by_rest_id"]["result"]["legacy"]["retweeted_status_result"] = {"result": original}
        assert _unwrap_tweet_result(data)["legacy"]["full_text"] == "被转推的原文"

    def test_returns_none_for_missing_result(self):
        assert _unwrap_tweet_result({"tweet_result_by_rest_id": {}}) is None
        assert _unwrap_tweet_result({}) is None

    def test_returns_none_for_tombstone(self):
        data = {"tweet_result_by_rest_id": {"result": {"__typename": "TweetTombstone"}}}
        assert _unwrap_tweet_result(data) is None


class TestNormalizeTweetResult:
    def test_normalizes_basic_fields(self):
        payload = normalize_tikhub_tweet_result(_tweet_result())
        assert payload["author_name"] == "测试作者"
        assert payload["author_handle"] == "test_author"
        assert payload["tweet_text"] == "普通推文正文"
        assert payload["likes"] == 12
        assert payload["tweet_url"] == "https://x.com/test_author/status/1799000000000000001"
        assert payload["author_avatar_url"].endswith("_400x400.jpg")

    def test_prefers_note_tweet_full_text(self):
        result = _tweet_result(text="被截断的文本…", note_text="这是超过 280 字符的完整长推文正文")
        assert normalize_tikhub_tweet_result(result)["tweet_text"] == "这是超过 280 字符的完整长推文正文"

    def test_collects_media_urls(self):
        result = _tweet_result(
            media=[{"media_url_https": "https://pbs.twimg.com/media/a.jpg"}, {"media_url_https": "https://pbs.twimg.com/media/b.jpg"}]
        )
        payload = normalize_tikhub_tweet_result(result)
        assert payload["media_urls"] == [
            "https://pbs.twimg.com/media/a.jpg",
            "https://pbs.twimg.com/media/b.jpg",
        ]
        assert payload["cover_image_url"] == "https://pbs.twimg.com/media/a.jpg"

    def test_external_urls_skip_x_internal_links(self):
        result = _tweet_result(
            text="看这篇文章 https://t.co/abc 和长文 https://x.com/i/article/2077719644425670656",
            urls=[{"expanded_url": "https://blog.example.com/post?utm=x"}],
        )
        payload = normalize_tikhub_tweet_result(result)
        assert payload["external_urls"] == ["https://blog.example.com/post?utm=x"]

    def test_article_preview_drives_title_and_cover(self):
        result = _tweet_result(
            article={
                "preview": {
                    "title": "X 长文标题",
                    "excerpt": "长文摘要",
                },
                "article_results": {
                    "result": {
                        "title": "X 长文标题",
                        "cover_media": {"original_img_url": "https://pbs.twimg.com/media/cover.jpg"},
                    }
                },
            }
        )
        payload = normalize_tikhub_tweet_result(result)
        assert payload["title"] == "X 长文标题"
        assert payload["article_preview"]["preview_text"] == "长文摘要"
        assert payload["cover_image_url"] == "https://pbs.twimg.com/media/cover.jpg"


class TestNormalizeFlatTweetData:
    def test_normalizes_basic_fields(self):
        payload = normalize_flat_tweet_data(_flat_tweet_data())
        assert payload["author_name"] == "Dongxi 东锡 NLP"
        assert payload["author_handle"] == "dongxi_nlp"
        assert payload["author_avatar_url"].endswith("_400x400.jpg")
        assert payload["likes"] == 623
        assert payload["tweet_url"] == "https://x.com/dongxi_nlp/status/2098945504289669481"
        assert payload["created_at"] == "Sun Sep 13 01:22:59 +0000 2026"

    def test_article_drives_title_and_cover(self):
        payload = normalize_flat_tweet_data(_flat_tweet_data())
        assert payload["title"] == "LLM 为什么缓存 K 和 V，却通常不缓存 Q？"
        assert payload["cover_image_url"] == "https://pbs.twimg.com/media/HSCpc8MboAAmzdC.jpg"
        assert payload["article_preview"]["preview_text"].startswith("你把一份很长的项目文档")

    def test_article_link_is_not_treated_as_external(self):
        payload = normalize_flat_tweet_data(_flat_tweet_data())
        assert payload["external_urls"] == []

    def test_external_url_from_text_is_kept(self):
        payload = normalize_flat_tweet_data(
            _flat_tweet_data(
                article=None,
                text="看看这篇文章 https://t.co/abc",
                urls=[{"expanded_url": "https://blog.example.com/kv-cache", "url": "https://t.co/abc"}],
            )
        )
        assert payload["external_urls"] == ["https://blog.example.com/kv-cache"]
        assert payload["title"] == "Dongxi 东锡 NLP 的推文"

    def test_media_list_extraction(self):
        payload = normalize_flat_tweet_data(
            _flat_tweet_data(article=None, media=[{"type": "photo", "url": "https://pbs.twimg.com/media/x.jpg"}])
        )
        assert payload["media_urls"] == ["https://pbs.twimg.com/media/x.jpg"]
        assert payload["cover_image_url"] == "https://pbs.twimg.com/media/x.jpg"


class TestFetchTikhubTweet:
    def test_flat_data_returns_article_text(self, monkeypatch):
        monkeypatch.setattr(tikhub, "fetch_tweet_detail", lambda tweet_id, token: _flat_tweet_data())
        data = fetch_tikhub_tweet("https://x.com/dongxi_nlp/status/2098945504289669481", {"tikhubApiKey": "tok"})
        assert data["article_result"] is None
        assert data["article_text"]["title"] == "LLM 为什么缓存 K 和 V，却通常不缓存 Q？"
        assert data["article_text"]["full_text"].startswith("你把一份很长的项目文档")
        assert data["article_text"]["cover_image_url"] == "https://pbs.twimg.com/media/HSCpc8MboAAmzdC.jpg"
        assert data["payload"]["title"] == "LLM 为什么缓存 K 和 V，却通常不缓存 Q？"

    def test_flat_data_without_article(self, monkeypatch):
        monkeypatch.setattr(tikhub, "fetch_tweet_detail", lambda tweet_id, token: _flat_tweet_data(article=None))
        data = fetch_tikhub_tweet("2098945504289669481", {"tikhubApiKey": "tok"})
        assert data["article_text"] is None
        assert data["payload"]["title"] == "Dongxi 东锡 NLP 的推文"

    def test_extracts_tweet_id_from_url_and_returns_article(self, monkeypatch):
        article_result = {
            "title": "X 长文标题",
            "content_state": {"blocks": [{"type": "unstyled", "text": "正文"}], "entityMap": {}},
        }
        result = _tweet_result(
            article={"article_results": {"result": article_result}},
        )
        monkeypatch.setattr(tikhub, "fetch_tweet_detail", lambda tweet_id, token: _tikhub_payload(result)["data"])
        data = fetch_tikhub_tweet("https://x.com/someone/status/1799000000000000001", {"tikhubApiKey": "tok"})
        assert data["article_result"] == article_result
        assert data["payload"]["title"] == "X 长文标题"

    def test_article_without_content_state_is_ignored(self, monkeypatch):
        result = _tweet_result(article={"article_results": {"result": {"title": "仅预览"}}})
        monkeypatch.setattr(tikhub, "fetch_tweet_detail", lambda tweet_id, token: _tikhub_payload(result)["data"])
        data = fetch_tikhub_tweet("1799000000000000001", {"tikhubApiKey": "tok"})
        assert data["article_result"] is None
        assert data["payload"]["tweet_text"] == "普通推文正文"

    def test_rejects_non_tweet_url(self):
        with pytest.raises(TikHubError, match="无法从链接中提取推文 ID"):
            fetch_tikhub_tweet("https://example.com/nope", {"tikhubApiKey": "tok"})

    def test_requires_token(self, monkeypatch):
        monkeypatch.delenv("TIKHUB_API_TOKEN", raising=False)
        with pytest.raises(TikHubNotConfiguredError):
            fetch_tikhub_tweet("https://x.com/someone/status/1799000000000000001", {})
