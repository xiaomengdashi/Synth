"""Platform-neutral article text and Chinese/English lexical retrieval."""
from dataclasses import dataclass
import re

from bs4 import BeautifulSoup

from app.services.note_export import extract_note_body


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: int
    article_id: str
    title: str
    source_type: str
    text: str
    article_updated_at: str


_TOKEN = re.compile(r'[\u3400-\u9fff]+|[a-zA-Z0-9_]+')
_STOP = {'the', 'a', 'an', 'is', 'are', 'what', 'how', 'why', 'which', 'in', 'of', 'to', 'and', 'it', 'this', 'that', 'about', 'please'}
_PHRASES = ('知识库', '文章', '资料', '什么', '哪些', '怎么', '如何', '是否', '请问', '详细', '讲讲', '解释', '说明', '介绍', '帮我', '根据', '可以', '相关', '有关', '一下', '再讲', '展开', '这些', '这个', '我的', '收藏')


def extract_search_text(content_md: str) -> str:
    clean = re.sub(r'<(script|style)\b[^>]*>[\s\S]*?</\1\s*>', '', content_md or '', flags=re.I)
    body = extract_note_body(clean)
    soup = BeautifulSoup(body, 'html.parser')
    for node in soup(['script', 'style']):
        node.decompose()
    body = soup.get_text('\n')
    body = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', body)
    body = re.sub(r'https?://\S+', '', body)
    body = re.sub(r'<!--.*?-->', '', body, flags=re.S)
    body = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\u200b-\u200f\ufeff]', '', body)
    return re.sub(r'\n{3,}', '\n\n', body).strip()


def split_chunks(text: str) -> list[str]:
    text = text.strip()
    chunks, seen = [], set()
    start = 0
    while start < len(text):
        end = min(start + 900, len(text))
        if end < len(text):
            boundaries = [text.rfind(c, start + 450, end) for c in ('\n', '。', '. ', '！', '？')]
            boundary = max(boundaries)
            if boundary > start:
                end = boundary + 1
        piece = text[start:end].strip()
        if piece and piece not in seen:
            chunks.append(piece)
            seen.add(piece)
        if end == len(text):
            break
        start = max(start + 1, end - 120)
    return chunks


def tokenize(text: str, *, query: bool = False) -> list[str]:
    original = text.strip()
    if query:
        for phrase in sorted(_PHRASES, key=len, reverse=True):
            text = text.replace(phrase, ' ')
    tokens = []
    for part in _TOKEN.findall(text.lower()):
        if '\u3400' <= part[0] <= '\u9fff':
            if not query or len(original) == 1:
                tokens.extend(part)
            tokens.extend(part[i:i + 2] for i in range(len(part) - 1))
        elif not query or part not in _STOP:
            tokens.append(part)
    result = list(dict.fromkeys(tokens))
    return result[:48] if query else result


def build_match_query(tokens: list[str]) -> str:
    return ' OR '.join('"' + token.replace('"', '""') + '"' for token in tokens[:48] if token)


async def retrieve_chunks(db, question: str, *, previous_questions: list[str], previous_article_ids: list[str]) -> list[RetrievedChunk]:
    from sqlalchemy import text

    tokens = tokenize(question, query=True)
    # Generic follow-ups reuse the topic; explicit new topics never fall back to unrelated history.
    if not tokens:
        tokens = tokenize(' '.join(previous_questions[-2:]), query=True)
    expression = build_match_query(tokens)
    if not expression:
        await db.commit()
        return []
    rows = (await db.execute(text('''
        SELECT c.id AS chunk_id,c.article_id,c.text,a.title,a.source_type,i.article_updated_at,
               bm25(knowledge_chunks_fts,4.0,1.0) AS score
        FROM knowledge_chunks_fts
        JOIN knowledge_chunks c ON c.id=knowledge_chunks_fts.rowid
        JOIN articles a ON a.id=c.article_id
        JOIN knowledge_indexed_articles i ON i.article_id=c.article_id
        WHERE knowledge_chunks_fts MATCH :query
        ORDER BY score,c.id LIMIT 60
    '''), {'query': expression})).mappings().all()
    await db.commit()
    # Round-robin articles so a long single source cannot crowd out other evidence.
    groups = {}
    for row in rows:
        groups.setdefault(row['article_id'], []).append(row)
    selected, seen, budget = [], set(), 14400
    for position in range(3):
        for group in groups.values():
            if position >= len(group):
                continue
            row = group[position]
            if row['text'] in seen or len(row['text']) > budget:
                continue
            selected.append(RetrievedChunk(**{key: row[key] for key in RetrievedChunk.__dataclass_fields__}))
            seen.add(row['text'])
            budget -= len(row['text'])
            if len(selected) == 12:
                return selected
    return selected
