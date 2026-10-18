"""YouTube ingestion: provider ordering, real captions, then audio ASR."""
import asyncio
import html
import json
import re
import shutil
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import yt_dlp
from bs4 import BeautifulSoup

from app.services.content_sources import detect_source_type
from app.services.fetch_priorities import PROVIDERS, resolve_priorities
from app.services.fetchers.bilibili_audio import (
    _audio_to_chunks, _minimax_stt, _resolve_minimax_bases, _resolve_bilibili_proxies, resolve_minimax_key,
)
from app.services.fetchers.tikhub import _tikhub_request, resolve_tikhub_token


def youtube_id(url: str) -> str:
    parsed = urlsplit(url)
    value = parsed.path.strip('/').split('/')[-1] if parsed.hostname in {'youtu.be', 'www.youtu.be'} or parsed.path.startswith(('/shorts/', '/embed/', '/live/')) else parse_qs(parsed.query).get('v', [''])[0]
    if not re.fullmatch(r'[A-Za-z0-9_-]{11}', value):
        raise ValueError('请提供具体的 YouTube 视频或 Shorts 链接。')
    return value


def parse_subtitles(content: str, extension: str) -> str:
    if extension == 'json3':
        data = json.loads(content)
        lines = [''.join(str(segment.get('utf8') or '') for segment in event.get('segs', [])) for event in data.get('events', [])]
    elif extension in {'xml', 'ttml'}:
        root = BeautifulSoup(content, 'xml')
        lines = [element.get_text(' ', strip=True) for element in root.find_all(['text', 'p'])]
    else:
        lines = []
        for line in content.splitlines():
            line = line.strip()
            if not line or '-->' in line or line.isdigit() or line.startswith(('WEBVTT', 'Kind:', 'Language:', 'NOTE', 'STYLE')):
                continue
            lines.append(re.sub(r'<[^>]*>', '', line))
    cleaned = []
    for line in lines:
        line = html.unescape(line).strip()
        if not line:
            continue
        if cleaned and line.startswith(cleaned[-1]):
            cleaned[-1] = line
        elif not cleaned or not cleaned[-1].endswith(line):
            cleaned.append(line)
    return '\n'.join(cleaned).strip()


def read_subtitle_track(track: dict, headers: dict | None = None, proxy: str | None = None) -> str:
    response = httpx.get(track['url'], headers=headers or {}, proxy=proxy, follow_redirects=True, timeout=25)
    response.raise_for_status()
    return parse_subtitles(response.text, track.get('ext', 'vtt'))


def _transcribe_file(raw: Path, workdir: Path, config: dict, step) -> str:
    key = resolve_minimax_key(config)
    chunks = _audio_to_chunks(raw, workdir)
    texts = []
    for index, chunk in enumerate(chunks, 1):
        step(f'正在转写视频语音（{index}/{len(chunks)}）…')
        texts.append(_minimax_stt(chunk, key, _resolve_minimax_bases(config)))
    text = '\n'.join(part for part in texts if part).strip()
    if not text:
        raise RuntimeError('视频转写结果为空，未保存空文稿。')
    return text


class _QuietLogger:
    def debug(self, *args): pass
    def warning(self, *args): pass
    def error(self, *args): pass


def _ydl_options(config: dict | None = None) -> dict:
    options = {'quiet': True, 'no_warnings': True, 'logger': _QuietLogger(), 'noplaylist': True,
               'socket_timeout': 20, 'retries': 1, 'extractor_retries': 1, 'skip_download': True}
    if shutil.which('node'):
        options['js_runtimes'] = {'node': {}}
    proxies = _resolve_bilibili_proxies(config)
    if len(proxies) > 1:
        options['proxy'] = proxies[-1]
    return options


def download_ytdlp_transcript(url: str, config: dict, step) -> str:
    resolve_minimax_key(config)
    with tempfile.TemporaryDirectory(prefix='synthai_video_') as directory:
        workdir = Path(directory)
        options = {**_ydl_options(config), 'skip_download': False, 'format': 'bestaudio/best',
                   'outtmpl': str(workdir / 'source.%(ext)s'), 'max_filesize': 256 * 1024 * 1024}
        step('无可用字幕，正在下载音频用于转写…')
        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.download([url])
        files = [path for path in workdir.glob('source.*') if path.suffix not in {'.part', '.ytdl'}]
        if not files:
            raise RuntimeError('未下载到可转写的音频，请检查视频权限及网络。')
        return _transcribe_file(files[0], workdir, config, step)


