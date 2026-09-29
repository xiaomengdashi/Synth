"""Validated queries from a snapshot of the official read-only catalog."""
import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from app.services.fetchers.tikhub import _tikhub_request


@lru_cache(maxsize=1)
def catalog() -> dict:
    return json.loads((Path(__file__).resolve().parents[1] / 'data/tikhub_catalog.json').read_text())


@lru_cache(maxsize=1)
def endpoint_index() -> dict:
    return {item['id']: item for item in catalog()['items']}


def query_catalog(platform: str = '', q: str = '', offset: int = 0, limit: int = 40) -> dict:
    source = catalog()
    words = q.lower().split()
    items = [item for item in source['items'] if (not platform or item['platform'] == platform)
             and all(word in f"{item['title']} {item['path']} {item['group']}".lower() for word in words)]
    return {'source': source['source'], 'generated_at': source['generated_at'],
            'platforms': source['platforms'], 'total': len(items),
            'items': items[offset:offset + limit], 'offset': offset, 'limit': limit}


def safe_response(value: Any, token: str) -> Any:
    """Keep integer IDs lossless in JavaScript, and strip credential echoes."""
    if isinstance(value, dict):
        return {str(k): '[已隐藏]' if any(part in str(k).lower() for part in ('authorization', 'api_token', 'apikey', 'cookie', 'password', 'access_token'))
                or (str(k).lower() == 'api_key' and not isinstance(v, dict)) else safe_response(v, token) for k, v in value.items()}
    if isinstance(value, list):
        return [safe_response(item, token) for item in value]
    if isinstance(value, str):
        return value.replace(token, '[已隐藏]') if token else value
    if isinstance(value, int) and abs(value) > 2**53 - 1:
        return str(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def run_query(endpoint_id: str, parameters: dict, token: str) -> dict:
    endpoint = endpoint_index().get(endpoint_id)
    if endpoint is None:
        raise ValueError('请选择查询目录中的接口。')
    if len(json.dumps(parameters, ensure_ascii=False)) > 128_000:
        raise ValueError('查询参数过大，请缩小单次查询范围。')
    allowed = {p['name'] for p in endpoint['parameters']}
    if set(parameters) - allowed:
        raise ValueError('包含该接口不支持的参数。')
    query, body = {}, {}
    root_body = None
    for param in endpoint['parameters']:
        name, schema = param['name'], param['schema']
        if name not in parameters:
            if param['required']:
                raise ValueError(f'请填写必填参数：{name}')
            continue
        value = parameters[name]
        if param['required'] and isinstance(value, str) and not value.strip():
            raise ValueError(f'请填写必填参数：{name}')
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f'参数 {name} 必须是有效数字。')
        error = next(Draft202012Validator(schema).iter_errors(value), None)
        if error:
            raise ValueError(f'参数 {name} 不符合要求（{error.validator}），请检查类型、范围或选项。')
        if param['in'] == 'query':
            query[name] = value
        elif param['in'] == 'body_root':
            root_body = value
        else:
            body[name] = value
    has_root_body = any(p['in'] == 'body_root' for p in endpoint['parameters'])
    payload = _tikhub_request(endpoint['path'], token, params=query or None,
                              json_body=(root_body if has_root_body else body) if endpoint['method'] == 'POST' else None,
                              unwrap_data=False, method=endpoint['method'])
    return {'endpoint': {'id': endpoint['id'], 'title': endpoint['title'], 'path': endpoint['path'], 'method': endpoint['method']},
            'data': safe_response(payload, token)}
