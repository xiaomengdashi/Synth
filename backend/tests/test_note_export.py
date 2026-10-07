import asyncio
import datetime
import json
from urllib.parse import quote

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.models import Article
from app.routers import articles
from app.services import runtime_store, settings_store
from app.services.note_export import (
    build_note_markdown,
    safe_filename,
    yaml_safe,
)


@pytest.fixture
def export_client(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'export.db'}")
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
    # require_admin 链路读 settings 表:get_admin_token_hash/verify_admin_token 函数体
    # 内部引用 settings_store 全局,patch AsyncSessionLocal 即可整体指向测试库
    monkeypatch.setattr(settings_store, "AsyncSessionLocal", sessions)
    app = FastAPI()
    app.include_router(articles.router, prefix="/api/v1/articles")
    app.dependency_overrides[get_db] = database
    with TestClient(app) as client:
        yield client, sessions
    asyncio.run(engine.dispose())


def seed(sessions, article_id, title="文章标题", content_md="正文", summary="摘要",
         source_type="other", category=None, publish_time="", account_name="",
         created_days_ago=0):
    values = {
        "id": article_id,
        "title": title,
        "summary": summary,
        "content_md": content_md,
        "original_url": f"https://example.com/{article_id}",
        "source_type": source_type,
        "category": category,
        "account_name": account_name,
        "publish_time": publish_time,
    }

    async def save():
        async with sessions() as session:
            session.add(Article(
                **values,
                created_at=datetime.datetime(2026, 10, 1) - datetime.timedelta(days=created_days_ago),
            ))
            await session.commit()

    asyncio.run(save())


# ---------- build_note_markdown 纯函数 ----------

def test_frontmatter_fields_order_yaml_escaping_and_date_precedence():
    article = {
        "title": "深度学习: 从入门到放弃",
        "summary": "一句摘要",
        "content_md": "## 内容摘要\n\n一句摘要\n\n---\n\n## 正文\n\n正文内容",
        "original_url": "https://example.com/a",
        "source_type": "bilibili",
        "category": "科技",
        "account_name": "UP主",
        "publish_time": "2026-09-28 10:00",
        "created_at": "2026-10-01T00:00:00",
    }
    markdown = build_note_markdown(article)
    frontmatter = markdown.split("\n---\n", 1)[0].removeprefix("---\n")
    keys = [line.split(":", 1)[0] for line in frontmatter.splitlines()]
    # 字段与顺序:title/source_url/source/category/account_name(有则)/date
    assert keys == ["title", "source_url", "source", "category", "account_name", "date"]
    # 含冒号的 title 整体加双引号转义(Obsidian 兼容)
    assert 'title: "深度学习: 从入门到放弃"' in frontmatter
    assert "source: Bilibili" in frontmatter
    # date 取 publish_time(前 10 位)而非 created_at
    assert "date: 2026-09-28" in frontmatter


def test_frontmatter_omits_account_name_when_blank_and_defaults_category():
    article = {
        "title": "无作者", "summary": "", "content_md": "正文",
        "original_url": "https://example.com/b", "source_type": "other",
        "category": "", "account_name": "", "created_at": "2026-10-01T00:00:00",
    }
    frontmatter = build_note_markdown(article).split("\n---\n", 1)[0]
    assert "account_name" not in frontmatter
    # 分类缺省「未分类」
    assert "category: 未分类" in frontmatter
    # created_at 兜底日期(publish_time 缺省)
    assert "date: 2026-10-01" in frontmatter


def test_plain_article_export_keeps_summary_and_markdown_body():
    article = {
        "title": "普通文章", "summary": "一句摘要",
        "content_md": "## 内容摘要\n\n一句摘要\n\n---\n\n## 正文标题\n\n正文段落。",
        "original_url": "https://example.com/plain", "source_type": "other",
        "created_at": "2026-10-01T00:00:00",
    }
    markdown = build_note_markdown(article)
    assert "## 内容摘要" in markdown
    assert "一句摘要" in markdown
    assert "## 正文标题" in markdown
    assert "正文段落。" in markdown
    assert "> 原文：https://example.com/plain" in markdown


