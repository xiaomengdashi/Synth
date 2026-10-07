"""后台可调参数（SETTING_DEFAULTS 新键）的存取、默认回落与解析边界。"""

import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.services import settings_store
from app.services.fetchers import bilibili_audio, tikhub
from app.services.video_notes import NOTES_PROMPT, build_notes_prompt


def _make_sessions(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 's.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def prepare():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(prepare())
    return engine, sessions


def test_load_settings_fills_tunable_defaults(tmp_path, monkeypatch):
    engine, sessions = _make_sessions(tmp_path)
    monkeypatch.setattr(settings_store, "AsyncSessionLocal", sessions)

    values = asyncio.run(settings_store.load_settings())
    assert values["tikhubApiBase"] == "https://api.tikhub.io"
    assert values["llmMaxTokens"] == "512000"
    assert values["emailFetchDays"] == "7"
    assert values["notesPrompt"] == ""

    # 保存后覆盖默认；清空（存空串）后恢复默认
    asyncio.run(settings_store.save_settings({"llmMaxTokens": "65536"}))
    values = asyncio.run(settings_store.load_settings())
    assert values["llmMaxTokens"] == "65536"
    asyncio.run(settings_store.save_settings({"llmMaxTokens": ""}))
    values = asyncio.run(settings_store.load_settings())
    assert values["llmMaxTokens"] == "512000"

    public = settings_store.public_settings(values)
    assert public["tikhubApiBase"] == "https://api.tikhub.io"
    assert public["bilibiliProxy"] == ""
    asyncio.run(engine.dispose())


def test_numeric_setting_falls_back_and_clamps():
    assert settings_store.numeric_setting({}, "llmTemperature", 0.3) == 0.3
    assert settings_store.numeric_setting({"llmTemperature": "0.7"}, "llmTemperature", 0.3) == 0.7
    assert settings_store.numeric_setting({"llmTemperature": "abc"}, "llmTemperature", 0.3) == 0.3
    assert settings_store.numeric_setting({"llmTemperature": "99"}, "llmTemperature", 0.3, hi=2.0) == 2.0
    assert settings_store.numeric_setting({"summaryLength": "5"}, "summaryLength", 120, lo=20, integer=True) == 20
    assert settings_store.numeric_setting(
        {"llmMaxTokens": "512000.9"}, "llmMaxTokens", 1000, integer=True) == 512000


def test_resolve_tikhub_base_updates_module_endpoint(monkeypatch):
    monkeypatch.setattr(tikhub, "_api_base", tikhub.TIKHUB_API_BASE)
    assert tikhub.resolve_tikhub_base({"tikhubApiBase": "https://mirror.example.com/"}) == "https://mirror.example.com"
    assert tikhub._api_base == "https://mirror.example.com"
    assert tikhub.resolve_tikhub_base({}) == tikhub.TIKHUB_API_BASE
    assert tikhub._api_base == tikhub.TIKHUB_API_BASE


def test_bilibili_proxy_and_minimax_bases(monkeypatch):
    monkeypatch.delenv("BILIBILI_PROXY", raising=False)
    assert bilibili_audio._resolve_bilibili_proxies({}) == [None]
    assert bilibili_audio._resolve_bilibili_proxies({"bilibiliProxy": "http://127.0.0.1:7890"}) == [
        None, "http://127.0.0.1:7890"]
    # 后台配置与环境变量并存时：直连 → 后台代理 → 环境变量
    monkeypatch.setenv("BILIBILI_PROXY", "http://env-proxy:7890")
    assert bilibili_audio._resolve_bilibili_proxies({"bilibiliProxy": "http://cfg-proxy:7890"}) == [
        None, "http://cfg-proxy:7890", "http://env-proxy:7890"]

    assert bilibili_audio._resolve_minimax_bases({}) == bilibili_audio.DEFAULT_MINIMAX_BASES
    assert bilibili_audio._resolve_minimax_bases({"minimaxApiBase": "https://relay.example.com"}) == (
        "https://relay.example.com",)
    # 误填逗号分隔时取第一个；非 URL 值回官方双地址
    assert bilibili_audio._resolve_minimax_bases({"minimaxApiBase": "https://a.cn/, https://b.cn"}) == (
        "https://a.cn",)
    assert bilibili_audio._resolve_minimax_bases({"minimaxApiBase": "not-a-url"}) == (
        bilibili_audio.DEFAULT_MINIMAX_BASES)


def test_notes_prompt_custom_template():
    payload = {
        "title": "网络是什么", "uploader": "UP", "chapter_info": "",
        "description": "", "transcript_text": "全文内容",
    }
    assert "全文内容" in build_notes_prompt(payload, {"notesPrompt": "把 {transcript} 改写成笔记，标题 {title}"})
    assert build_notes_prompt(payload, {}) == NOTES_PROMPT.format(
        title="网络是什么", uploader="UP", chapters="（未提供）", description="（未提供）", transcript="全文内容")
    # 含未知占位符的模板给出可操作的错误信息
    try:
        build_notes_prompt(payload, {"notesPrompt": "{bad_field}"})
    except RuntimeError as exc:
        assert "{transcript}" in str(exc)
    else:
        raise AssertionError("expected RuntimeError for unknown placeholder")
