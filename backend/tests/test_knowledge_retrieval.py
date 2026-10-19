import json

from app.services import knowledge_retrieval as retrieval


def test_platform_bodies_extract_without_scripts_or_markers():
    cases = [
        '<!-- HTML_CONTENT_START --><p>可检索正文</p><script>secret()</script><style>.noise{}</style><!-- HTML_CONTENT_END -->',
        '<!-- X_ARTICLE_START -->' + json.dumps({'body_html': '<p>可检索正文</p><script>secret()</script>'}) + '<!-- X_ARTICLE_END -->',
        '<!-- X_CONTENT_START -->' + json.dumps({'tweet_text': '可检索正文'}) + '<!-- X_CONTENT_END -->',
        '## 内容摘要\n\n不应代替全文\n\n---\n\n可检索正文',
    ]
    for content in cases:
        result = retrieval.extract_search_text(content)
        assert '可检索正文' in result
        assert 'secret' not in result and '.noise' not in result and 'START' not in result


def test_corrupt_payload_has_no_summary_substitute():
    assert retrieval.extract_search_text('<!-- X_ARTICLE_START -->broken<!-- X_ARTICLE_END -->') == ''


def test_chunks_preserve_tail_and_respect_budget():
    body = '开篇。' + ''.join(f'第{i}段知识检索需要完整保留。' for i in range(2000)) + '尾部独有证据'
    chunks = retrieval.split_chunks(body)
    assert all(0 < len(c) <= 1200 for c in chunks)
    assert '尾部独有证据' in chunks[-1]
    assert len(chunks) > 10


def test_tokens_match_chinese_and_english():
    assert '缓存' in retrieval.tokenize('如何使用缓存', query=True)
    assert 'kv' in retrieval.tokenize('KV Cache')
    assert '字' in retrieval.tokenize('字', query=True)


def test_query_operators_are_literal_and_tokens_bounded():
    tokens = retrieval.tokenize(' '.join(f'term{i}' for i in range(100)), query=True)
    assert len(tokens) <= 48
    expression = retrieval.build_match_query(['hello" OR *', '缓存'])
    assert expression == '"hello"" OR *" OR "缓存"'
