"""Render Draft.js article JSON into the library reader with local media."""
import asyncio
import hashlib
import html
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from bs4 import BeautifulSoup

from app.config import settings
from app.services.fetchers.twitter_article_rich import _normalize_entity_map
from app.services.fetchers.x_article import _allowed_url, _read, ASSET_HOSTS, EXTENSIONS
from app.services.fetchers.social import extract_x_tweet_id


def _atomic_write(path: Path, data: bytes):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _utf16_span(text, offset, length):
    units = text.encode('utf-16-le')
    start = max(0, min(int(offset), len(units) // 2))
    end = max(start, min(start + max(0, int(length)), len(units) // 2))
    return (len(units[:start * 2].decode('utf-16-le', errors='ignore')),
            len(units[:end * 2].decode('utf-16-le', errors='ignore')))


def _inline(block, entities):
    text = str(block.get('text') or '')
    styles = [set() for _ in text]
    links = ['' for _ in text]
    for item in block.get('inlineStyleRanges') or []:
        if not isinstance(item, dict):
            continue
        try:
            start, end = _utf16_span(text, item.get('offset', 0), item.get('length', 0))
        except (TypeError, ValueError):
            continue
        for index in range(start, end):
            styles[index].add(str(item.get('style') or '').upper())
    for item in block.get('entityRanges') or []:
        entity = entities.get(str(item.get('key')), {})
        href = (entity.get('data') or {}).get('url', '')
        try:
            safe = urlsplit(href)
            if entity.get('type') != 'LINK' or safe.scheme not in {'http', 'https'} or safe.username or safe.password:
                continue
            start, end = _utf16_span(text, item.get('offset', 0), item.get('length', 0))
        except (TypeError, ValueError):
            continue
        for index in range(start, end):
            links[index] = href
    chunks = []
    i = 0
    while i < len(text):
        j = i + 1
        while j < len(text) and styles[j] == styles[i] and links[j] == links[i]:
            j += 1
        chunk = html.escape(text[i:j]).replace('\n', '<br>')
        for style, tag in [('CODE', 'code'), ('BOLD', 'strong'), ('ITALIC', 'em'), ('UNDERLINE', 'u'), ('STRIKETHROUGH', 's')]:
            if style in styles[i]:
                chunk = f'<{tag}>{chunk}</{tag}>'
        if links[i]:
            chunk = f'<a href="{html.escape(links[i], quote=True)}" target="_blank" rel="noopener noreferrer">{chunk}</a>'
        chunks.append(chunk)
        i = j
    return ''.join(chunks)


def render_draft_html(article: dict, media: dict) -> tuple[str, list[str]]:
    soup = BeautifulSoup('<div class="x-article-body"><div class="contents"></div></div>', 'html.parser')
    root = soup.select_one('.contents')
    entities = _normalize_entity_map((article.get('content_state') or {}).get('entityMap'))
    lists = []
    warnings = []
    for block in (article.get('content_state') or {}).get('blocks') or []:
        if not isinstance(block, dict):
            continue
        kind = block.get('type') or 'unstyled'
        if kind not in {'unordered-list-item', 'ordered-list-item'}:
            lists = []
        if kind == 'atomic':
            rendered = False
            for span in block.get('entityRanges') or []:
                entity = entities.get(str(span.get('key')), {})
                if entity.get('type') == 'MARKDOWN':
                    pre = soup.new_tag('pre')
                    pre.string = str((entity.get('data') or {}).get('markdown') or '')
                    root.append(pre)
                    rendered = True
                for item in (entity.get('data') or {}).get('mediaItems') or []:
                    entry = media.get(str(item.get('mediaId')), {})
                    figure = soup.new_tag('figure')
                    if entry.get('src'):
                        if entry['kind'] == 'video':
                            node = soup.new_tag('video', src=entry['src'], controls='', muted='', playsinline='', preload='metadata')
                            if entry.get('gif'):
                                node['autoplay'], node['loop'] = '', ''
                            if entry.get('poster'):
                                node['poster'] = entry['poster']
                        else:
                            node = soup.new_tag('img', src=entry['src'], alt='文章插图', loading='lazy')
                        figure.append(node)
                    else:
                        figure.string = '媒体未能保存到本地'
                        warnings.append('正文媒体缺失或下载失败')
                    root.append(figure)
                    rendered = True
            if not rendered:
                warnings.append('存在无法解析的 atomic 内容块')
                placeholder = soup.new_tag('p')
                placeholder.string = '此内容块未能解析'
                root.append(placeholder)
            continue
        fragment = _inline(block, entities)
        if kind in {'unordered-list-item', 'ordered-list-item'}:
            tag = 'ul' if kind == 'unordered-list-item' else 'ol'
            depth = max(0, min(int(block.get('depth') or 0), 8))
            depth = min(depth, len(lists))
            lists = lists[:depth + 1]
            if len(lists) <= depth or lists[depth].name != tag:
                parent = root if depth == 0 else lists[depth - 1].find_all('li', recursive=False)[-1]
                node = soup.new_tag(tag)
                parent.append(node)
                lists = lists[:depth] + [node]
            node = soup.new_tag('li')
            for child in list(BeautifulSoup('<span>' + fragment + '</span>', 'html.parser').span.contents):
                node.append(child)
            lists[-1].append(node)
        else:
            tag = {'header-one': 'h2', 'header-two': 'h2', 'header-three': 'h3', 'header-four': 'h4',
                   'header-five': 'h5', 'header-six': 'h6', 'blockquote': 'blockquote', 'code-block': 'pre'}.get(kind, 'p')
            node = soup.new_tag(tag)
            for child in list(BeautifulSoup('<span>' + fragment + '</span>', 'html.parser').span.contents):
                node.append(child)
            root.append(node)
    return str(soup), list(dict.fromkeys(warnings))


def _media_descriptor(entity):
    info = entity.get('media_info') or {}
    variants = [v for v in info.get('variants') or [] if isinstance(v, dict) and v.get('content_type') == 'video/mp4'
                and _allowed_url(str(v.get('url') or ''), ASSET_HOSTS)]
    if variants:
        best = max(variants, key=lambda v: v.get('bit_rate') or v.get('bitrate') or 0)
        return {'kind': 'video', 'source': best['url'], 'poster': (info.get('preview_image') or {}).get('original_img_url', ''),
                'gif': info.get('__typename') == 'ApiGif'}
    return {'kind': 'image', 'source': info.get('original_img_url') or info.get('media_url_https') or '', 'poster': ''}


async def build_graphql_article(article: dict, metadata: dict, url: str, update_step, *, client=None, media_dir=None) -> dict:
    tweet_id = extract_x_tweet_id(url)
    if not tweet_id:
        raise RuntimeError('生成文章需要有效推文 ID')
    if not (article.get('content_state') or {}).get('blocks'):
        raise RuntimeError('没有可渲染的文章正文块')
    if client is None:
        async with httpx.AsyncClient(timeout=30) as owned:
            return await build_graphql_article(article, metadata, url, update_step, client=owned, media_dir=media_dir)
    update_step('正在下载 GraphQL 文章图片、GIF 和封面...')
    directory = Path(media_dir or settings.MEDIA_DIR) / 'x' / tweet_id
    media_directory = directory / 'media'
    media_directory.mkdir(parents=True, exist_ok=True)
    prefix = f'/media/x/{tweet_id}/'
    descriptors = {}
    for entity in article.get('media_entities') or []:
        if not isinstance(entity, dict):
            continue
        item = _media_descriptor(entity)
        for key in ('media_id', 'media_key', 'id'):
            if entity.get(key) is not None:
                descriptors[str(entity[key])] = item
    cover = _media_descriptor(article.get('cover_media') or {})['source']
    avatar = str(metadata.get('author_avatar_url') or '')
    sources = list(dict.fromkeys([value for d in descriptors.values() for value in (d['source'], d['poster']) if value] + [s for s in (cover, avatar) if s]))
    if len(sources) > 80:
        raise RuntimeError('文章媒体数量超过限制')
    semaphore = asyncio.Semaphore(4)
    budget = 0
    async def save(source):
        nonlocal budget
        async with semaphore:
            try:
                data, mime = await _read(client, source, ASSET_HOSTS, 30 * 1024 * 1024)
                extension = EXTENSIONS.get(mime)
                if not extension or not mime.startswith(('image/', 'video/')) or not data:
                    raise ValueError('无效媒体格式')
                budget += len(data)
                if budget > 200 * 1024 * 1024:
                    raise ValueError('文章媒体总大小超过限制')
                name = hashlib.sha256(data).hexdigest() + extension
                _atomic_write(media_directory / name, data)
                return {'source_url': source, 'local_url': prefix + 'media/' + name, 'bytes': len(data), 'content_type': mime}
            except (httpx.HTTPError, ValueError, OSError):
                return {'source_url': source, 'error': '媒体下载失败'}
    saved = await asyncio.gather(*(save(source) for source in sources))
    assets = [asset for asset in saved if 'local_url' in asset]
    mapping = {asset['source_url']: asset['local_url'] for asset in assets}
    media = {key: {**item, 'src': mapping.get(item['source'], ''), 'poster': mapping.get(item['poster'], '')} for key, item in descriptors.items()}
    body, warnings = render_draft_html(article, media)
    failures = len(saved) - len(assets)
    if failures:
        warnings.insert(0, f'{failures} 个媒体资源下载失败')
    text = '\n\n'.join(str(block.get('text') or '') for block in article['content_state']['blocks']
                       if isinstance(block, dict) and block.get('type') != 'atomic').strip()
    if not text.strip():
        raise RuntimeError('文章正文为空')
    result = {'version': 1, 'status': 'partial' if warnings else 'complete', 'title': article.get('title') or metadata.get('title', ''),
              'body_html': body, 'body_css': '', 'text': text, 'text_verified': True, 'source_url': url,
              'cover_url': mapping.get(cover, ''), 'author_name': metadata.get('author_name', ''),
              'author_handle': metadata.get('author_handle', ''), 'author_avatar_url': mapping.get(avatar, ''),
              'created_at': metadata.get('created_at', ''), 'assets': assets, 'fonts': [], 'warnings': warnings}
    update_step('Draft.js 正文与本地媒体已整理，正在保存到文章库...')
    return result