def test_wechat_replica_export_extracts_html_text_and_keeps_source_link():
    """微信复刻(HTML_CONTENT_START)不做 HTML→md,但提纯 HTML 文字作正文(与 X 长文 body_html 同先例);
    产物不含 marker 与 HTML 标签,尾部保留原文链接行。"""
    article = {
        "title": "微信复刻文章", "summary": "微信摘要",
        "content_md": (
            "## 内容摘要\n\n微信摘要\n\n---\n\n"
            "<!-- HTML_CONTENT_START -->\n<p style=\"color:red\">复刻正文</p>\n<!-- HTML_CONTENT_END -->"
        ),
        "original_url": "https://mp.weixin.qq.com/s/abc", "source_type": "wechat",
        "created_at": "2026-10-01T00:00:00",
    }
    markdown = build_note_markdown(article)
    assert "HTML_CONTENT_START" not in markdown
    assert "<p" not in markdown
    assert "复刻正文" in markdown
    assert "微信摘要" in markdown
    assert "> 原文：https://mp.weixin.qq.com/s/abc" in markdown


# ---------- X 回归:marker 块 JSON 承载正文 ----------

def test_x_tweet_export_contains_tweet_text_not_summary_only():
    payload = {"tweet_text": "这是推文正文", "article_preview": {"preview_text": "预览文本"}}
    article = {
        "title": "推文", "summary": "推文摘要",
        "content_md": (
            "## 内容摘要\n\n推文摘要\n\n---\n\n"
            f"<!-- X_CONTENT_START -->\n{json.dumps(payload, ensure_ascii=False)}\n<!-- X_CONTENT_END -->"
        ),
        "original_url": "https://x.com/a/status/1", "source_type": "x",
        "created_at": "2026-10-01T00:00:00",
    }
    markdown = build_note_markdown(article)
    assert "这是推文正文" in markdown


def test_x_tweet_export_falls_back_to_article_preview_text():
    """tweet_text 为空时取 article_preview.preview_text,循 task_service 入库口径。"""
    payload = {"tweet_text": "", "article_preview": {"preview_text": "长文预览文本"}}
    article = {
        "title": "长文推文", "summary": "摘要",
        "content_md": (
            "## 内容摘要\n\n摘要\n\n---\n\n"
            f"<!-- X_CONTENT_START -->\n{json.dumps(payload, ensure_ascii=False)}\n<!-- X_CONTENT_END -->"
        ),
        "original_url": "https://x.com/a/status/2", "source_type": "x",
        "created_at": "2026-10-01T00:00:00",
    }
    assert "长文预览文本" in build_note_markdown(article)


def test_x_article_export_prefers_replica_text():
    replica = {"title": "X 长文", "text": "长文 markdown 正文", "body_html": "<p>html 正文</p>"}
    article = {
        "title": "X 长文", "summary": "长文摘要",
        "content_md": (
            "## 内容摘要\n\n长文摘要\n\n---\n\n"
            f"<!-- X_ARTICLE_START -->\n{json.dumps(replica, ensure_ascii=False)}\n<!-- X_ARTICLE_END -->"
        ),
        "original_url": "https://x.com/a/status/3", "source_type": "x",
        "created_at": "2026-10-01T00:00:00",
    }
    markdown = build_note_markdown(article)
    assert "长文 markdown 正文" in markdown


def test_x_article_export_extracts_text_from_body_html_when_text_blank():
    replica = {"title": "X 长文", "text": "", "body_html": "<p>只有 <strong>HTML</strong> 的正文</p>"}
    article = {
        "title": "X 长文", "summary": "摘要",
        "content_md": (
            "## 内容摘要\n\n摘要\n\n---\n\n"
            f"<!-- X_ARTICLE_START -->\n{json.dumps(replica, ensure_ascii=False)}\n<!-- X_ARTICLE_END -->"
        ),
        "original_url": "https://x.com/a/status/4", "source_type": "x",
        "created_at": "2026-10-01T00:00:00",
    }
    assert "只有 HTML 的正文" in build_note_markdown(article).replace("\n", " ")


