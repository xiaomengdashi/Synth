"""Optional twitter-cli provider: rich articles, explicit auth, cleanup and fallback."""
import asyncio
import json
import sys

import pytest

URL = 'https://x.com/author/status/123456789'
RESULT = {
    'rest_id': '123456789',
    'core': {'user_results': {'result': {'legacy': {'name': '作者', 'screen_name': 'author'}}}},
    'legacy': {'full_text': 'https://x.com/i/article/999', 'created_at': '2026-10-18'},
    'article': {'article_results': {'result': {'title': 'CLI 长文', 'content_state': {
        'blocks': [{'type': 'unstyled', 'text': '完整长文正文', 'inlineStyleRanges': [{'offset': 0, 'length': 2, 'style': 'BOLD'}]}],
        'entityMap': [],
    }}}},
}


@pytest.fixture
def cli_ready(monkeypatch):
    from app.services.fetchers import x_twitter_cli as cli
    monkeypatch.setenv('TWITTER_AUTH_TOKEN', 'test-auth-secret')
    monkeypatch.setenv('TWITTER_CT0', 'test-csrf-secret')
    monkeypatch.setattr(cli, '_twitter_command', lambda config=None: '/opt/tools/twitter')
    monkeypatch.setattr(cli, '_twitter_python', lambda command: sys.executable)
    return cli


def test_rich_cli_output_maps_to_reader_and_preserves_formatting(cli_ready, monkeypatch):
    cli = cli_ready
    class Process:
        returncode = 0
        async def communicate(self):
            return json.dumps({'tweet_result': RESULT}).encode(), b''
    async def spawn(*args, **kwargs):
        assert kwargs['env']['TWITTER_AUTH_TOKEN'] == 'test-auth-secret'
        assert 'test-auth-secret' not in str(args)
        assert args[-1] == '123456789'
        return Process()
    monkeypatch.setattr(cli.asyncio, 'create_subprocess_exec', spawn)
    result = asyncio.run(cli.fetch_x_via_twitter_cli(URL, lambda step: None))
    assert result['payload']['title'] == 'CLI 长文'
    assert result['payload']['author_name'] == '作者'
    assert result['article_result']['title'] == 'CLI 长文'
    assert '**完整**' in result['article_text']['full_text']


def test_no_explicit_credentials_never_starts_browser_cookie_extraction(cli_ready, monkeypatch):
    monkeypatch.delenv('TWITTER_AUTH_TOKEN')
    monkeypatch.delenv('TWITTER_CT0')
    monkeypatch.setattr(cli_ready.settings, 'TWITTER_AUTH_TOKEN', '')
    monkeypatch.setattr(cli_ready.settings, 'TWITTER_CT0', '')
    async def unexpected(*args, **kwargs):
        raise AssertionError('缺少凭据时不应启动 CLI 或读取浏览器 Cookie')
    monkeypatch.setattr(cli_ready.asyncio, 'create_subprocess_exec', unexpected)
    with pytest.raises(RuntimeError, match='登录态'):
        asyncio.run(cli_ready.fetch_x_via_twitter_cli(URL, lambda step: None))


def test_cli_markdown_fallback_keeps_bullets_code_and_images(cli_ready, monkeypatch):
    outputs = [(1, b''), (0, '# 标题\n\n- Author: @author (作者)\n- URL: https://x.com/author/status/123456789\n\n- 正文列表第一项\n- 正文列表第二项\n\n```python\nprint(1)\n```\n\n![图片](https://pbs.twimg.com/a.jpg)'.encode())]
    class Process:
        async def communicate(self):
            return self.output, b''
    async def spawn(*args, **kwargs):
        process = Process()
        process.returncode, process.output = outputs.pop(0)
        return process
    monkeypatch.setattr(cli_ready.asyncio, 'create_subprocess_exec', spawn)
    result = asyncio.run(cli_ready.fetch_x_via_twitter_cli(URL, lambda step: None))
    body = result['article_text']['full_text']
    assert body.startswith('- 正文列表第一项')
    assert '```python' in body and '![图片]' in body
    assert '- Author:' not in body


def test_invalid_cookie_error_does_not_expose_raw_stderr(cli_ready, monkeypatch):
    class Process:
        returncode = 1
        async def communicate(self):
            return b'', b'auth_token=test-auth-secret; ct0=test-csrf-secret'
    async def spawn(*args, **kwargs):
        return Process()
    monkeypatch.setattr(cli_ready.asyncio, 'create_subprocess_exec', spawn)
    with pytest.raises(RuntimeError) as caught:
        asyncio.run(cli_ready.fetch_x_via_twitter_cli(URL, lambda step: None))
    assert 'test-auth-secret' not in str(caught.value) and 'test-csrf-secret' not in str(caught.value)


def test_timeout_kills_child_and_allows_provider_fallback(cli_ready, monkeypatch):
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
    monkeypatch.setattr(cli_ready.asyncio, 'create_subprocess_exec', spawn)
    monkeypatch.setattr(cli_ready, 'CLI_TIMEOUT_SECONDS', .01)
    with pytest.raises(RuntimeError, match='超时'):
        asyncio.run(cli_ready.fetch_x_via_twitter_cli(URL, lambda step: None))
    assert state == {'killed': True, 'reaped': True}


