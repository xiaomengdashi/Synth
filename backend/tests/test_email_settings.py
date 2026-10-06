import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.services import settings_store


def _make_sessions(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 's.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def prepare():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(prepare())
    return engine, sessions


def test_public_settings_masks_imap_password(tmp_path, monkeypatch):
    engine, sessions = _make_sessions(tmp_path)
    monkeypatch.setattr(settings_store, "AsyncSessionLocal", sessions)
    asyncio.run(settings_store.save_settings({
        "imapUser": "kolane@163.com",
        "imapPassword": "authcode-12345",
        "imapSenderWhitelist": "friend@qq.com",
    }))

    public = settings_store.public_settings(asyncio.run(settings_store.load_settings()))
    assert "authcode-12345" not in str(public)
    assert public["imapPassword"] == "••••2345"
    assert public["imapUser"] == "kolane@163.com"
    assert public["imapHost"] == ""
    assert public["imapSenderWhitelist"] == "friend@qq.com"
    assert public["imapConfigured"] is True
    asyncio.run(engine.dispose())


def test_imap_password_not_configured_when_user_missing(tmp_path, monkeypatch):
    engine, sessions = _make_sessions(tmp_path)
    monkeypatch.setattr(settings_store, "AsyncSessionLocal", sessions)
    asyncio.run(settings_store.save_settings({"imapPassword": "authcode-12345"}))
    public = settings_store.public_settings(asyncio.run(settings_store.load_settings()))
    assert public["imapConfigured"] is False
    asyncio.run(engine.dispose())


def test_processed_message_ids_roundtrip_and_cap(tmp_path, monkeypatch):
    engine, sessions = _make_sessions(tmp_path)
    monkeypatch.setattr(settings_store, "AsyncSessionLocal", sessions)

    asyncio.run(settings_store.record_processed_message_ids(["a@1", "b@2"]))
    asyncio.run(settings_store.record_processed_message_ids(["b@2", "c@3"]))
    assert asyncio.run(settings_store.load_processed_message_ids()) == ["a@1", "b@2", "c@3"]

    batch = [f"id-{n}" for n in range(600)]
    kept = asyncio.run(settings_store.record_processed_message_ids(batch))
    assert len(kept) == 500
    assert kept[0] == "id-100"
    assert kept[-1] == "id-599"
    asyncio.run(engine.dispose())
