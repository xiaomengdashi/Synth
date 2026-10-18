import asyncio
import json

import httpx
import pytest
from bs4 import BeautifulSoup

URL = 'https://x.com/author/status/123456789'
ARTICLE = {
    'title': '长文 <标题>',
    'content_state': {
        'blocks': [
            {'type': 'unstyled', 'text': '😀加粗<script>', 'inlineStyleRanges': [{'offset': 2, 'length': 2, 'style': 'BOLD'}]},
            {'type': 'header-two', 'text': '章节'},
            {'type': 'unordered-list-item', 'text': '第一项', 'depth': 0},
            {'type': 'unordered-list-item', 'text': '子项', 'depth': 1},
            {'type': 'atomic', 'entityRanges': [{'key': 0, 'offset': 0, 'length': 1}]},
            {'type': 'atomic', 'entityRanges': [{'key': 1, 'offset': 0, 'length': 1}]},
            {'type': 'unstyled', 'text': '最后一段'},
        ],
        'entityMap': [
            {'key': '0', 'value': {'type': 'MEDIA', 'data': {'mediaItems': [{'mediaId': 'photo'}]}}},
            {'key': '1', 'value': {'type': 'MEDIA', 'data': {'mediaItems': [{'mediaId': 'gif'}]}}},
        ],
    },
    'media_entities': [
        {'media_id': 'photo', 'media_info': {'__typename': 'ApiImage', 'original_img_url': 'https://pbs.twimg.com/media/photo.jpg'}},
        {'media_id': 'gif', 'media_info': {'__typename': 'ApiGif', 'preview_image': {'original_img_url': 'https://pbs.twimg.com/media/poster.jpg'}, 'variants': [
            {'content_type': 'video/mp4', 'bit_rate': 100, 'url': 'https://video.twimg.com/clip.mp4'},
        ]}},
    ],
    'cover_media': {'media_info': {'original_img_url': 'https://pbs.twimg.com/media/cover.jpg'}},
}
TWEET = {'rest_id': '123456789', 'legacy': {'full_text': 'https://t.co/article'},
         'core': {'user_results': {'result': {'legacy': {'name': '作者', 'screen_name': 'author'}}}},
         'article': {'article_results': {'result': ARTICLE}}}


def test_replaces_saved_x_method_in_place_without_changing_wechat():
    from app.services.fetch_priorities import resolve_priorities
    result = resolve_priorities({'fetchProviderPriorities': json.dumps({
        'x': ['content_downloader', 'twitter_cli', 'tikhub'], 'wechat': ['content_downloader', 'tikhub'],
    })})
    assert result['x'] == ['x_graphql', 'twitter_cli', 'tikhub']
    assert result['wechat'] == ['content_downloader', 'tikhub']


def test_graphql_requests_full_article_json_using_saved_credentials():
    from app.services.fetchers.x_graphql import fetch_x_via_graphql
    def handle(request):
        assert request.url.host == 'x.com'
        assert request.url.path.endswith('/TweetResultByRestId')
        assert json.loads(request.url.params['fieldToggles']) == {'withArticleRichContentState': True, 'withArticlePlainText': True}
        assert json.loads(request.url.params['variables'])['tweetId'] == '123456789'
        assert request.headers['x-csrf-token'] == 'test-csrf'
        return httpx.Response(200, json={'data': {'tweetResult': {'result': TWEET}}})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            return await fetch_x_via_graphql(URL, lambda _: None, {'twitterAuthToken': 'test-auth', 'twitterCt0': 'test-csrf'}, client=client)
    result = asyncio.run(run())
    assert result['article_result'] == ARTICLE
    assert result['payload']['title'] == '长文 <标题>'


@pytest.mark.parametrize('changes', [
    {'rest_id': '999'}, {'article': {'article_results': {'result': {'title': '只有标题'}}}},
])
def test_wrong_tweet_or_missing_article_body_is_not_success(changes):
    from app.services.fetchers.x_graphql import fetch_x_via_graphql
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={'data': {'tweetResult': {'result': {**TWEET, **changes}}}}))) as client:
            return await fetch_x_via_graphql(URL, lambda _: None, {'twitterAuthToken': 'secret-auth', 'twitterCt0': 'secret-csrf'}, client=client)
    with pytest.raises(RuntimeError):
        asyncio.run(run())


