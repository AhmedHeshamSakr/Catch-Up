import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.core.config import Settings


@pytest.fixture
def client(tmp_path):
    cfg = tmp_path / "config"; cfg.mkdir()
    (cfg / "sources.yaml").write_text("sources: []\n", encoding="utf-8")
    (cfg / "watchlist.yaml").write_text("entities: []\nkeywords: []\n", encoding="utf-8")
    settings = Settings(sqlite_path=str(tmp_path / "db.sqlite"),
                        config_dir=str(cfg), output_dir=str(tmp_path / "out"))
    app = create_app(settings, run_digest_fn=lambda **kw: None)
    return TestClient(app)


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
