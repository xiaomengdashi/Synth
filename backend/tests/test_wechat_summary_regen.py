"""存量微信摘要批量重生成：正文还原、摘要段替换与跑批统计（LLM 打桩）。"""

import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.models import Article
from app.services import wechat_summary_regen


def _make_sessions(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 's.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def prepare():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(prepare())
    return engine, sessions


def test_extract_body_text_prefers_html_block():
    content = (
        "## 内容摘要\n\n旧摘要文本\n\n---\n\n"
        "<!-- HTML_CONTENT_START -->\n<p>HTML 正文第一段。</p><p>第二段。</p>\n<!-- HTML_CONTENT_END -->"
    )
    body = wechat_summary_regen.extract_body_text(content)
    assert "HTML 正文第一段。" in body and "第二段。" in body
    assert "旧摘要" not in body

    md_only = "## 内容摘要\n\n旧摘要\n\n---\n\n这是 markdown 正文，足够长的一段内容。"
    assert wechat_summary_regen.extract_body_text(md_only) == "这是 markdown 正文，足够长的一段内容。"


def test_replace_summary_section_keeps_body_and_fallback():
    content = "## 内容摘要\n\n旧摘要\n\n---\n\n<!-- HTML_CONTENT_START -->\n<p>正文</p>\n<!-- HTML_CONTENT_END -->"
    updated = wechat_summary_regen.replace_summary_section(content, "新模型摘要")
    assert updated.startswith("## 内容摘要\n\n新模型摘要\n\n---")
    assert "<p>正文</p>" in updated
    # 结构不匹配时原样返回
    assert wechat_summary_regen.replace_summary_section("裸正文没有摘要段", "x") == "裸正文没有摘要段"


def test_regenerate_walks_articles_and_updates(tmp_path, monkeypatch):
    engine, sessions = _make_sessions(tmp_path)
    monkeypatch.setattr(wechat_summary_regen, "AsyncSessionLocal", sessions)

    async def fake_summary(title, body, config, *, limit=120):
        if "短文" in title:
            raise wechat_summary_regen.ArticleSummarySkipped("短")
        if "炸机" in title:
            raise RuntimeError("LLM down")
        return f"LLM 摘要:{title}"

    monkeypatch.setattr(wechat_summary_regen, "generate_article_summary", fake_summary)

    async def fake_load():
        return {}

    monkeypatch.setattr(wechat_summary_regen, "load_settings", fake_load)

    long_body = "很长的正文内容。" * 40

    def make(title, source, body_html=True):
        content = (
            f"## 内容摘要\n\n旧摘要{title}\n\n---\n\n"
            + (f"<!-- HTML_CONTENT_START -->\n<p>{long_body}</p>\n<!-- HTML_CONTENT_END -->" if body_html else long_body)
        )
        return Article(id=title, title=title, summary=f"旧摘要{title}", content_md=content,
                       original_url="https://mp.weixin.qq.com/s/x", source_type=source)

    async def seed():
        async with sessions() as session:
            session.add_all([
                make("微信正常", "wechat"),
                make("微信炸机", "wechat"),
                Article(id="微信短文", title="微信短文", summary="旧", content_md="## 内容摘要\n\n旧\n\n---\n\n<p>短</p>",
                       original_url="u", source_type="wechat"),
                make("B站不受影响", "bilibili"),
            ])
            await session.commit()

    asyncio.run(seed())
    result = asyncio.run(wechat_summary_regen.regenerate_wechat_summaries())

    assert result["total"] == 3  # 只统计微信
    assert result["ok"] == 1
    assert result["failed"] == 1
    assert result["skipped"] == 1

    async def check():
        async with sessions() as session:
            normal = await session.get(Article, "微信正常")
            assert normal.summary == "LLM 摘要:微信正常"
            assert normal.content_md.startswith("## 内容摘要\n\nLLM 摘要:微信正常\n\n---")
            assert long_body in normal.content_md  # 正文原样保留
            broken = await session.get(Article, "微信炸机")
            assert broken.summary == "旧摘要微信炸机"  # 失败保留原摘要
            bili = await session.get(Article, "B站不受影响")
            assert bili.summary == "旧摘要B站不受影响"

    asyncio.run(check())
    asyncio.run(engine.dispose())