def test_x_article_export_tolerates_broken_replica_json():
    """replica json 损坏(截断/非 JSON)时回退仅摘要+原文链接,导出不报错。"""
    article = {
        "title": "损坏长文", "summary": "摘要文本",
        "content_md": (
            "## 内容摘要\n\n摘要文本\n\n---\n\n"
            "<!-- X_ARTICLE_START -->\n{\"title\": \"截断\n<!-- X_ARTICLE_END -->"
        ),
        "original_url": "https://x.com/a/status/5", "source_type": "x",
        "created_at": "2026-10-01T00:00:00",
    }
    markdown = build_note_markdown(article)
    assert "摘要文本" in markdown
    assert "> 原文：https://x.com/a/status/5" in markdown


# ---------- 视频笔记:无摘要段头 ----------

def test_video_notes_without_summary_section_export_full_notes_as_body():
    """视频笔记型 content_md 无摘要段头(笔记即成品直接入库):整篇作正文。"""
    article = {
        "title": "视频学习笔记", "summary": "笔记摘要",
        "content_md": "# 视频学习笔记\n\n## 要点\n\n- 要点一\n- 要点二",
        "original_url": "https://bilibili.com/video/BV1", "source_type": "bilibili",
        "created_at": "2026-10-01T00:00:00",
    }
    markdown = build_note_markdown(article)
    assert "# 视频学习笔记" in markdown
    assert "要点一" in markdown


# ---------- safe_filename ----------

def test_yaml_safe_quotes_yaml_bare_scalars():
    """YAML 1.1 裸词(纯数字/布尔/null 变体)不加引号会被 Obsidian 解析为 number/bool/null。"""
    assert yaml_safe("123") == '"123"'
    assert yaml_safe("4.5") == '"4.5"'
    assert yaml_safe("true") == '"true"'
    assert yaml_safe("False") == '"False"'
    assert yaml_safe("null") == '"null"'
    assert yaml_safe("ON") == '"ON"'
    assert yaml_safe("~") == '"~"'
    # 普通文本不受影响
    assert yaml_safe("科技") == "科技"
    assert yaml_safe("X / Twitter") == "X / Twitter"


def test_safe_filename_strips_illegal_chars_collapses_whitespace_and_truncates():
    assert safe_filename('a/b\\c:d*e?f"g<h>i|j') == "abcdefghij"
    # 控制符(含 \t\n)直接剔除,其余连续空白折叠为单个空格
    assert safe_filename("  多\t空\n白  标题 ") == "多空白 标题"
    # 截 80 字符
    assert len(safe_filename("长" * 200)) == 80
    # 清空后兜底
    assert safe_filename("///") == "笔记"


# ---------- 单篇端点 ----------

def test_export_endpoint_returns_markdown_attachment(export_client):
    client, sessions = export_client
    seed(sessions, "plain", title="普通文章",
         content_md="## 内容摘要\n\n一句摘要\n\n---\n\n## 正文\n\n正文内容", summary="一句摘要")
    response = client.get("/api/v1/articles/plain/export")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    disposition = response.headers["content-disposition"]
    assert disposition.startswith("attachment;")
    # ascii 兜底名 + RFC 5987 UTF-8 文件名双段
    assert 'filename="plain.md"' in disposition
    assert f"filename*=UTF-8''{quote('普通文章.md')}" in disposition
    assert response.text.startswith("---")
    assert "## 正文" in response.text


def test_export_endpoint_404_for_unknown_id(export_client):
    client, _ = export_client
    assert client.get("/api/v1/articles/nope/export").status_code == 404
