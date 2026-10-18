"""X provider fallback and error redaction contracts."""
import asyncio
import json
import pytest
URL = "https://x.com/author/status/123456789"


def test_priority_first_success_skips_paid_provider(monkeypatch):
    from app.services.fetchers import x_providers
    async def download(url, *args):
        return {'payload': {'tweet_text': '本地方式正文', 'media_items': []}}
    def paid(*args):
        raise AssertionError('成功后不应调用付费方式')
    monkeypatch.setattr(x_providers, 'fetch_x_via_graphql', download)
    result = asyncio.run(x_providers.fetch_x_with_priority(URL, {
        'fetchProviderPriorities': json.dumps({'x': ['x_graphql', 'tikhub']}),
    }, lambda step: None, tikhub_fetcher=paid))
    assert result['payload']['tweet_text'] == '本地方式正文'


def test_failed_first_provider_falls_back_and_reports_step(monkeypatch):
    from app.services.fetchers import x_providers
    async def download(url, *args):
        raise RuntimeError('不支持的长文')
    def paid(*args):
        return {'payload': {'tweet_text': 'TikHub 完整正文', 'media_items': []}}
    monkeypatch.setattr(x_providers, 'fetch_x_via_graphql', download)
    steps = []
    result = asyncio.run(x_providers.fetch_x_with_priority(URL, {
        'fetchProviderPriorities': json.dumps({'x': ['x_graphql', 'tikhub']}),
    }, steps.append, tikhub_fetcher=paid))
    assert result['payload']['tweet_text'] == 'TikHub 完整正文'
    assert any('回退' in step and 'TikHub' in step for step in steps)


def test_unconfigured_tikhub_falls_back_without_key(monkeypatch):
    from app.services.fetchers import x_providers
    from app.services.fetchers.tikhub import TikHubNotConfiguredError
    async def download(url, *args):
        return {'payload': {'tweet_text': '无需 Key 的正文', 'media_items': []}}
    def paid(*args):
        raise TikHubNotConfiguredError('未配置 Key')
    monkeypatch.setattr(x_providers, 'fetch_x_via_graphql', download)
    result = asyncio.run(x_providers.fetch_x_with_priority(URL, {}, lambda step: None, tikhub_fetcher=paid))
    assert result['payload']['tweet_text'] == '无需 Key 的正文'


def test_all_provider_failures_are_visible_without_leaking_key(monkeypatch):
    from app.services.fetchers import x_providers
    async def download(url, *args):
        raise RuntimeError('downloader 不可用')
    def paid(*args):
        raise RuntimeError('凭据 secret-test-token 无效')
    monkeypatch.setattr(x_providers, 'fetch_x_via_graphql', download)
    with pytest.raises(RuntimeError) as caught:
        asyncio.run(x_providers.fetch_x_with_priority(URL, {'tikhubApiKey': 'secret-test-token'}, lambda step: None, tikhub_fetcher=paid))
    message = str(caught.value)
    assert 'TikHub' in message and 'X GraphQL' in message
    assert 'secret-test-token' not in message


def test_empty_provider_payload_triggers_next_provider(monkeypatch):
    from app.services.fetchers import x_providers
    async def download(url, *args):
        return {'payload': {'tweet_text': '有效正文', 'media_items': []}}
    monkeypatch.setattr(x_providers, 'fetch_x_via_graphql', download)
    result = asyncio.run(x_providers.fetch_x_with_priority(URL, {}, lambda step: None,
        tikhub_fetcher=lambda *args: {'payload': {'tweet_text': '', 'media_items': []}}))
    assert result['payload']['tweet_text'] == '有效正文'


