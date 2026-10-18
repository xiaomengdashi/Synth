import asyncio
import json

import pytest


def test_subtitle_parsers_preserve_dialogue_and_remove_cue_markup():
    from app.services.fetchers.video_platforms import parse_subtitles
    assert parse_subtitles('WEBVTT\n\n00:00:01.000 --> 00:00:02.000\n<c>Hello</c>\n\n00:00:02.000 --> 00:00:03.000\nHello world\n', 'vtt') == 'Hello world'
    assert parse_subtitles(json.dumps({'events': [{'segs': [{'utf8': '你好'}, {'utf8': '世界'}]}]}), 'json3') == '你好世界'
    assert parse_subtitles('<transcript><text start="0">A &amp; B</text></transcript>', 'xml') == 'A & B'


def test_youtube_short_and_watch_ids():
    from app.services.fetchers.video_platforms import youtube_id
    for url in ['https://youtu.be/BaW_jenozKc', 'https://www.youtube.com/watch?v=BaW_jenozKc', 'https://youtube.com/shorts/BaW_jenozKc']:
        assert youtube_id(url) == 'BaW_jenozKc'
    with pytest.raises(ValueError):
        youtube_id('https://youtube.com/@channel')


def test_video_priority_fallback_requires_real_transcript(monkeypatch):
    from app.services.fetchers import video_platforms as video
    calls = []
    def empty(url, config, step):
        calls.append('yt_dlp')
        return {'title': 'title', 'transcript_text': ''}
    def transcript(url, config, step):
        calls.append('tikhub')
        return {'title': 'title', 'transcript_text': '真正的视频文稿'}
    monkeypatch.setattr(video, 'fetch_ytdlp_video', empty)
    monkeypatch.setattr(video, 'fetch_tikhub_video', transcript)
    result = asyncio.run(video.fetch_platform_video('https://youtu.be/BaW_jenozKc', {}, lambda s: None))
    assert result['transcript_text'] == '真正的视频文稿'
    assert calls == ['yt_dlp', 'tikhub']



def test_ytdlp_subtitles_do_not_download_audio_or_call_asr(monkeypatch):
    from app.services.fetchers import video_platforms as video
    class YDL:
        def __init__(self, options): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def extract_info(self, url, download):
            assert download is False
            return {'title': '字幕视频', 'uploader': '作者', 'subtitles': {'en': [{'ext': 'vtt', 'url': 'https://media.example/sub.vtt'}]}}
    monkeypatch.setattr(video.yt_dlp, 'YoutubeDL', YDL)
    monkeypatch.setattr(video, 'read_subtitle_track', lambda *args: '已有字幕的完整正文')
    monkeypatch.setattr(video, 'download_ytdlp_transcript', lambda *a: pytest.fail('字幕可用时不能产生转写费用'))
    assert video.fetch_ytdlp_video('https://youtu.be/BaW_jenozKc', {}, lambda s: None)['transcript_text'] == '已有字幕的完整正文'



def test_video_network_options_use_configured_download_proxy():
    from app.services.fetchers.video_platforms import _ydl_options
    assert _ydl_options({'bilibiliProxy': 'http://127.0.0.1:7890'})['proxy'] == 'http://127.0.0.1:7890'


def test_empty_video_results_fail_instead_of_creating_description_only_article(monkeypatch):
    from app.services.fetchers import video_platforms as video
    monkeypatch.setattr(video, 'fetch_ytdlp_video', lambda *a: {'title': '标题', 'description': '只有简介'})
    monkeypatch.setattr(video, 'fetch_tikhub_video', lambda *a: {'title': '标题', 'transcript_text': ''})
    with pytest.raises(RuntimeError, match='有效字幕或转写'):
        asyncio.run(video.fetch_platform_video('https://youtu.be/BaW_jenozKc', {}, lambda s: None))



@pytest.mark.parametrize('url', ['https://www.youtube.com/@channel', 'https://www.youtube.com/playlist?list=abc'])
def test_channels_are_rejected_before_expanding_a_feed(monkeypatch, url):
    from app.services.fetchers import video_platforms as video
    def unexpected(*args):
        pytest.fail('必须在抓取前拒绝频道和用户主页，避免批量下载')
    monkeypatch.setattr(video, 'fetch_tikhub_video', unexpected)
    monkeypatch.setattr(video, 'fetch_ytdlp_video', unexpected)
    with pytest.raises(ValueError, match='具体'):
        asyncio.run(video.fetch_platform_video(url, {}, lambda s: None))
