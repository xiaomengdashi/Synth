"""Source identifiers shared by importing, statistics and platform dispatch."""
from urllib.parse import urlsplit

SOURCE_DOMAINS = {
    'wechat': ('mp.weixin.qq.com',), 'x': ('x.com', 'twitter.com'),
    'bilibili': ('bilibili.com', 'b23.tv'),
    'youtube': ('youtube.com', 'youtu.be'), 'csdn': ('csdn.net',), 'cnblogs': ('cnblogs.com',),
}
SOURCE_IDS = (*SOURCE_DOMAINS, 'other')


def detect_source_type(url: str) -> str:
    try:
        host = (urlsplit(str(url).strip()).hostname or '').lower()
    except ValueError:
        return 'other'
    if any(host == domain or host.endswith('.' + domain) for domain in ('douyin.com', 'iesdouyin.com')):
        raise ValueError('不支持此平台链接。')
    for source, domains in SOURCE_DOMAINS.items():
        if any(host == domain or host.endswith('.' + domain) for domain in domains):
            return source
    return 'other'
