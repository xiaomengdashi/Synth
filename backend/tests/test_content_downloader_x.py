"""Exercise provider normalization, timeout cleanup and priority fallback without live APIs."""
import asyncio
import json

import pytest

URL = 'https://x.com/author/status/123456789'
INFO = {
    'id': '123456789', 'display_id': '123456789', 'extractor_key': 'Twitter',
    'title': '作者 - 正文标题', 'description': '完整推文正文\n第二行',
    'uploader': '作者', 'uploader_id': 'author', 'timestamp': 1720000000,
    'thumbnail': 'https://pbs.twimg.com/media/photo.jpg',
    'thumbnails': [{'url': 'https://pbs.twimg.com/media/photo.jpg'}],
    'formats': [], 'like_count': 12, 'repost_count': 3, 'comment_count': 1,
}


def test_ytdlp_metadata_becomes_existing_reader_payload(monkeypatch):
    from app.services.fetchers import content_downloader_x as downloader
    class Process:
        returncode = 0
        async def communicate(self):
            return json.dumps(INFO).encode(), b''
    async def spawn(*args, **kwargs):
        assert args[-1] == URL
        assert args[-2] == '--'
        return Process()
    monkeypatch.setattr(downloader.asyncio, 'create_subprocess_exec', spawn)
    result = asyncio.run(downloader.fetch_content_downloader_tweet(URL))
    payload = result['payload']
    assert payload['tweet_text'] == '完整推文正文\n第二行'
    assert payload['author_name'] == '作者'
    assert payload['author_handle'] == 'author'
    assert payload['tweet_url'] == URL
    assert payload['media_items'][0]['type'] == 'photo'
    assert payload['created_at'].startswith('2024-07-03')
    assert result['article_result'] is None


@pytest.mark.parametrize('changes', [
    {'description': '', 'title': '只有标题'},
    {'description': '长文 https://x.com/i/article/999'},
    {'description': '被截断的内容…'},
    {'display_id': '987', 'id': '987'},
    {'extractor_key': 'Youtube'},
])
def test_empty_truncated_or_unrelated_metadata_is_not_success(changes):
    from app.services.fetchers.content_downloader_x import normalize_metadata
    with pytest.raises(RuntimeError):
        normalize_metadata({**INFO, **changes}, URL)


def test_timeout_kills_and_reaps_child(monkeypatch):
    from app.services.fetchers import content_downloader_x as downloader
    state = {'killed': False, 'reaped': False}
    class Process:
        returncode = None
        def kill(self):
            state['killed'] = True
        async def communicate(self):
            if state['killed']:
                state['reaped'] = True
                return b'', b''
            await asyncio.Event().wait()
    async def spawn(*args, **kwargs):
        return Process()
    monkeypatch.setattr(downloader.asyncio, 'create_subprocess_exec', spawn)
    monkeypatch.setattr(downloader, 'FETCH_TIMEOUT_SECONDS', 0.01)
    with pytest.raises(RuntimeError, match='超时'):
        asyncio.run(downloader.fetch_content_downloader_tweet(URL))
    assert state == {'killed': True, 'reaped': True}


def test_priority_first_success_skips_paid_provider(monkeypatch):
    from app.services.fetchers import x_providers
    async def download(url):
        return {'payload': {'tweet_text': '本地方式正文', 'media_items': []}}
    def paid(*args):
        raise AssertionError('成功后不应调用付费方式')
    monkeypatch.setattr(x_providers, 'fetch_content_downloader_tweet', download)
    result = asyncio.run(x_providers.fetch_x_with_priority(URL, {
        'fetchProviderPriorities': json.dumps({'x': ['content_downloader', 'tikhub']}),
    }, lambda step: None, tikhub_fetcher=paid))
    assert result['payload']['tweet_text'] == '本地方式正文'


def test_failed_first_provider_falls_back_and_reports_step(monkeypatch):
    from app.services.fetchers import x_providers
    async def download(url):
        raise RuntimeError('不支持的长文')
    def paid(*args):
        return {'payload': {'tweet_text': 'TikHub 完整正文', 'media_items': []}}
    monkeypatch.setattr(x_providers, 'fetch_content_downloader_tweet', download)
    steps = []
    result = asyncio.run(x_providers.fetch_x_with_priority(URL, {
        'fetchProviderPriorities': json.dumps({'x': ['content_downloader', 'tikhub']}),
    }, steps.append, tikhub_fetcher=paid))
    assert result['payload']['tweet_text'] == 'TikHub 完整正文'
    assert any('回退' in step and 'TikHub' in step for step in steps)


