"""Tests for the local desktop Settings surface: /api/health marker, and the
GET/PUT /api/settings routes with their localhost-only write guard."""

import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.core.config import Settings


def _make(tmp_path, *, google_api_key="", app_port=8000):
    cfg = tmp_path / "config"
    cfg.mkdir(exist_ok=True)
    (cfg / "sources.yaml").write_text("sources: []\n", encoding="utf-8")
    (cfg / "watchlist.yaml").write_text("entities: []\nkeywords: []\n", encoding="utf-8")
    settings = Settings(
        _env_file=None,
        sqlite_path=str(tmp_path / "db.sqlite"),
        config_dir=str(cfg),
        output_dir=str(tmp_path / "out"),
        env_path=str(tmp_path / "app.env"),
        google_api_key=google_api_key,
        app_port=app_port,
    )
    return settings


def _client(settings, *, client=("127.0.0.1", 12345), base_url="http://127.0.0.1:8000"):
    app = create_app(settings, run_digest_fn=lambda **kw: None)
    return TestClient(app, base_url=base_url, client=client)


# --- /api/health marker (Codex #9) -----------------------------------------

def test_health_includes_app_marker(tmp_path):
    c = _client(_make(tmp_path))
    body = c.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["app"] == "catch-up"
    assert "version" in body


# --- GET /api/settings (non-secret) ----------------------------------------

def test_get_settings_returns_nonsecret_state(tmp_path):
    c = _client(_make(tmp_path, google_api_key="secret-key", app_port=8123))
    body = c.get("/api/settings").json()
    assert body["app_port"] == 8123
    assert body["gemini_key_set"] is True
    # the actual key value must never be exposed
    assert "secret-key" not in str(body)
    assert "google_api_key" not in body


def test_get_settings_key_unset(tmp_path):
    c = _client(_make(tmp_path, google_api_key=""))
    assert c.get("/api/settings").json()["gemini_key_set"] is False


# --- PUT /api/settings (apply + persist) -----------------------------------

def test_put_key_applies_live_and_persists(tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "old")  # monkeypatch restores after test
    settings = _make(tmp_path, google_api_key="old")
    c = _client(settings)

    r = c.put("/api/settings", json={"google_api_key": "new-key-123"})
    assert r.status_code == 200
    body = r.json()
    assert body["applied"] == ["google_api_key"]
    assert body["restart_required"] == []

    import os

    assert os.environ["GOOGLE_API_KEY"] == "new-key-123"   # live, overwritten
    assert settings.google_api_key == "new-key-123"         # in-memory updated
    # persisted to the injected env file
    assert "new-key-123" in (tmp_path / "app.env").read_text(encoding="utf-8")
    # GET reflects it
    assert c.get("/api/settings").json()["gemini_key_set"] is True


def test_put_port_is_restart_required(tmp_path):
    settings = _make(tmp_path, app_port=8000)
    c = _client(settings)
    r = c.put("/api/settings", json={"app_port": 9090})
    assert r.status_code == 200
    assert r.json()["restart_required"] == ["app_port"]
    assert r.json()["applied"] == []
    assert settings.app_port == 9090
    assert "APP_PORT=9090" in (tmp_path / "app.env").read_text(encoding="utf-8")


def test_put_invalid_port_rejected(tmp_path):
    c = _client(_make(tmp_path))
    assert c.put("/api/settings", json={"app_port": 80}).status_code == 422
    assert c.put("/api/settings", json={"app_port": 70000}).status_code == 422


# --- localhost write guard (Codex #6) --------------------------------------

def test_put_rejects_remote_client(tmp_path):
    c = _client(_make(tmp_path), client=("203.0.113.9", 5000))
    assert c.put("/api/settings", json={"app_port": 9000}).status_code == 403


def test_put_rejects_non_loopback_host(tmp_path):
    # loopback socket but attacker-controlled Host header (DNS-rebinding)
    c = _client(_make(tmp_path))
    r = c.put("/api/settings", json={"app_port": 9000}, headers={"host": "evil.example"})
    assert r.status_code == 403


def test_put_rejects_cross_origin(tmp_path):
    c = _client(_make(tmp_path))
    r = c.put(
        "/api/settings",
        json={"app_port": 9000},
        headers={"origin": "http://evil.example"},
    )
    assert r.status_code == 403


def test_put_allows_loopback_with_same_origin(tmp_path):
    c = _client(_make(tmp_path))
    r = c.put(
        "/api/settings",
        json={"app_port": 9000},
        headers={"origin": "http://127.0.0.1:8000"},
    )
    assert r.status_code == 200


def test_get_settings_also_local_only(tmp_path):
    c = _client(_make(tmp_path), client=("203.0.113.9", 5000))
    assert c.get("/api/settings").status_code == 403
