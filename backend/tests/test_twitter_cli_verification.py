"""Verify saved X credentials with the CLI runtime, without publishing secrets."""
import asyncio
import json
import sys
import types

import pytest

from app.services.fetchers import twitter_cli_runner as runner
from app.services.fetchers import x_twitter_cli as cli

CONFIG = {'twitterAuthToken': 'verify-auth-test-secret', 'twitterCt0': 'verify-ct0-test-secret'}


@pytest.fixture
def runtime(monkeypatch):
    monkeypatch.setattr(cli, '_twitter_command', lambda config=None: '/test/twitter')
    monkeypatch.setattr(cli, '_twitter_python', lambda command: sys.executable)
    return cli


def test_verification_uses_saved_pair_and_only_returns_account_display_fields(runtime, monkeypatch):
    async def run(args, env):
        assert args[-1] == '--verify'
        assert env['TWITTER_AUTH_TOKEN'] == CONFIG['twitterAuthToken']
        assert env['TWITTER_CT0'] == CONFIG['twitterCt0']
        assert CONFIG['twitterAuthToken'] not in str(args)
        return 0, json.dumps({'verified': True, 'account': {'name': '测试账号', 'screen_name': 'test_user', 'email': 'must-not-escape', 'cookie': CONFIG['twitterAuthToken']}})
    monkeypatch.setattr(cli, '_run', run)
    result = asyncio.run(cli.verify_twitter_cli(CONFIG))
    assert result['verified'] is True
    assert result['reason'] == 'verified' and result['checked_at']
    assert result['account'] == {'name': '测试账号', 'screen_name': 'test_user'}
    assert 'must-not-escape' not in json.dumps(result)
    assert CONFIG['twitterAuthToken'] not in json.dumps(result)


@pytest.mark.parametrize('code,reason', [(401, 'unauthorized'), (403, 'forbidden'), (429, 'rate_limited'), (0, 'network')])
def test_runner_verifies_current_account_and_sanitizes_errors(monkeypatch, code, reason):
    class APIError(Exception):
        status_code = code
    class Client:
        def __init__(self, auth, csrf, rate_limit_config):
            assert (auth, csrf) == ('explicit-auth', 'explicit-csrf')
            assert rate_limit_config['maxRetries'] == 0
        def fetch_me(self):
            raise APIError('explicit-auth explicit-csrf raw response')
    module = types.ModuleType('twitter_cli.client')
    module.TwitterClient = Client
    monkeypatch.setitem(sys.modules, 'twitter_cli.client', module)
    monkeypatch.setenv('TWITTER_AUTH_TOKEN', 'explicit-auth')
    monkeypatch.setenv('TWITTER_CT0', 'explicit-csrf')
    result = runner.verify_login()
    assert result == {'verified': False, 'reason': reason}


def test_runner_success_requires_an_authenticated_profile(monkeypatch):
    state = {'profile': types.SimpleNamespace(id='123', name='测试账号', screen_name='test_user', email='must-not-escape')}
    class Client:
        def __init__(self, *args, **kwargs):
            pass
        def fetch_me(self):
            return state['profile']
    module = types.ModuleType('twitter_cli.client')
    module.TwitterClient = Client
    monkeypatch.setitem(sys.modules, 'twitter_cli.client', module)
    monkeypatch.setenv('TWITTER_AUTH_TOKEN', 'explicit-auth')
    monkeypatch.setenv('TWITTER_CT0', 'explicit-csrf')
    assert runner.verify_login() == {'verified': True, 'account': {'name': '测试账号', 'screen_name': 'test_user'}}
    state['profile'] = types.SimpleNamespace(id='', screen_name='')
    assert runner.verify_login() == {'verified': False, 'reason': 'invalid_response'}


@pytest.mark.parametrize('output', ['not-json with verify-auth-test-secret', '{"verified":"yes"}', '{"verified":false,"reason":"verify-auth-test-secret"}', '{}', '{"verified":true}', '{"verified":true,"account":"bad"}', '{"verified":true,"account":{"screen_name":"bad/handle"}}'])
def test_invalid_runner_output_never_reports_success_or_exposes_input(runtime, monkeypatch, output):
    async def run(*args):
        return 0, output
    monkeypatch.setattr(cli, '_run', run)
    result = asyncio.run(cli.verify_twitter_cli(CONFIG))
    assert result['verified'] is False
    assert CONFIG['twitterAuthToken'] not in json.dumps(result)


@pytest.mark.parametrize('reason', ['unauthorized', 'forbidden', 'rate_limited', 'network', 'runtime'])
def test_verification_maps_failure_to_safe_message(runtime, monkeypatch, reason):
    async def run(*args):
        return 0, json.dumps({'verified': False, 'reason': reason})
    monkeypatch.setattr(cli, '_run', run)
    result = asyncio.run(cli.verify_twitter_cli(CONFIG))
    assert result['verified'] is False and result['reason'] == reason
    assert result['message'] and result['checked_at']


def test_missing_credentials_never_starts_cli(runtime, monkeypatch):
    monkeypatch.delenv('TWITTER_AUTH_TOKEN', raising=False)
    monkeypatch.delenv('TWITTER_CT0', raising=False)
    monkeypatch.setattr(cli.settings, 'TWITTER_AUTH_TOKEN', '')
    monkeypatch.setattr(cli.settings, 'TWITTER_CT0', '')
    async def unexpected(*args):
        raise AssertionError('Cannot run with missing explicit cookies')
    monkeypatch.setattr(cli, '_run', unexpected)
    result = asyncio.run(cli.verify_twitter_cli({}))
    assert result['reason'] == 'missing_credentials' and result['verified'] is False


def test_verification_timeout_is_bounded_and_cancels_child(runtime, monkeypatch):
    state = {'cancelled': False}
    async def run(*args):
        try:
            await asyncio.sleep(10)
        finally:
            state['cancelled'] = True
    monkeypatch.setattr(cli, '_run', run)
    monkeypatch.setattr(cli, 'VERIFY_TIMEOUT_SECONDS', .01, raising=False)
    result = asyncio.run(cli.verify_twitter_cli(CONFIG))
    assert result['reason'] == 'timeout' and result['verified'] is False
    assert state['cancelled']
