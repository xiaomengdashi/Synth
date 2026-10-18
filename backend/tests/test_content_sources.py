import pytest

from app.services.task_service import detect_source_type


@pytest.mark.parametrize('url,source', [
    ('https://youtu.be/BaW_jenozKc', 'youtube'),
    ('https://www.youtube.com/shorts/BaW_jenozKc', 'youtube'),
    ('https://blog.csdn.net/author/article/details/123', 'csdn'),
    ('https://www.cnblogs.com/author/p/123.html', 'cnblogs'),
    ('https://example.com/?next=https://x.com/author/status/123', 'other'),
    ('https://youtube.com.evil.test/watch?v=abc', 'other'),
])
def test_source_detection_uses_hostname(url, source):
    assert detect_source_type(url) == source


def test_new_sources_are_in_priority_configuration():
    from app.services.fetch_priorities import priority_view
    platforms = priority_view({})['platforms']
    assert {'csdn', 'cnblogs', 'web', 'youtube'} <= platforms.keys()
    assert platforms['youtube']['providers'] == ['yt_dlp', 'tikhub']


@pytest.mark.parametrize('url', [
    'https://youtu.be/BaW_jenozKc',
    'https://blog.csdn.net/u/article/details/123', 'https://www.cnblogs.com/u/p/123.html',
    'https://docs.python.org/3/tutorial/',
])
def test_new_platforms_can_be_received_from_phone_share(url):
    from app.services.share_import import extract_shared_url
    identity, normalized = extract_shared_url(url)
    assert identity and normalized.startswith('https://')
