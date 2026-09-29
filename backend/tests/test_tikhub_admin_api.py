import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import tikhub as tikhub_router


@pytest.fixture
def client(tmp_path, monkeypatch):
    config_file = tmp_path / "config.json"
    monkeypatch.setattr(tikhub_router, "CONFIG_FILE", str(config_file))
    monkeypatch.delenv("TIKHUB_API_TOKEN", raising=False)
    app = FastAPI()
    app.include_router(tikhub_router.router, prefix="/api/v1/tikhub")
    with TestClient(app) as test_client:
        yield test_client, config_file


def test_account_returns_not_configured_when_no_token(client):
    http, _ = client
    response = http.get("/api/v1/tikhub/account")
    assert response.status_code == 200
    assert response.json() == {"configured": False}


def test_account_returns_summary_when_configured(client, monkeypatch):
    http, config_file = client
    config_file.write_text(json.dumps({"tikhubApiKey": "tok", "apiKey": "llm"}))

    def fake_account(config):
        return {
            "api_key": {"name": "SynthAI", "created_at": None, "expires_at": None, "status": 1, "scopes_count": 70},
            "user": {"email": "a@b.c", "balance": 4.966, "free_credit": 0.0, "is_active": True},
            "daily_usage": {"date": "2026-09-29", "usage": 0.034, "total_request_per_day": 20,
                            "paid_request_per_day": 18, "uri_counts": {"/api/v1/twitter/web/fetch_tweet_detail": 4}},
        }

    monkeypatch.setattr(tikhub_router, "fetch_tikhub_account", fake_account)
    data = http.get("/api/v1/tikhub/account").json()
    assert data["configured"] is True
    assert data["user"]["balance"] == 4.966
    assert data["daily_usage"]["uri_counts"]["/api/v1/twitter/web/fetch_tweet_detail"] == 4


def test_set_key_rejects_invalid_token_without_saving(client, monkeypatch):
    http, config_file = client

    def invalid(token):
        from app.services.fetchers.tikhub import TikHubError
        raise TikHubError("TikHub Token 无效、缺失或未激活 (401)。")

    monkeypatch.setattr(tikhub_router, "verify_tikhub_token", invalid)
    response = http.post("/api/v1/tikhub/key", json={"apiKey": "bad"})
    assert response.status_code == 400
    assert "Token 验证失败" in response.json()["detail"]
    assert not config_file.exists()


def test_set_key_verifies_then_persists(client, monkeypatch):
    http, config_file = client
    config_file.write_text(json.dumps({"apiKey": "llm", "tikhubApiKey": "old"}))

    def valid(token):
        return {
            "api_key": {"name": "SynthAI", "created_at": None, "expires_at": None, "status": 1, "scopes_count": 70},
            "user": {"balance": 5.0, "free_credit": 0.0, "is_active": True},
        }

    monkeypatch.setattr(tikhub_router, "verify_tikhub_token", valid)
    response = http.post("/api/v1/tikhub/key", json={"apiKey": "new-token"})
    assert response.status_code == 200
    assert response.json()["status"] == "success"

    stored = json.loads(config_file.read_text())
    assert stored["tikhubApiKey"] == "new-token"
    assert stored["apiKey"] == "llm"  # 其他配置字段保持不变


def test_set_key_rejects_empty(client):
    http, _ = client
    assert http.post("/api/v1/tikhub/key", json={"apiKey": "  "}).status_code == 400
