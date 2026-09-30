import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.services import settings_store


def test_public_settings_never_expose_tikhub_key(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 's.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def prepare():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(prepare())
    monkeypatch.setattr(settings_store, "AsyncSessionLocal", sessions)
    asyncio.run(settings_store.save_settings({"tikhubApiKey": "real-private-token", "apiKey": "model-private-key"}))

    public = settings_store.public_settings(asyncio.run(settings_store.load_settings()))
    assert "real-private-token" not in str(public)
    assert "model-private-key" not in str(public)
    assert public["tikhubConfigured"] is True
    assert public["apiKey"] == "••••-key"
    assert public["apiKeyConfigured"] is True
    asyncio.run(engine.dispose())