def test_saved_cli_priority_is_used_before_other_providers(monkeypatch):
    from app.services.fetchers import x_providers
    async def cli(url, step, config=None):
        return {'payload': {'tweet_text': 'CLI 正文'}}
    def unexpected(*args):
        raise AssertionError('CLI 成功后不能调用 TikHub')
    monkeypatch.setattr(x_providers, 'fetch_x_via_twitter_cli', cli)
    result = asyncio.run(x_providers.fetch_x_with_priority(URL, {
        'fetchProviderPriorities': json.dumps({'x': ['twitter_cli', 'tikhub', 'content_downloader']}),
    }, lambda step: None, tikhub_fetcher=unexpected))
    assert result['payload']['tweet_text'] == 'CLI 正文'


def test_cli_failure_falls_back_to_tikhub(monkeypatch):
    from app.services.fetchers import x_providers
    async def cli(url, step, config=None):
        raise RuntimeError('未配置登录态')
    monkeypatch.setattr(x_providers, 'fetch_x_via_twitter_cli', cli)
    result = asyncio.run(x_providers.fetch_x_with_priority(URL, {
        'fetchProviderPriorities': json.dumps({'x': ['twitter_cli', 'tikhub', 'content_downloader']}),
    }, lambda step: None, tikhub_fetcher=lambda *args: {'payload': {'tweet_text': '后备正文'}}))
    assert result['payload']['tweet_text'] == '后备正文'


def test_missing_executable_is_reported_as_unavailable(monkeypatch):
    from app.services.fetchers import x_twitter_cli as cli
    monkeypatch.setattr(cli.shutil, 'which', lambda command: None)
    assert cli.twitter_cli_status()['installed'] is False
    with pytest.raises(RuntimeError, match='未找到'):
        asyncio.run(cli.fetch_x_via_twitter_cli(URL, lambda step: None))


def test_status_and_public_config_never_return_credentials(cli_ready):
    from app.services.fetch_priorities import priority_view
    from app.services.settings_store import public_settings
    value = json.dumps({'priority_view': priority_view({}), 'public': public_settings({})})
    assert 'test-auth-secret' not in value and 'test-csrf-secret' not in value
    assert cli_ready.twitter_cli_status()['credentials_configured'] is True


def test_runner_uses_explicit_credentials_and_requests_article_rich_content(monkeypatch):
    import types
    from app.services.fetchers.twitter_cli_runner import fetch_tweet_result
    observed = {}
    class Client:
        def __init__(self, auth, csrf):
            observed['credentials'] = (auth, csrf)
        def _graphql_get(self, name, **kwargs):
            assert name == 'TweetResultByRestId'
            assert kwargs['field_toggles']['withArticleRichContentState'] is True
            return {'data': {'tweetResult': {'result': RESULT}}}
    package = types.ModuleType('twitter_cli')
    module = types.ModuleType('twitter_cli.client')
    module.TwitterClient = Client
    monkeypatch.setitem(sys.modules, 'twitter_cli', package)
    monkeypatch.setitem(sys.modules, 'twitter_cli.client', module)
    monkeypatch.setenv('TWITTER_AUTH_TOKEN', 'test-auth')
    monkeypatch.setenv('TWITTER_CT0', 'test-csrf')
    assert fetch_tweet_result('123456789')['article']['article_results']['result']['title'] == 'CLI 长文'
    assert observed['credentials'] == ('test-auth', 'test-csrf')


def test_article_preview_without_full_body_is_not_saved_as_success(cli_ready, monkeypatch):
    preview = {**RESULT, 'article': {'article_results': {'result': {'title': '仅预览'}}}}
    outputs = [(0, json.dumps({'tweet_result': preview})), (1, '')]
    async def run(*args):
        return outputs.pop(0)
    monkeypatch.setattr(cli_ready, '_run', run)
    with pytest.raises(RuntimeError):
        asyncio.run(cli_ready.fetch_x_via_twitter_cli(URL, lambda step: None))


def test_markdown_mismatched_source_does_not_replace_article():
    from app.services.fetchers.x_twitter_cli import parse_twitter_article_markdown
    with pytest.raises(RuntimeError):
        parse_twitter_article_markdown('# 不同文章\n\n- URL: https://x.com/other/status/987654321\n\n另一篇正文', URL)


def test_article_link_without_article_result_requires_full_body(cli_ready, monkeypatch):
    link_only = {key: value for key, value in RESULT.items() if key != 'article'}
    outputs = [(0, json.dumps({'tweet_result': link_only})), (1, '')]
    async def run(*args):
        return outputs.pop(0)
    monkeypatch.setattr(cli_ready, '_run', run)
    with pytest.raises(RuntimeError):
        asyncio.run(cli_ready.fetch_x_via_twitter_cli(URL, lambda step: None))


def test_markdown_runner_overrides_cli_implicit_cookie_lookup(monkeypatch):
    import types
    from app.services.fetchers import twitter_cli_runner as runner
    cli_module = types.ModuleType('twitter_cli.cli')
    def forbidden():
        raise AssertionError('不能自动读取浏览器 Cookie')
    cli_module.get_cookies = forbidden
    class Command:
        def main(self, args, **kwargs):
            assert args == ['article', URL, '--markdown']
            assert cli_module.get_cookies() == {'auth_token': 'explicit-auth', 'ct0': 'explicit-csrf'}
            return '正文'
    cli_module.cli = Command()
    package = types.ModuleType('twitter_cli')
    package.cli = cli_module
    monkeypatch.setitem(sys.modules, 'twitter_cli', package)
    monkeypatch.setitem(sys.modules, 'twitter_cli.cli', cli_module)
    monkeypatch.setenv('TWITTER_AUTH_TOKEN', 'explicit-auth')
    monkeypatch.setenv('TWITTER_CT0', 'explicit-csrf')
    runner.print_article_markdown(URL)
