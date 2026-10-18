"""Optional X reader using twitter-cli and explicitly configured server credentials.

Restores the historical CLI/GraphQL route without browser-cookie extraction.
The CLI remains optional; missing dependencies/authentication trigger fallback.
"""
import asyncio
import json
import os
import re
import shlex
import shutil
from datetime import UTC, datetime
from pathlib import Path

from app.config import settings
from app.services.twitter_cli_settings import resolve_twitter_cli
from app.services.fetchers.social import TWEET_HOSTS, extract_x_article_id, extract_x_tweet_id
from app.services.fetchers.tikhub import normalize_flat_tweet_data, normalize_tikhub_tweet_result
from app.services.fetchers.twitter_article_rich import render_twitter_article_result
from urllib.parse import urlsplit

CLI_TIMEOUT_SECONDS = 90
VERIFY_TIMEOUT_SECONDS = 45


def _twitter_command(config: dict | None = None) -> str:
    configured = resolve_twitter_cli(config)['executable']
    command = shutil.which(configured or 'twitter')
    if not command:
        raise RuntimeError('未找到 twitter-cli，请在后端服务器安装，并在后台「X 登录配置」设置可执行文件路径')
    return command


def _twitter_python(command: str) -> str | None:
    try:
        with open(command, encoding='utf-8') as stream:
            line = stream.readline(1024).strip()
        parts = shlex.split(line[2:]) if line.startswith('#!') else []
        if parts and Path(parts[0]).name == 'env':
            parts = parts[1:]
        if parts and 'python' in Path(parts[0]).name:
            return shutil.which(parts[0])
    except (OSError, UnicodeError, ValueError):
        pass
    return None


def _explicit_auth(config: dict | None = None) -> tuple[str, str]:
    resolved = resolve_twitter_cli(config)
    return resolved['auth'], resolved['csrf']


def twitter_cli_status(config: dict | None = None) -> dict:
    try:
        _twitter_command(config)
        installed = True
    except RuntimeError:
        installed = False
    auth, csrf = _explicit_auth(config)
    configured = bool(auth and csrf)
    return {'installed': installed, 'credentials_configured': configured,
            'status': '未安装 twitter-cli' if not installed else '未配置登录态' if not configured else '已配置，登录有效性以抓取结果为准'}


async def _run(args: list[str], env: dict) -> tuple[int, str]:
    process = await asyncio.create_subprocess_exec(*args, env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=CLI_TIMEOUT_SECONDS)
    except (TimeoutError, asyncio.CancelledError) as exc:
        if process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
        await process.communicate()
        if isinstance(exc, asyncio.CancelledError):
            raise
        raise RuntimeError('twitter-cli 获取超时') from exc
    return process.returncode, stdout.decode('utf-8', errors='replace')


async def verify_twitter_cli(config: dict) -> dict:
    """Verify the saved pair using the CLI's authenticated account endpoint."""
    messages = {
        'verified': 'X 登录态验证成功。',
        'missing_credentials': '请先保存完整的 auth_token 和 ct0，再验证登录态。',
        'missing_cli': '服务器未找到 twitter-cli，请安装或检查可执行文件路径。',
        'runtime': '无法使用 twitter-cli 的 Python 运行环境，请检查安装与可执行文件路径。',
        'unauthorized': 'X 登录态无效或已过期，请重新获取同一账号的 auth_token 和 ct0 后保存。',
        'forbidden': 'X 拒绝了认证请求，登录态可能失效或账号受到限制，请检查账号状态。',
        'rate_limited': 'X 请求受到频率限制，请稍后再验证。',
        'network': '无法完成 X 认证请求，请检查服务器网络或稍后重试。',
        'timeout': 'X 登录态验证超时，请检查服务器网络后重试。',
        'invalid_response': 'X 未返回有效的登录账号信息，暂时无法确认登录态。',
    }
    def outcome(reason: str) -> dict:
        return {'verified': reason == 'verified', 'reason': reason, 'message': messages[reason],
                'checked_at': datetime.now(UTC).isoformat()}

    auth, csrf = _explicit_auth(config)
    if not auth or not csrf:
        return outcome('missing_credentials')
    try:
        command = _twitter_command(config)
    except RuntimeError:
        return outcome('missing_cli')
    interpreter = _twitter_python(command)
    if not interpreter:
        return outcome('runtime')
    env = os.environ.copy()
    for key in ('PYTHONHOME', 'PYTHONPATH', '__PYVENV_LAUNCHER__'):
        env.pop(key, None)
    env.update(TWITTER_AUTH_TOKEN=auth, TWITTER_CT0=csrf)
    try:
        runner = str(Path(__file__).with_name('twitter_cli_runner.py'))
        code, output = await asyncio.wait_for(_run([interpreter, runner, '--verify'], env), timeout=VERIFY_TIMEOUT_SECONDS)
        if code != 0:
            return outcome('runtime')
        data = json.loads(output)
        if isinstance(data, dict) and data.get('verified') is True:
            account = data.get('account')
            if not isinstance(account, dict):
                return outcome('invalid_response')
            screen_name = account.get('screen_name')
            if not isinstance(screen_name, str) or not re.fullmatch(r'[A-Za-z0-9_]{1,64}', screen_name):
                return outcome('invalid_response')
            name = account.get('name')
            return {**outcome('verified'), 'account': {
                'name': name[:256] if isinstance(name, str) and name else screen_name,
                'screen_name': screen_name,
            }}
        reason = data.get('reason') if isinstance(data, dict) else None
        if isinstance(data, dict) and data.get('verified') is False and isinstance(reason, str) and reason in {
            'unauthorized', 'forbidden', 'rate_limited', 'network', 'runtime', 'invalid_response',
        }:
            return outcome(reason)
        return outcome('invalid_response')
    except TimeoutError:
        return outcome('timeout')
    except (ValueError, TypeError):
        return outcome('invalid_response')
    except Exception:
        # Subprocess/network exceptions can include headers and cookie values.
        return outcome('network')


