"""Resolve persisted CLI settings without exposing credentials in public config."""
import os

from app.config import settings
from app.services.settings_store import is_masked, mask_secret


def resolve_twitter_cli(values: dict | None = None) -> dict:
    values = values or {}
    saved_auth = str(values.get('twitterAuthToken') or '').strip()
    saved_csrf = str(values.get('twitterCt0') or '').strip()
    # A stored pair belongs together; never combine cookies from two accounts.
    saved = bool(saved_auth or saved_csrf)
    auth = saved_auth if saved else os.environ.get('TWITTER_AUTH_TOKEN', '').strip() or settings.TWITTER_AUTH_TOKEN.strip()
    csrf = saved_csrf if saved else os.environ.get('TWITTER_CT0', '').strip() or settings.TWITTER_CT0.strip()
    executable = (str(values.get('twitterCliBin') or '').strip()
                  or os.environ.get('SYNTHAI_TWITTER_BIN', '').strip() or settings.SYNTHAI_TWITTER_BIN.strip())
    return {'auth': auth, 'csrf': csrf, 'executable': executable,
            'source': 'config' if saved else 'environment' if auth or csrf else None,
            'has_saved_credentials': saved}


def twitter_cli_config_view(values: dict) -> dict:
    from app.services.fetchers.x_twitter_cli import twitter_cli_status
    runtime = resolve_twitter_cli(values)
    return {**twitter_cli_status(values),
            'auth_token_configured': bool(runtime['auth']), 'ct0_configured': bool(runtime['csrf']),
            'auth_token_masked': mask_secret(runtime['auth']), 'ct0_masked': mask_secret(runtime['csrf']),
            'source': runtime['source'], 'has_saved_credentials': runtime['has_saved_credentials'],
            'executable': str(values.get('twitterCliBin') or ''),
            'effective_executable': runtime['executable'] or 'twitter'}


def twitter_cli_updates(payload: object, saved: dict) -> dict[str, str]:
    keys = {'authToken': 'twitterAuthToken', 'ct0': 'twitterCt0', 'executable': 'twitterCliBin'}
    if not isinstance(payload, dict) or set(payload) - keys.keys():
        raise ValueError('配置格式不正确。')
    updates = {}
    for field, key in keys.items():
        if field not in payload or payload[field] is None:
            continue
        value = payload[field]
        limit = 2048 if field == 'executable' else 4096
        if not isinstance(value, str) or len(value) > limit or any(char in value for char in '\r\n\x00'):
            raise ValueError('配置值格式不正确，请检查长度及换行。')
        value = value.strip()
        if field != 'executable' and (not value or is_masked(value)):
            continue
        updates[key] = value
    if {'twitterAuthToken', 'twitterCt0'} & updates.keys():
        effective = {**saved, **updates}
        if not effective.get('twitterAuthToken') or not effective.get('twitterCt0'):
            raise ValueError('首次保存请同时填写 auth_token 和 ct0；已保存的字段可留空保持不变。')
    return updates
