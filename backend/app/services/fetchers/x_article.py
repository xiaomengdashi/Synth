"""Supplement TikHub with server-rendered X article markup and local media."""
from __future__ import annotations

import asyncio
import hashlib
import re
import tempfile
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup, Comment
from app.config import settings

PAGE_HOSTS = {'x.com', 'www.x.com', 'twitter.com', 'www.twitter.com', 'mobile.x.com', 'mobile.twitter.com'}
ASSET_HOSTS = {'pbs.twimg.com', 'video.twimg.com', 'abs.twimg.com'}
ALLOWED_TAGS = set('div section p span h1 h2 h3 h4 h5 h6 b strong i em u s del br hr a ul ol li blockquote pre code figure figcaption img video source table thead tbody tr th td sub sup'.split())
ALLOWED_ATTRS = set('class dir lang title alt width height colspan rowspan start value type src poster href autoplay muted loop playsinline controls preload'.split())
STYLE_PROPERTIES = set('white-space font-weight font-style text-decoration text-align color background-color font-size line-height letter-spacing vertical-align'.split())
EXTENSIONS = {'image/jpeg': '.jpg', 'image/png': '.png', 'image/webp': '.webp', 'image/gif': '.gif', 'video/mp4': '.mp4', 'video/webm': '.webm', 'font/woff2': '.woff2', 'application/font-woff': '.woff2', 'application/octet-stream': '.woff2'}


def _allowed_url(url: str, hosts: set[str]) -> bool:
    try:
        p = urlsplit(url)
        return p.scheme == 'https' and p.hostname in hosts and not p.username and not p.password and p.port in (None, 443)
    except ValueError:
        return False


def _clean_css(css: str) -> str:
    css = re.sub(r'@import\s+[^;]+;', '', css, flags=re.I)
    css = re.sub(r'url\([^)]*\)', 'none', css, flags=re.I)
    # Prevent a CSS string from closing its style element in a srcdoc document.
    return css.replace('</', '<\\/')


def parse_x_article_page(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, 'html.parser')
    root = soup.select_one('.x-article-body')
    if root is None:
        raise ValueError('X 原页面未返回文章正文，可能需要登录或页面结构已变化。')
    heading = soup.select_one('h1[itemprop="headline"]') or soup.find('h1')
    cover = soup.select_one('img[itemprop="image"]')
    css = '\n'.join(_clean_css(n.get_text()) for n in root.select('style'))
    fonts = list(dict.fromkeys(n.get('href', '') for n in soup.select('link[as="font"]') if _allowed_url(n.get('href', ''), {'abs.twimg.com'})))[:6]
    for n in root.select('script,style,iframe,object,embed,form,input,button,link,meta,svg'):
        n.decompose()
    for n in root.find_all(string=lambda v: isinstance(v, Comment)):
        n.extract()
    for n in [root, *root.find_all(True)]:
        if n.name not in ALLOWED_TAGS:
            n.unwrap()
            continue
        style = n.get('style', '')
        n.attrs = {k: v for k, v in n.attrs.items() if k in ALLOWED_ATTRS}
        declarations = []
        for decl in style.split(';'):
            prop, sep, value = decl.partition(':')
            if sep and prop.strip().lower() in STYLE_PROPERTIES and not re.search(r'url|expression|[<>\\]', value, re.I):
                declarations.append(f'{prop.strip()}:{value.strip()}')
        if declarations: n['style'] = ';'.join(declarations)
        for attr in ('src', 'poster'):
            if n.get(attr):
                source = urljoin(url, n[attr])
                if _allowed_url(source, ASSET_HOSTS): n[attr] = source
                else: del n[attr]
        if n.name == 'a':
            href = urljoin(url, n.get('href', ''))
            if urlsplit(href).scheme in {'http', 'https'}:
                n['href'], n['target'], n['rel'] = href, '_blank', 'noopener noreferrer'
            else: n.attrs.pop('href', None)
        if n.name == 'video':
            n['muted'], n['playsinline'], n['preload'] = '', '', 'metadata'
        if n.name == 'img': n['loading'] = 'lazy'
    text = root.get_text()
    if not text.strip(): raise ValueError('X 文章正文为空。')
    cover_url = cover.get('src', '') if cover else ''
    return {'title': heading.get_text() if heading else '', 'body_html': str(root), 'body_css': css, 'text': text,
            'cover_url': cover_url if _allowed_url(cover_url, ASSET_HOSTS) else '', 'font_urls': fonts}