def test_draft_article_downloads_media_for_library_without_a_second_html_entry(tmp_path):
    from app.services.fetchers.x_graphql_article import build_graphql_article
    def handle(request):
        assert 'cookie' not in request.headers and 'authorization' not in request.headers
        video = request.url.host == 'video.twimg.com'
        return httpx.Response(200, content=b'video' if video else str(request.url).encode(), headers={'content-type': 'video/mp4' if video else 'image/jpeg'})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            return await build_graphql_article(ARTICLE, {'author_name': '作者'}, URL, lambda _: None, client=client, media_dir=tmp_path)
    result = asyncio.run(run())
    soup = BeautifulSoup(result['body_html'], 'html.parser')
    assert soup.strong.text == '加粗'  # Draft offsets are UTF-16 units, not Python code points.
    assert soup.find('script') is None and '<script>' in soup.get_text()
    assert soup.h2.text == '章节' and soup.select_one('ul > li > ul > li').text == '子项'
    assert soup.video.has_attr('loop') and soup.video.has_attr('muted')
    assert soup.img['src'].startswith('/media/x/123456789/media/')
    assert 'video.twimg.com' not in result['body_html']
    assert result['body_html'].index('<img') < result['body_html'].index('<video') < result['body_html'].index('最后一段')
    for node in soup.select('[src], [poster]'):
        for attr in ('src', 'poster'):
            if node.get(attr):
                assert (tmp_path / node[attr].removeprefix('/media/')).is_file()
    assert 'archive_url' not in result
    assert not (tmp_path / 'x/123456789/article.html').exists()
    assert not (tmp_path / 'x/123456789/metadata.json').exists()
    assert result['status'] == 'complete'


def test_failed_media_is_explicitly_partial_without_remote_hotlinks(tmp_path):
    from app.services.fetchers.x_graphql_article import build_graphql_article
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(403))) as client:
            return await build_graphql_article(ARTICLE, {}, URL, lambda _: None, client=client, media_dir=tmp_path)
    result = asyncio.run(run())
    assert result['status'] == 'partial' and result['warnings']
    assert 'https://' not in result['body_html']
    assert '最后一段' in result['body_html']


def test_media_redirect_cannot_access_local_network(tmp_path):
    from app.services.fetchers.x_graphql_article import build_graphql_article
    visited = []
    def handle(request):
        visited.append(request.url.host)
        return httpx.Response(302, headers={'location': 'http://127.0.0.1/private'})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            return await build_graphql_article(ARTICLE, {}, URL, lambda _: None, client=client, media_dir=tmp_path)
    result = asyncio.run(run())
    assert '127.0.0.1' not in visited and result['status'] == 'partial'


@pytest.mark.parametrize('status', [401, 403, 429])
def test_authentication_errors_do_not_publish_upstream_cookie_values(status):
    from app.services.fetchers.x_graphql import fetch_x_via_graphql
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(status, text='secret-auth / secret-csrf'))) as client:
            return await fetch_x_via_graphql(URL, lambda _: None, {'twitterAuthToken': 'secret-auth', 'twitterCt0': 'secret-csrf'}, client=client)
    with pytest.raises(RuntimeError) as caught:
        asyncio.run(run())
    assert 'secret-auth' not in str(caught.value) and 'secret-csrf' not in str(caught.value)


def test_missing_credentials_does_not_fetch_or_discover_browser_cookies(monkeypatch):
    from app.services.fetchers import x_graphql
    monkeypatch.setattr(x_graphql, 'resolve_twitter_cli', lambda _: {'auth': '', 'csrf': ''})
    with pytest.raises(RuntimeError, match='登录态'):
        asyncio.run(x_graphql.fetch_x_via_graphql(URL, lambda _: None, {}))


def test_stale_query_id_refreshes_from_public_x_bundle_without_auth_leak():
    from app.services.fetchers.x_graphql import fetch_x_via_graphql
    calls = []
    def handle(request):
        calls.append(request.url.path)
        if request.url.path == '/':
            assert 'cookie' not in request.headers and 'authorization' not in request.headers
            return httpx.Response(200, text='<script src="https://abs.twimg.com/responsive-web/client-web/main.test123.js"></script>')
        if request.url.host == 'abs.twimg.com':
            assert 'cookie' not in request.headers and 'authorization' not in request.headers
            return httpx.Response(200, text='queryId:"fresh-operation",operationName:"TweetResultByRestId"')
        if 'fresh-operation' not in request.url.path:
            return httpx.Response(404)
        return httpx.Response(200, json={'data': {'tweetResult': {'result': TWEET}}})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            return await fetch_x_via_graphql(URL, lambda _: None, {'twitterAuthToken': 'secret-auth', 'twitterCt0': 'secret-csrf'}, client=client)
    assert asyncio.run(run())['article_result']['title'] == '长文 <标题>'
    assert calls[-1] == '/i/api/graphql/fresh-operation/TweetResultByRestId'
