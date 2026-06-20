"""Deploy-surface tests: the product /api/* routes must be mountable onto ANY
FastAPI app (this is how app/fast_api_app.py serves them in the deployed
container), and create_app's CORS must honor Settings.allow_origins.

Note: app/fast_api_app.py itself isn't imported here — it calls
google.auth.default() and creates a Cloud Logging client at import time, which
needs GCP creds. We test register_product_routes (the exact function it uses)
and create_app instead.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.app import create_app, register_product_routes
from app.core.config import Settings


def _settings(tmp_path) -> Settings:
    return Settings(
        _env_file=None,
        config_dir=str(tmp_path),
        sqlite_path=str(tmp_path / "t.db"),
        allow_origins=["https://console.example"],
    )


def test_register_product_routes_mounts_api_on_any_app(tmp_path):
    app = FastAPI()  # a bare app, standing in for the ADK deploy app
    register_product_routes(app, _settings(tmp_path))
    client = TestClient(app)
    health = client.get("/api/health").json()
    assert health["status"] == "ok"
    assert health["app"] == "catch-up"  # marker for the launcher's reuse-detection
    # A real product route is live (not just health) — proves the frontend's
    # /api/* calls would reach a backend in the deployed container.
    r = client.get("/api/dashboard")
    assert r.status_code == 200
    assert r.json()["total_items"] == 0


def test_create_app_cors_uses_settings_allow_origins(tmp_path):
    client = TestClient(create_app(_settings(tmp_path)))
    allowed = client.get("/api/health", headers={"Origin": "https://console.example"})
    assert allowed.headers.get("access-control-allow-origin") == "https://console.example"
    denied = client.get("/api/health", headers={"Origin": "https://evil.example"})
    assert denied.headers.get("access-control-allow-origin") is None
