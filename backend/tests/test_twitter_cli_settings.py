"""Admin-managed X credentials stay private and are used by the actual provider."""
import asyncio
import json
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.routers import config
from app.services import settings_store
from app.services.fetchers import x_twitter_cli

ENDPOINT = '/api/v1/config/twitter-cli'
AUTH = 'saved-auth-cookie-for-test'
CSRF = 'saved-csrf-cookie-for-test'


@pytest.fixture
def cli_settings_client(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'cli-settings.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async def prepare():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    asyncio.run(prepare())
    monkeypatch.setattr(settings_store, 'AsyncSessionLocal', sessions)
    for name in ('TWITTER_AUTH_TOKEN', 'TWITTER_CT0', 'SYNTHAI_TWITTER_BIN'):
        monkeypatch.delenv(name, raising=False)
        monkeypatch.setattr(x_twitter_cli.settings, name, '')
    app = FastAPI()
    app.include_router(config.router, prefix='/api/v1/config')
    with TestClient(app) as client:
        yield client
    asyncio.run(engine.dispose())


def test_roundtrip_masks_credentials_and_survives_other_settings(cli_settings_client):
    client = cli_settings_client
    response = client.put(ENDPOINT, json={'authToken': AUTH, 'ct0': CSRF, 'executable': '/opt/tools/twitter'})
    assert response.status_code == 200
    for response in (response, client.get(ENDPOINT), client.get('/api/v1/config')):
        assert AUTH not in response.text and CSRF not in response.text
    view = client.get(ENDPOINT).json()
    assert view['credentials_configured'] is True
    assert view['source'] == 'config'
    assert view['auth_token_masked'].startswith('••••')
    assert view['ct0_masked'].startswith('••••')
    assert view['executable'] == '/opt/tools/twitter'
    assert client.post('/api/v1/config', json={'modelName': 'test-model'}).status_code == 200
    saved = asyncio.run(config.get_runtime_config())
    assert saved['twitterAuthToken'] == AUTH and saved['twitterCt0'] == CSRF
    assert saved['twitterCliBin'] == '/opt/tools/twitter'


def test_blank_and_masked_inputs_preserve_saved_pair(cli_settings_client):
    client = cli_settings_client
    assert client.put(ENDPOINT, json={'authToken': AUTH, 'ct0': CSRF}).status_code == 200
    assert client.put(ENDPOINT, json={'authToken': '', 'ct0': '••••test', 'executable': ''}).status_code == 200
    saved = asyncio.run(config.get_runtime_config())
    assert (saved['twitterAuthToken'], saved['twitterCt0']) == (AUTH, CSRF)
    assert client.put(ENDPOINT, json={'authToken': 'rotated-auth-secret'}).status_code == 200
    saved = asyncio.run(config.get_runtime_config())
    assert saved['twitterAuthToken'] == 'rotated-auth-secret' and saved['twitterCt0'] == CSRF


def test_saved_credentials_override_environment_and_clear_restores_fallback(cli_settings_client, monkeypatch):
    client = cli_settings_client
    monkeypatch.setenv('TWITTER_AUTH_TOKEN', 'env-auth-secret')
    monkeypatch.setenv('TWITTER_CT0', 'env-csrf-secret')
    view = client.get(ENDPOINT).json()
    assert view['source'] == 'environment' and view['credentials_configured']
    assert client.put(ENDPOINT, json={'authToken': AUTH, 'ct0': CSRF}).status_code == 200
    saved = asyncio.run(config.get_runtime_config())
    assert x_twitter_cli._explicit_auth(saved) == (AUTH, CSRF)
    cleared = client.delete(ENDPOINT)
    assert cleared.status_code == 200
    assert cleared.json()['source'] == 'environment'
    assert cleared.json()['has_saved_credentials'] is False
    saved = asyncio.run(config.get_runtime_config())
    assert x_twitter_cli._explicit_auth(saved) == ('env-auth-secret', 'env-csrf-secret')


@pytest.mark.parametrize('method', ['GET', 'PUT', 'DELETE'])
def test_all_cli_settings_operations_require_admin(cli_settings_client, method):
    client = cli_settings_client
    asyncio.run(settings_store.set_admin_token_hash(settings_store.hash_admin_token('admin-test-token')))
    response = client.request(method, ENDPOINT, json={} if method == 'PUT' else None)
    assert response.status_code == 401
    assert client.get(ENDPOINT, headers={'X-Admin-Token': 'admin-test-token'}).status_code == 200


def test_generic_config_cannot_update_private_cli_fields(cli_settings_client):
    client = cli_settings_client
    assert client.post('/api/v1/config', json={'twitterAuthToken': AUTH, 'twitterCt0': CSRF}).status_code == 200
    saved = asyncio.run(config.get_runtime_config())
    assert not saved.get('twitterAuthToken') and not saved.get('twitterCt0')
    assert 'twitterAuthToken' not in client.get('/api/v1/config').json()


def test_malformed_json_never_echoes_secret_input(cli_settings_client):
    response = cli_settings_client.put(ENDPOINT, content='{"authToken":"' + AUTH, headers={'Content-Type': 'application/json'})
    assert response.status_code == 422
    assert AUTH not in response.text


def test_verification_endpoint_requires_admin_and_uses_saved_config(cli_settings_client, monkeypatch):
    client = cli_settings_client
    assert client.put(ENDPOINT, json={'authToken': AUTH, 'ct0': CSRF}).status_code == 200
    asyncio.run(settings_store.set_admin_token_hash(settings_store.hash_admin_token('verify-admin-token')))
    async def verify(values):
        assert values['twitterAuthToken'] == AUTH and values['twitterCt0'] == CSRF
        return {'verified': True, 'reason': 'verified', 'message': 'verified', 'checked_at': '2026-10-18T00:00:00Z'}
    monkeypatch.setattr(x_twitter_cli, 'verify_twitter_cli', verify, raising=False)
    assert client.post(ENDPOINT + '/verify').status_code == 401
    response = client.post(ENDPOINT + '/verify', headers={'X-Admin-Token': 'verify-admin-token'})
    assert response.status_code == 200 and response.json()['verified'] is True
    assert AUTH not in response.text and CSRF not in response.text
    saved = asyncio.run(config.get_runtime_config())
    assert saved['twitterAuthToken'] == AUTH and saved['twitterCt0'] == CSRF


def test_failure_reason_redacts_saved_cookies(cli_settings_client, monkeypatch):
    from app.services.fetchers import x_providers
    async def fail(*args):
        raise RuntimeError(f'provider error: {AUTH} / {CSRF}')
    monkeypatch.setattr(x_providers, 'fetch_x_via_twitter_cli', fail)
    monkeypatch.setattr(x_providers, 'fetch_x_via_graphql', fail)
    saved = {'twitterAuthToken': AUTH, 'twitterCt0': CSRF}
    with pytest.raises(RuntimeError) as error:
        asyncio.run(x_providers.fetch_x_with_priority('https://x.com/a/status/123', saved, lambda step: None, tikhub_fetcher=lambda *args: None))
    assert AUTH not in str(error.value) and CSRF not in str(error.value)
    assert '[已隐藏]' in str(error.value)


@pytest.mark.parametrize('body', [
    {'authToken': AUTH}, {'ct0': CSRF},
    {'authToken': AUTH + '\ninvalid', 'ct0': CSRF},
    {'authToken': AUTH * 200, 'ct0': CSRF},
    {'authToken': [AUTH], 'ct0': CSRF},
    {'authToken': AUTH, 'ct0': CSRF, 'executable': 'bad\x00path'},
    [AUTH, CSRF], {'unknown': AUTH},
])
def test_invalid_payload_is_atomic_and_does_not_echo_credentials(cli_settings_client, body):
    client = cli_settings_client
    response = client.put(ENDPOINT, json=body)
    assert response.status_code == 422
    assert AUTH not in response.text and CSRF not in response.text
    saved = asyncio.run(config.get_runtime_config())
    assert not saved.get('twitterAuthToken') and not saved.get('twitterCt0')


def test_saved_path_and_pair_reach_real_provider_without_command_line_secrets(cli_settings_client, tmp_path, monkeypatch):
    client = cli_settings_client
    executable = tmp_path / 'twitter'
    executable.write_text(f'#!{sys.executable}\n')
    executable.chmod(0o700)
    response = client.put(ENDPOINT, json={'authToken': AUTH, 'ct0': CSRF, 'executable': str(executable)})
    assert response.status_code == 200
    assert response.json()['installed'] is True
    assert client.get('/api/v1/config/fetch-priorities').json()['providers']['twitter_cli']['credentials_configured']
    observed = {}
    async def run(args, env):
        observed.update(args=args, env=env)
        return 0, json.dumps({'tweet_result': {'rest_id': '123456789', 'legacy': {'full_text': 'Saved credential content'}}})
    monkeypatch.setattr(x_twitter_cli, '_run', run)
    from app.services.fetchers.x_providers import fetch_x_with_priority
    saved = asyncio.run(config.get_runtime_config())
    saved['fetchProviderPriorities'] = json.dumps({'x': ['twitter_cli', 'tikhub', 'x_graphql']})
    def unexpected(*args):
        raise AssertionError('Successful CLI fetch must not call another provider')
    result = asyncio.run(fetch_x_with_priority('https://x.com/author/status/123456789', saved, lambda step: None, tikhub_fetcher=unexpected))
    assert result['payload']['tweet_text'] == 'Saved credential content'
    assert observed['env']['TWITTER_AUTH_TOKEN'] == AUTH and observed['env']['TWITTER_CT0'] == CSRF
    assert AUTH not in str(observed['args']) and CSRF not in str(observed['args'])