def test_unconfigured_tikhub_falls_back_without_key(monkeypatch):
    from app.services.fetchers import x_providers
    from app.services.fetchers.tikhub import TikHubNotConfiguredError
    async def download(url):
        return {'payload': {'tweet_text': '无需 Key 的正文', 'media_items': []}}
    def paid(*args):
        raise TikHubNotConfiguredError('未配置 Key')
    monkeypatch.setattr(x_providers, 'fetch_content_downloader_tweet', download)
    result = asyncio.run(x_providers.fetch_x_with_priority(URL, {}, lambda step: None, tikhub_fetcher=paid))
    assert result['payload']['tweet_text'] == '无需 Key 的正文'


def test_all_provider_failures_are_visible_without_leaking_key(monkeypatch):
    from app.services.fetchers import x_providers
    async def download(url):
        raise RuntimeError('downloader 不可用')
    def paid(*args):
        raise RuntimeError('凭据 secret-test-token 无效')
    monkeypatch.setattr(x_providers, 'fetch_content_downloader_tweet', download)
    with pytest.raises(RuntimeError) as caught:
        asyncio.run(x_providers.fetch_x_with_priority(URL, {'tikhubApiKey': 'secret-test-token'}, lambda step: None, tikhub_fetcher=paid))
    message = str(caught.value)
    assert 'TikHub' in message and 'Content Downloader' in message
    assert 'secret-test-token' not in message


def test_empty_provider_payload_triggers_next_provider(monkeypatch):
    from app.services.fetchers import x_providers
    async def download(url):
        return {'payload': {'tweet_text': '有效正文', 'media_items': []}}
    monkeypatch.setattr(x_providers, 'fetch_content_downloader_tweet', download)
    result = asyncio.run(x_providers.fetch_x_with_priority(URL, {}, lambda step: None,
        tikhub_fetcher=lambda *args: {'payload': {'tweet_text': '', 'media_items': []}}))
    assert result['payload']['tweet_text'] == '有效正文'


def test_extraction_keeps_tweet_metadata_instead_of_following_external_link(monkeypatch):
    from app.services.fetchers import content_downloader_runner as runner
    seen = {}
    class Downloader:
        def __init__(self, options):
            seen.update(options)
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def extract_info(self, url, download=True, process=True):
            if process or download:
                raise RuntimeError('模拟外链网页 404')
            return {**INFO, '_type': 'url', 'url': 'https://example.com/deep-article'}
    monkeypatch.setattr(runner, 'YoutubeDL', Downloader)
    info = runner.extract_metadata(URL)
    assert info['description'] == '完整推文正文\n第二行'
    assert seen['ignore_no_formats_error'] is True


def test_short_link_to_x_article_is_not_mistaken_for_full_body():
    from app.services.fetchers.content_downloader_x import normalize_metadata
    with pytest.raises(RuntimeError, match='完整'):
        normalize_metadata({**INFO, '_type': 'url', 'url': 'https://x.com/i/article/999',
                            'description': 'https://t.co/short'}, URL)


def test_expanded_external_link_is_passed_to_existing_article_fetch_flow():
    from app.services.fetchers.content_downloader_x import normalize_metadata
    result = normalize_metadata({**INFO, '_type': 'url', 'url': 'https://example.com/article',
                                 'description': '文章在这里 https://t.co/short'}, URL)
    assert result['payload']['external_urls'] == ['https://example.com/article']


def test_raw_mp4_formats_keep_video_instead_of_turning_poster_into_photo():
    from app.services.fetchers.content_downloader_x import normalize_metadata
    result = normalize_metadata({**INFO, 'formats': [
        {'url': 'https://video.twimg.com/vid/clip.mp4', 'tbr': 832},
        {'url': 'https://video.twimg.com/vid/low.mp4', 'tbr': 256},
    ]}, URL)
    assert result['payload']['media_items'] == [{'type': 'video', 'url': 'https://video.twimg.com/vid/clip.mp4',
                                               'poster': 'https://pbs.twimg.com/media/photo.jpg'}]


def test_unexpanded_shortlink_without_media_metadata_requires_fallback():
    from app.services.fetchers.content_downloader_x import normalize_metadata
    with pytest.raises(RuntimeError):
        normalize_metadata({**INFO, 'description': '配图正文 https://t.co/unknown', 'thumbnail': None,
                            'thumbnails': [], 'formats': []}, URL)