def fetch_ytdlp_video(url: str, config: dict, step) -> dict:
    step('正在通过 yt-dlp 读取视频与字幕…')
    options = _ydl_options(config)
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info or info.get('_type') in {'playlist', 'multi_video'} or info.get('is_live'):
        raise RuntimeError('请提供已发布的单个视频，暂不支持直播或播放列表。')
    transcript = ''
    for collection in (info.get('subtitles') or {}, info.get('automatic_captions') or {}):
        languages = sorted((lang for lang in collection if lang != 'live_chat'), key=lambda lang: (not lang.startswith('zh'), not lang.startswith('en'), lang))
        for language in languages[:3]:
            tracks = sorted(collection[language], key=lambda track: {'json3': 0, 'vtt': 1, 'srt': 2, 'ttml': 3}.get(track.get('ext'), 9))
            for track in tracks[:2]:
                try:
                    transcript = read_subtitle_track(track, info.get('http_headers'), options.get('proxy'))
                    if transcript:
                        step(f'已读取视频字幕（{language}）。')
                        break
                except (httpx.HTTPError, ValueError, KeyError):
                    continue
            if transcript:
                break
        if transcript:
            break
    if not transcript:
        transcript = download_ytdlp_transcript(url, config, step)
    chapters = '\n'.join(f"{chapter.get('start_time') or 0}s {chapter.get('title', '')}" for chapter in info.get('chapters') or [])
    return {'title': info.get('title') or '视频内容', 'description': info.get('description') or '',
            'uploader': info.get('uploader') or info.get('channel') or '', 'transcript_text': transcript,
            'cover_image_url': info.get('thumbnail') or '', 'publish_time': info.get('upload_date') or '',
            'chapter_info': chapters, 'bvid': ''}


def fetch_tikhub_video(url: str, config: dict, step) -> dict:
    token = resolve_tikhub_token(config)
    video_id = youtube_id(url)
    data = _tikhub_request('/api/v1/youtube/web_v2/get_video_info', token, params={'video_id': video_id})
    transcript = ''
    for language in ('zh-CN', 'en'):
        try:
            captions = _tikhub_request('/api/v1/youtube/web_v2/get_video_captions', token,
                                      params={'video_id': video_id, 'language_code': language, 'format': 'json3'})
            content = captions.get('content')
            if content:
                transcript = parse_subtitles(json.dumps(content) if isinstance(content, dict) else str(content), 'json3' if isinstance(content, dict) else captions.get('format', 'vtt'))
            if transcript:
                break
        except Exception:
            continue
    if not transcript:
        transcript = download_ytdlp_transcript(url, config, step)
    thumbs = data.get('thumbnails') or []
    return {'title': data.get('title') or 'YouTube 视频', 'description': data.get('description') or '',
            'uploader': data.get('author') or '', 'transcript_text': transcript,
            'cover_image_url': thumbs[-1].get('url', '') if thumbs else '', 'publish_time': data.get('publish_date') or '',
            'chapter_info': '', 'bvid': ''}


async def fetch_platform_video(url: str, config: dict, step) -> dict:
    platform = detect_source_type(url)
    if platform != 'youtube':
        raise ValueError('不支持的视频平台。')
    youtube_id(url)  # Reject channels/playlists before yt-dlp can expand them.
    errors = []
    for provider in resolve_priorities(config)[platform]:
        label = PROVIDERS[provider]['label']
        step(f'正在通过 {label} 获取视频正文…')
        try:
            fetch = fetch_tikhub_video if provider == 'tikhub' else fetch_ytdlp_video
            payload = await asyncio.to_thread(fetch, url, config, step)
            if not str(payload.get('transcript_text') or '').strip():
                raise RuntimeError('未获取到有效字幕或转写文稿。')
            return {**payload, 'provider_label': label}
        except Exception as exc:
            message = str(exc)
            for key in ('tikhubApiKey', 'minimaxApiKey', 'apiKey', 'twitterAuthToken', 'twitterCt0'):
                if config.get(key):
                    message = message.replace(str(config[key]), '[已隐藏]')
            errors.append(f'{label}：{message[:250]}')
    raise RuntimeError('视频正文获取失败；' + '；'.join(errors))
