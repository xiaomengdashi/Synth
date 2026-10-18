"""Removed platforms cannot be imported or queried through generic fallbacks."""
import asyncio
import pytest
from app.services.content_sources import SOURCE_IDS, detect_source_type
from app.services.fetch_priorities import resolve_priorities
from app.services.fetchers.article import fetch_article_content
from app.services.share_import import extract_shared_url
from app.services.tikhub_queries import query_catalog

URLS = ['https://www.douyin.com/video/123', 'https://v.douyin.com/abc/', 'https://www.iesdouyin.com/share/video/123']

@pytest.mark.parametrize('url', URLS)
def test_removed_platform_is_not_accepted_as_a_generic_webpage(url):
    with pytest.raises(ValueError, match='不支持'):
        detect_source_type(url)
    with pytest.raises(ValueError):
        extract_shared_url(url)

def test_removed_platform_article_fetch_stops_before_network():
    with pytest.raises(ValueError, match='不支持'):
        asyncio.run(fetch_article_content(URLS[0], lambda _: None))

def test_removed_platform_is_absent_from_sources_priorities_and_query_catalog():
    assert 'douyin' not in SOURCE_IDS
    assert 'douyin' not in resolve_priorities({'fetchProviderPriorities': '{"douyin":["tikhub"]}'})
    catalog = query_catalog('', '', 0, 1000)
    assert all(platform['id'] not in {'douyin', 'hybrid'} for platform in catalog['platforms'])
    assert all('/douyin/' not in item['path'] and '/hybrid/' not in item['path'] for item in catalog['items'])
