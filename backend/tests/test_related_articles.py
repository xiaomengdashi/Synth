import asyncio
import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.models import Article
from app.routers import articles
from app.services import runtime_store
from app.services.related_articles import build_related, char_bigrams, fetch_related


@pytest.fixture
def related_client(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'related.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def prepare():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(prepare())

    async def database():
        async with sessions() as session:
            yield session

    # articles.py 在 import 时已绑定 ARTICLES_DB 名称,隔离内存兜底须 patch 使用方模块属性
    monkeypatch.setattr(runtime_store, "ARTICLES_DB", {})
    monkeypatch.setattr(articles, "ARTICLES_DB", runtime_store.ARTICLES_DB)
    app = FastAPI()
    app.include_router(articles.router, prefix="/api/v1/articles")
    app.dependency_overrides[get_db] = database
    with TestClient(app) as client:
        yield client, sessions
    asyncio.run(engine.dispose())


def seed(sessions, article_id, title="文章标题", summary="摘要内容", category=None, created_days_ago=0):
    values = {
        "id": article_id,
        "title": title,
        "summary": summary,
        "content_md": "正文",
        "original_url": f"https://example.com/{article_id}",
        "source_type": "other",
        "category": category,
    }

    async def save():
        async with sessions() as session:
            if created_days_ago is None:
                # ORM 对显式 None 仍应用列 default(实测存入 now()),Core insert 才能存真 NULL(回归该路径)
                await session.execute(Article.__table__.insert().values(**values, created_at=None))
            else:
                session.add(Article(
                    **values,
                    created_at=datetime.datetime(2026, 10, 1) - datetime.timedelta(days=created_days_ago),
                ))
            await session.commit()

    asyncio.run(save())


def make_article(article_id, title="文章标题", summary="摘要内容", category=None, created_days_ago=0):
    return Article(
        id=article_id,
        title=title,
        summary=summary,
        content_md="正文",
        original_url=f"https://example.com/{article_id}",
        source_type="other",
        category=category,
        created_at=datetime.datetime(2026, 10, 1) - datetime.timedelta(days=created_days_ago),
    )


# ---------- char_bigrams 纯函数 ----------

def test_char_bigrams_strips_whitespace_lowers_and_dedupes():
    assert char_bigrams("你好") == {"你好"}
    # 去空白:a b → ab 只剩一对;lower 让大小写归一
    assert char_bigrams("  A\nb ") == {"ab"}
    # 相邻对 + 集合去重:abcabc → ab/bc/ca
    assert char_bigrams("abcabc") == {"ab", "bc", "ca"}
    # 单字符/空串无相邻对
    assert char_bigrams("字") == set()
    assert char_bigrams("") == set()


def test_char_bigrams_limit_truncates_before_pairing():
    assert char_bigrams("abcdefgh", limit=3) == {"ab", "bc"}


# ---------- build_related 纯函数 ----------

def test_same_category_weight_beats_slightly_lower_title_overlap():
    target = make_article("t", title="深度学习的实践指南", category="科技")
    same = make_article("same", title="深度学习的实践", category="科技", created_days_ago=9)
    other = make_article("other", title="深度学习的实践指南啊", category="生活", created_days_ago=1)
    ranked = build_related(target, [other, same])
    # other 标题重合略高,但 2.0 的同分类加权让 same 胜出
    assert ranked[0].id == "same"


def test_higher_title_overlap_ranks_first():
    target = make_article("t", title="SQLite 性能调优实录", category="科技")
    similar = make_article("similar", title="SQLite 性能调优心得", category="科技", created_days_ago=9)
    unlike = make_article("unlike", title="周末骑行路线分享", category="科技", created_days_ago=1)
    ranked = build_related(target, [unlike, similar])
    assert ranked[0].id == "similar"


def test_build_related_excludes_self():
    target = make_article("t", title="SQLite 性能调优实录", category="科技")
    self_like = make_article("t", title="SQLite 性能调优实录", category="科技")
    other = make_article("o", title="完全无关的另一篇", category="生活", created_days_ago=1)
    ranked = build_related(target, [self_like, other])
    assert all(item.id != "t" for item in ranked)


def test_ties_break_by_newer_created_at():
    target = make_article("t", title="标题", category="科技")
    older = make_article("older", title="候选甲", category="科技", created_days_ago=5)
    newer = make_article("newer", title="候选乙", category="科技", created_days_ago=1)
    ranked = build_related(target, [older, newer])
    assert [item.id for item in ranked] == ["newer", "older"]


# ---------- fetch_related / 端点 ----------

def test_fetch_related_fills_with_latest_when_category_pool_short(related_client):
    _, sessions = related_client
    seed(sessions, "t", title="目标文章", category="科技", created_days_ago=0)
    seed(sessions, "same-cat", title="同分类仅此一篇", category="科技", created_days_ago=9)
    for index in range(1, 5):
        seed(sessions, f"fill-{index}", title=f"其他分类补位 {index}", category="生活", created_days_ago=index)

    async def run():
        async with sessions() as session:
            return await fetch_related(session, "t")

    rows = asyncio.run(run())
    assert [row["id"] for row in rows] == ["same-cat", "fill-1", "fill-2", "fill-3", "fill-4"]


def test_uncategorized_article_pulls_candidates_from_uncategorized_pool(related_client):
    """回归:直接 == None 生成永不匹配的 WHERE,会让未分类的同分类加分静默失效。"""
    _, sessions = related_client
    # 未分类池两篇(created 更旧、标题与目标不同),其他分类三篇(created 更新
    seed(sessions, "t", title="未分类目标", created_days_ago=0)
    seed(sessions, "u1", title="未分类之一", created_days_ago=8)
    seed(sessions, "u2", title="未分类之二", created_days_ago=9)
    for index in range(1, 4):
        seed(sessions, f"c-{index}", title=f"别的分类 {index}", category="生活", created_days_ago=index)

    async def run():
        async with sessions() as session:
            return await fetch_related(session, "t")

    rows = asyncio.run(run())
    ids = [row["id"] for row in rows]
    # 未分类池命中候选:u1/u2 拿同分类加权排前两位;若 SQL 退化匹配 0 行,
    # 补位全按 created_at 排序,更新的 c-3/c-2 会排在前——此断言即失败
    assert set(ids[:2]) == {"u1", "u2"}
    assert set(ids[2:]) == {"c-3", "c-2", "c-1"}


def test_fetch_related_returns_empty_when_only_article_in_db(related_client):
    client, sessions = related_client
    seed(sessions, "only", title="孤本")
    response = client.get("/api/v1/articles/only/related")
    assert response.status_code == 200
    assert response.json() == {"data": []}


def test_related_endpoint_returns_projection_rows(related_client):
    client, sessions = related_client
    seed(sessions, "t", title="目标文章标题", category="科技", created_days_ago=0)
    seed(sessions, "rel", title="目标文章标题续篇", category="科技", created_days_ago=1)

    response = client.get("/api/v1/articles/t/related")
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["id"] == "rel"
    assert set(data[0].keys()) == {
        "id", "title", "summary", "source_type", "category",
        "cover_image_url", "account_name", "publish_time", "created_at",
    }


def test_related_endpoint_404_for_unknown_id(related_client):
    client, _ = related_client
    assert client.get("/api/v1/articles/nope/related").status_code == 404


def test_null_created_at_candidate_does_not_crash_and_ranks_last(related_client):
    """回归:created_at 列可空,排序键若走 .timestamp() 会因 year 0 哨兵抛 ValueError。"""
    _, sessions = related_client
    seed(sessions, "t", title="目标文章", category="科技", created_days_ago=0)
    seed(sessions, "dated", title="有日期候选", category="科技", created_days_ago=1)
    seed(sessions, "null-date", title="无日期候选", category="科技", created_days_ago=None)

    async def run():
        async with sessions() as session:
            return await fetch_related(session, "t")

    rows = asyncio.run(run())
    # 两篇分数并列(同分类+摘要同、标题不重合),NULL 日期按最旧垫底
    assert [row["id"] for row in rows] == ["dated", "null-date"]


def test_candidate_window_truncates_oldest_same_category_rows(related_client):
    """同分类候选只取最新 30 篇:窗口外更旧的文章即使标题高重合也不进结果。"""
    _, sessions = related_client
    seed(sessions, "t", title="目标文章标题", category="科技", created_days_ago=0)
    # 30 篇窗口内的普通候选 + 第 31 篇最旧但标题与目标高重合
    for index in range(1, 31):
        seed(sessions, f"f-{index}", title=f"科技杂谈第{index}篇", category="科技", created_days_ago=index)
    seed(sessions, "f-31", title="目标文章标题续写", category="科技", created_days_ago=99)

    async def run():
        async with sessions() as session:
            return await fetch_related(session, "t")

    rows = asyncio.run(run())
    ids = [row["id"] for row in rows]
    assert "f-31" not in ids
    assert ids == [f"f-{index}" for index in range(1, 6)]


def test_global_filler_can_outrank_same_category_on_title_overlap(related_client):
    """钉死权重取舍:标题重合 3.0 权重高于同分类 2.0,跨分类强相关可反超弱相关同分类。"""
    _, sessions = related_client
    seed(sessions, "t", title="深度学习入门指南", category="科技", created_days_ago=0)
    seed(sessions, "same-cat", title="美食探店笔记", category="科技", created_days_ago=1)
    seed(sessions, "filler", title="深度学习入门指南", category="生活", created_days_ago=9)

    async def run():
        async with sessions() as session:
            return await fetch_related(session, "t")

    rows = asyncio.run(run())
    # same-cat: 2.0 同分类 + 0 标题 + 1.0 摘要 = 3.0;filler: 0 + 3.0 标题全重合 + 1.0 摘要 = 4.0
    assert [row["id"] for row in rows][0] == "filler"