async def _read(client, url: str, hosts: set[str], limit: int) -> tuple[bytes, str]:
    for _ in range(4):
        if not _allowed_url(url, hosts): raise ValueError('资源地址不在允许的 X 域名范围内。')
        async with client.stream('GET', url, follow_redirects=False) as response:
            if response.is_redirect:
                url = urljoin(url, response.headers.get('location', ''))
                continue
            response.raise_for_status()
            data = bytearray()
            async for chunk in response.aiter_bytes():
                data.extend(chunk)
                if len(data) > limit: raise ValueError('X 页面或资源超过大小限制。')
            return bytes(data), response.headers.get('content-type', '').split(';')[0].lower()
    raise ValueError('X 资源重定向次数过多。')


async def fetch_x_article_replica(url: str, metadata: dict, update_step, *, client=None, media_dir=None) -> dict:
    if client is None:
        async with httpx.AsyncClient(timeout=30, headers={'User-Agent': 'Mozilla/5.0', 'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'}) as owned:
            return await fetch_x_article_replica(url, metadata, update_step, client=owned, media_dir=media_dir)
    if not re.fullmatch(r'/(?:\w+/status/\d+|i/web/status/\d+)/?', urlsplit(url).path):
        raise ValueError('补采需要 X 原始推文链接。')
    update_step('正在补采 X 原文格式、图片和动画...')
    raw, _ = await _read(client, url, PAGE_HOSTS, 4 * 1024 * 1024)
    parsed = parse_x_article_page(raw.decode('utf-8'), url)
    expected = metadata.get('full_text', '')
    if expected and re.sub(r'\s+', '', expected) != re.sub(r'\s+', '', parsed['text']):
        raise ValueError('X 原页与 TikHub 正文不一致，保留 TikHub 全文并提示重新抓取。')
    root = BeautifulSoup(parsed['body_html'], 'html.parser')
    urls = list(dict.fromkeys([n[a] for n in root.find_all(True) for a in ('src', 'poster') if n.get(a)] + [parsed['cover_url'], metadata.get('author_avatar_url', '')] + parsed['font_urls']))
    urls = [u for u in urls if u and _allowed_url(u, ASSET_HOSTS)]
    if len(urls) > 80: raise ValueError('X 文章资源数量超过限制。')
    directory = Path(media_dir or settings.MEDIA_DIR) / 'x'
    directory.mkdir(parents=True, exist_ok=True)
    semaphore = asyncio.Semaphore(4)
    budget = 0

    async def save(source):
        nonlocal budget
        async with semaphore:
            try:
                content, mime = await _read(client, source, ASSET_HOSTS, 30 * 1024 * 1024)
                extension = EXTENSIONS.get(mime)
                if not extension or not content: raise ValueError('无法识别媒体格式。')
                if source in parsed['font_urls']:
                    if content[:4] != b'wOF2': raise ValueError('字体格式错误。')
                    extension = '.woff2'
                elif mime == 'application/octet-stream': raise ValueError('媒体格式错误。')
                budget += len(content)
                if budget > 200 * 1024 * 1024: raise ValueError('文章媒体总大小超过限制。')
                name = hashlib.sha256(content).hexdigest() + extension
                target = directory / name
                if not target.exists():
                    with tempfile.NamedTemporaryFile(dir=directory, delete=False) as temp:
                        temp.write(content)
                        temporary = Path(temp.name)
                    temporary.replace(target)
                return {'source_url': source, 'local_url': f'/media/x/{name}', 'bytes': len(content), 'content_type': mime}
            except (httpx.HTTPError, ValueError, OSError):
                return {'source_url': source, 'error': '下载失败'}
    saved = await asyncio.gather(*(save(u) for u in urls))
    assets = [a for a in saved if 'local_url' in a]
    mapping = {a['source_url']: a['local_url'] for a in assets}
    for n in root.find_all(True):
        for attr in ('src', 'poster'):
            if n.get(attr) in mapping: n[attr] = mapping[n[attr]]
    failures = len(saved) - len(assets)
    fonts = [{'url': mapping[u], 'weight': 700 if 'bold' in u.lower() else 500 if 'medium' in u.lower() else 400} for u in parsed['font_urls'] if u in mapping]
    return {'version': 1, 'status': 'partial' if failures else 'complete', 'title': parsed['title'] or metadata.get('title', ''),
            'body_html': str(root), 'body_css': parsed['body_css'], 'text': parsed['text'], 'text_verified': bool(expected),
            'cover_url': mapping.get(parsed['cover_url'], parsed['cover_url']),
            'author_name': metadata.get('author_name', ''), 'author_handle': metadata.get('author_handle', ''),
            'author_avatar_url': mapping.get(metadata.get('author_avatar_url', ''), metadata.get('author_avatar_url', '')),
            'created_at': metadata.get('created_at', ''), 'source_url': url, 'fonts': fonts, 'assets': assets,
            'warnings': [f'{failures} 个资源未能保存到本地，当前仍使用原站链接。'] if failures else []}
