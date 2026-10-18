"""Build the local read-only query catalog from TikHub's public OpenAPI file.

Usage: python scripts/build_tikhub_catalog.py /tmp/tikhub-openapi.json
Source: https://api.tikhub.io/openapi.json (no API key required).
"""
import json
import sys
from datetime import date
from pathlib import Path
from urllib.parse import quote

PLATFORMS = {
    'tikhub': '账户与计费', 'tiktok': 'TikTok',
    'xiaohongshu': '小红书', 'bilibili': 'Bilibili', 'twitter': 'X / Twitter',
    'wechat_mp': '微信公众号', 'wechat_channels': '微信视频号', 'wechat_search': '微信搜索',
    'youtube': 'YouTube', 'instagram': 'Instagram', 'kuaishou': '快手', 'weibo': '微博',
    'zhihu': '知乎', 'reddit': 'Reddit', 'threads': 'Threads', 'linkedin': 'LinkedIn',
    'telegram': 'Telegram', 'lemon8': 'Lemon8', 'pipixia': '皮皮虾',
    'xigua': '西瓜视频', 'toutiao': '今日头条',
}
# Exclude device registration, signatures, encryption and non-query utilities.
EXCLUDED_PREFIXES = ('generate_', 'encrypt_', 'decrypt_', 'register_', 'device_', 'open_', 'TTencrypt_', 'translate_', 'bulk_translate_')
EXCLUDED_NAMES = {'handler_shorten_url', 'fetch_tiktok_web_guest_cookie', 'fetch_sec_token', 'get_sign_image', 'fetch_share_qr_code', 'tiktok_live_room'}


def build(spec: dict) -> dict:
    def resolve(value, stack=()):
        if isinstance(value, list):
            return [resolve(item, stack) for item in value]
        if not isinstance(value, dict):
            return value
        if '$ref' in value:
            ref = value['$ref']
            if ref in stack or not ref.startswith('#/components/schemas/'):
                raise ValueError(f'Unsupported schema reference: {ref}')
            return resolve(spec['components']['schemas'][ref.rsplit('/', 1)[-1]], (*stack, ref))
        return {key: [entry.get('value') for entry in item.values()] if key == 'examples' and isinstance(item, dict)
                else resolve(item, stack) for key, item in value.items()}

    items = []
    for path, methods in spec['paths'].items():
        platform = path.split('/')[3] if path.startswith('/api/v1/') else ''
        leaf = path.rsplit('/', 1)[-1]
        if platform not in PLATFORMS or leaf.startswith(EXCLUDED_PREFIXES) or leaf in EXCLUDED_NAMES:
            continue
        if platform == 'tikhub' and not path.startswith('/api/v1/tikhub/user/'):
            continue
        for method, op in methods.items():
            if method not in ('get', 'post'):
                continue
            if method == 'post' and not leaf.startswith(('fetch_', 'get_', 'search_', 'multi_get_', 'check_', 'calculate_')):
                continue
            params = []
            for param in op.get('parameters', []):
                if param['in'] != 'query':
                    raise ValueError(f'Unsupported parameter location in {path}')
                params.append({'name': param['name'], 'in': 'query', 'required': param.get('required', False),
                               'schema': resolve(param['schema']), 'description': param.get('description', ''),
                               'example': param.get('example')})
            body = resolve(op.get('requestBody', {}).get('content', {}).get('application/json', {}).get('schema', {}))
            if body:
                properties = body.get('properties', {})
                # Scalar/array bodies and arbitrary JSON objects cannot be
                # represented as independent form fields, so preserve the
                # complete request body as one validated JSON parameter.
                if body.get('type') != 'object' or not properties:
                    params.append({'name': '$body', 'in': 'body_root', 'required': op.get('requestBody', {}).get('required', False), 'schema': body, 'description': body.get('description', '请求内容（JSON）'), 'example': body.get('example')})
                for name, schema in properties.items():
                    params.append({'name': name, 'in': 'body', 'required': name in body.get('required', []),
                                   'schema': schema, 'description': schema.get('description', ''),
                                   'example': schema.get('example')})
            if len({p['name'] for p in params}) != len(params):
                raise ValueError(f'Duplicate parameter in {path}')
            items.append({
                'id': f'{method.upper()} {path}', 'platform': platform, 'method': method.upper(), 'path': path,
                'title': op.get('summary', leaf).split('/')[0].strip(),
                'group': op.get('tags', [''])[0],
                'description': op.get('description', '').split('# [English]')[0].strip()[:2400],
                'docs_url': f'https://api.tikhub.io/#/{quote(op.get("tags", [""])[0])}/{quote(op.get("operationId", ""))}',
                'parameters': params,
            })
    return {'source': 'https://api.tikhub.io/openapi.json', 'generated_at': str(date.today()),
            'platforms': [{'id': key, 'name': name, 'count': sum(item['platform'] == key for item in items)} for key, name in PLATFORMS.items()],
            'items': items}


if __name__ == '__main__':
    catalog = build(json.loads(Path(sys.argv[1]).read_text()))
    output = Path(__file__).resolve().parents[1] / 'app/data/tikhub_catalog.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    # One operation per line makes regenerated diffs reviewable.
    header = json.dumps({k: v for k, v in catalog.items() if k != 'items'}, ensure_ascii=False)
    output.write_text(header[:-1] + ', "items": [\n' + ',\n'.join(json.dumps(item, ensure_ascii=False) for item in catalog['items']) + '\n]}\n')
    print(f'Built {len(catalog["items"])} queries across {len(catalog["platforms"])} platforms: {output}')
