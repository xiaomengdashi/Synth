"""Read X's web GraphQL operation directly; no CLI or yt-dlp dependency."""
import json
import re
from urllib.parse import urlsplit

import httpx

from app.services.twitter_cli_settings import resolve_twitter_cli
from app.services.fetchers.social import TWEET_HOSTS, extract_x_tweet_id
from app.services.fetchers.tikhub import normalize_tikhub_tweet_result

# Public web application bearer, not a user's API key or account credential.
PUBLIC_WEB_BEARER = 'AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA'
QUERY_ID = '7xflPyRiUxGVbJd4uWmbfg'
FEATURES = {
    'longform_notetweets_consumption_enabled': True,
    'responsive_web_twitter_article_tweet_consumption_enabled': True,
    'longform_notetweets_rich_text_read_enabled': True,
    'longform_notetweets_inline_media_enabled': True,
    'articles_preview_enabled': True,
    'responsive_web_graphql_exclude_directive_enabled': True,
    'verified_phone_label_enabled': False,
}


async def _refresh_query_id(client):
    """Refresh a stale public operation ID from X's own web application bundle."""
    from app.services.fetchers.x_article import _read, PAGE_HOSTS
    page, _ = await _read(client, 'https://x.com/', PAGE_HOSTS, 4 * 1024 * 1024)
    scripts = re.findall(r'https://abs\.twimg\.com/responsive-web/client-web(?:-legacy)?/main\.[\w-]+\.js', page.decode(errors='replace'))
    if not scripts:
        raise RuntimeError('X GraphQL 接口标识已变化，无法从 X 网页更新，请稍后重试')
    raw, _ = await _read(client, scripts[0], {'abs.twimg.com'}, 10 * 1024 * 1024)
    match = re.search(r'queryId:"([\w-]+)",operationName:"TweetResultByRestId"', raw.decode(errors='replace'))
    if not match:
        raise RuntimeError('X GraphQL 接口标识已变化，请稍后重试')
    return match[1]


async def fetch_x_via_graphql(url: str, update_step, config: dict | None = None, *, client=None) -> dict:
    parsed = urlsplit(url)
    tweet_id = extract_x_tweet_id(url)
    if (parsed.scheme not in {'https', 'http'} or parsed.hostname not in TWEET_HOSTS or not tweet_id
            or parsed.username or parsed.password or parsed.port not in {None, 80, 443}):
        raise RuntimeError('X GraphQL 需要宿主推文链接')
    credentials = resolve_twitter_cli(config)
    if not credentials['auth'] or not credentials['csrf']:
        raise RuntimeError('X GraphQL 需要登录态，请在「X 登录配置」保存 auth_token 和 ct0')
    if client is None:
        async with httpx.AsyncClient(timeout=30) as owned:
            return await fetch_x_via_graphql(url, update_step, config, client=owned)
    update_step('正在通过 X GraphQL 获取完整文章 JSON...')
    headers = {'authorization': 'Bearer ' + PUBLIC_WEB_BEARER,
               'x-csrf-token': credentials['csrf'], 'x-twitter-auth-type': 'OAuth2Session',
               'x-twitter-active-user': 'yes', 'user-agent': 'Mozilla/5.0',
               'cookie': f'auth_token={credentials["auth"]}; ct0={credentials["csrf"]}'}
    params = {
        'variables': json.dumps({'tweetId': tweet_id, 'withCommunity': False, 'includePromotedContent': False, 'withVoice': False}),
        'features': json.dumps(FEATURES),
        'fieldToggles': json.dumps({'withArticleRichContentState': True, 'withArticlePlainText': True}),
    }
    query_id = QUERY_ID
    try:
        for attempt in range(2):
            response = await client.get(f'https://x.com/i/api/graphql/{query_id}/TweetResultByRestId',
                                        params=params, headers=headers,
                                        follow_redirects=False)
            if response.status_code in {404, 422} and attempt == 0:
                query_id = await _refresh_query_id(client)
                continue
            if response.status_code in {401, 403}:
                raise RuntimeError('X GraphQL 登录态失效或访问被拒绝，请重新验证 X 登录态')
            if response.status_code == 429:
                raise RuntimeError('X GraphQL 请求受到频率限制，请稍后重试')
            response.raise_for_status()
            if len(response.content) > 8 * 1024 * 1024:
                raise RuntimeError('X GraphQL 返回数据超过大小限制')
            data = response.json()
            break
    except (httpx.HTTPError, ValueError):
        raise RuntimeError('X GraphQL 获取失败，请检查网络、登录态或原文可见性') from None
    result = ((data.get('data') or {}).get('tweetResult') or {}).get('result')
    if isinstance(result, dict) and result.get('__typename') == 'TweetWithVisibilityResults':
        result = result.get('tweet')
    if not isinstance(result, dict) or str(result.get('rest_id') or '') != tweet_id:
        raise RuntimeError('X GraphQL 未返回匹配的推文，原文可能已删除或不可见')
    article = ((result.get('article') or {}).get('article_results') or {}).get('result')
    payload = normalize_tikhub_tweet_result(result)
    if article is not None:
        if not isinstance(article, dict) or not any(isinstance(b, dict) and str(b.get('text') or '').strip()
                                                   for b in (article.get('content_state') or {}).get('blocks', [])):
            raise RuntimeError('X GraphQL 未返回长文正文块，不能把标题或预览当作完整文章')
        payload['title'] = article.get('title') or payload['title']
    elif payload.get('article_preview') or not payload.get('tweet_text', '').strip():
        raise RuntimeError('X GraphQL 未返回完整正文')
    return {'payload': payload, 'article_result': article, 'article_text': None}