def parse_twitter_article_markdown(markdown: str, url: str) -> dict:
    lines = markdown.strip().splitlines()
    if not lines or not lines[0].startswith('# '):
        raise RuntimeError('twitter-cli 未返回有效长文')
    title = lines[0][2:].strip() or 'X 长文'
    index = 1
    metadata = {}
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            if metadata:
                break
            continue
        match = re.match(r'^- (Author|Published|URL|Likes|Retweets|Replies|Bookmarks|Views):\s*(.*)$', line)
        if not match:
            break
        metadata[match[1]] = match[2]
        index += 1
    body = '\n'.join(lines[index:]).strip()
    if not body:
        raise RuntimeError('twitter-cli 未返回长文正文')
    if metadata.get('URL') and extract_x_tweet_id(metadata['URL']) != extract_x_tweet_id(url):
        raise RuntimeError('twitter-cli 返回的文章与原始链接不一致')
    author = re.match(r'@([^\s]+)(?:\s*\((.*?)\))?', metadata.get('Author', ''))
    payload = normalize_flat_tweet_data({'id': extract_x_tweet_id(url), 'text': '',
        'author': {'name': (author.group(2) or author.group(1)) if author else '未知作者',
                   'screen_name': author.group(1) if author else ''},
        'created_at': metadata.get('Published', '')})
    payload['title'] = title
    payload['tweet_url'] = url
    return {'payload': payload, 'article_result': None,
            'article_text': {'title': title, 'full_text': body, 'cover_image_url': ''}}


async def fetch_x_via_twitter_cli(url: str, update_step, config: dict | None = None) -> dict:
    parsed = urlsplit(url)
    tweet_id = extract_x_tweet_id(url)
    if (parsed.scheme not in {'https', 'http'} or parsed.hostname not in TWEET_HOSTS or not tweet_id
            or parsed.username or parsed.password or parsed.port not in {None, 80, 443}):
        raise RuntimeError('twitter-cli 需要 X 宿主推文链接，暂不支持 i/article 直链')
    command = _twitter_command(config)
    auth, csrf = _explicit_auth(config)
    if not auth or not csrf:
        raise RuntimeError('twitter-cli 未配置登录态，请在后台「X 登录配置」保存 auth_token 和 ct0')
    env = os.environ.copy()
    for key in ('PYTHONHOME', 'PYTHONPATH', '__PYVENV_LAUNCHER__'):
        env.pop(key, None)
    env.update(TWITTER_AUTH_TOKEN=auth, TWITTER_CT0=csrf)
    interpreter = _twitter_python(command)
    if not interpreter:
        raise RuntimeError('无法识别 twitter-cli 的 Python 运行环境，请在后台「X 登录配置」将路径指向 CLI 的 Python 入口脚本')
    if interpreter:
        update_step('正在通过 twitter-cli 登录态读取 X 富文本...')
        runner = str(Path(__file__).with_name('twitter_cli_runner.py'))
        code, output = await _run([interpreter, runner, tweet_id], env)
        if code == 0:
            try:
                result = json.loads(output)['tweet_result']
                if str(result.get('rest_id') or '') != tweet_id:
                    raise ValueError('推文不匹配')
                payload = normalize_tikhub_tweet_result(result)
                raw_article = ((result.get('article') or {}).get('article_results') or {}).get('result')
                rendered = render_twitter_article_result(raw_article) if isinstance(raw_article, dict) else {}
                body = rendered.get('content_md') or str((raw_article or {}).get('plain_text') or '')
                if body:
                    payload['title'] = rendered.get('title') or payload['title']
                    payload['cover_image_url'] = rendered.get('cover_image_url') or payload['cover_image_url']
                    return {'payload': payload, 'article_result': raw_article,
                            'article_text': {'title': payload['title'], 'full_text': body, 'cover_image_url': payload['cover_image_url']}}
                if (payload['tweet_text'].strip() and not raw_article and not payload.get('article_preview')
                        and not extract_x_article_id(payload['tweet_text'])):
                    return {'payload': payload, 'article_result': None, 'article_text': None}
            except (ValueError, KeyError, TypeError, AttributeError):
                pass
    update_step('正在通过 twitter-cli article 读取长文 Markdown...')
    code, output = await _run([interpreter, runner, '--markdown', url], env)
    if code != 0:
        # CLI errors can contain auth headers/cookies. Never publish raw output.
        raise RuntimeError('twitter-cli 获取失败，请检查登录态是否有效、网络及宿主推文链接')
    return parse_twitter_article_markdown(output, url)
