"""Read X GraphQL through twitter-cli's Python runtime, emitting only article data."""
import json
import os
import sys


def explicit_cookies() -> dict:
    auth = os.environ.get('TWITTER_AUTH_TOKEN', '').strip()
    csrf = os.environ.get('TWITTER_CT0', '').strip()
    if not auth or not csrf:
        raise RuntimeError('Explicit Twitter credentials are required')
    return {'auth_token': auth, 'ct0': csrf}


def print_article_markdown(url: str) -> None:
    from twitter_cli import cli as cli_module
    # CLI's normal get_cookies retries with browser extraction after an auth
    # failure. Bind only explicit credentials, including for that failure path.
    cli_module.get_cookies = explicit_cookies
    cli_module.cli.main(args=['article', url, '--markdown'], prog_name='twitter')


def verify_login() -> dict:
    """Require an authenticated profile and expose only its display fields."""
    try:
        from twitter_cli.client import TwitterClient
        cookies = explicit_cookies()
        client = TwitterClient(cookies['auth_token'], cookies['ct0'], rate_limit_config={'maxRetries': 0})
        profile = client.fetch_me()
        if not getattr(profile, 'id', '') or not getattr(profile, 'screen_name', ''):
            return {'verified': False, 'reason': 'invalid_response'}
        return {'verified': True, 'account': {
            'name': str(getattr(profile, 'name', '') or ''),
            'screen_name': str(profile.screen_name),
        }}
    except ImportError:
        return {'verified': False, 'reason': 'runtime'}
    except Exception as exc:
        reason = {401: 'unauthorized', 403: 'forbidden', 429: 'rate_limited'}.get(getattr(exc, 'status_code', 0), 'network')
        return {'verified': False, 'reason': reason}


def fetch_tweet_result(tweet_id: str) -> dict:
    from twitter_cli.client import TwitterClient
    cookies = explicit_cookies()
    client = TwitterClient(cookies['auth_token'], cookies['ct0'])
    data = client._graphql_get('TweetResultByRestId',
        variables={'tweetId': tweet_id, 'withCommunity': False, 'includePromotedContent': False, 'withVoice': False},
        features={
            'longform_notetweets_consumption_enabled': True,
            'responsive_web_twitter_article_tweet_consumption_enabled': True,
            'longform_notetweets_rich_text_read_enabled': True,
            'longform_notetweets_inline_media_enabled': True,
            'articles_preview_enabled': True,
            'responsive_web_graphql_exclude_directive_enabled': True,
            'verified_phone_label_enabled': False,
        }, field_toggles={'withArticleRichContentState': True, 'withArticlePlainText': True})
    result = ((data.get('data') or {}).get('tweetResult') or {}).get('result')
    if isinstance(result, dict) and result.get('__typename') == 'TweetWithVisibilityResults':
        result = result.get('tweet')
    if not isinstance(result, dict):
        raise RuntimeError('TweetResultByRestId returned no tweet')
    return result


if __name__ == '__main__':
    try:
        if sys.argv[1] == '--verify':
            print(json.dumps(verify_login()))
        elif sys.argv[1] == '--markdown':
            print_article_markdown(sys.argv[2])
        else:
            print(json.dumps({'tweet_result': fetch_tweet_result(sys.argv[1])}, ensure_ascii=False))
    except Exception:
        sys.exit(1)
