import pytest
from fastapi.testclient import TestClient

from app.adapters.storage.sqlite_backend import SqliteBackend
from app.api.app import create_app
from app.core.config import Settings
from app.core.domain import (
    Category,
    DigestRun,
    Importance,
    NewsItem,
    RawItem,
    SourceType,
)


@pytest.fixture
def client(tmp_path):
    cfg = tmp_path / "config"
    cfg.mkdir()
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


def _seed(settings):
    st = SqliteBackend(settings.sqlite_path)
    st.init_schema()
    run = DigestRun(run_id="r1")
    st.create_run(run)
    raw = RawItem(source_id="s", source_type=SourceType.RSS, source_name="S",
                  url="https://a/1", title="AI item")
    it = NewsItem.from_raw(raw, run_id="r1")
    it.category = Category.AI_TECH
    it.importance = Importance.HIGH
    it.summary_en = "Summary."
    st.save_items([it])
    return st


def test_dashboard_news_runs(tmp_path):
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "sources.yaml").write_text("sources: []\n", encoding="utf-8")
    (cfg / "watchlist.yaml").write_text("entities: []\nkeywords: []\n", encoding="utf-8")
    settings = Settings(sqlite_path=str(tmp_path / "db.sqlite"),
                        config_dir=str(cfg), output_dir=str(tmp_path / "out"))
    _seed(settings)
    app = create_app(settings, run_digest_fn=lambda **kw: None)
    c = TestClient(app)

    d = c.get("/api/dashboard").json()
    assert d["total_items"] == 1
    assert d["category_counts"]["ai_tech"] == 1
    assert d["latest_run"]["run_id"] == "r1"

    runs = c.get("/api/runs").json()
    assert [r["run_id"] for r in runs] == ["r1"]

    detail = c.get("/api/runs/r1").json()
    assert detail["run"]["run_id"] == "r1"
    assert detail["items"][0]["url"] == "https://a/1"

    assert c.get("/api/runs/missing").status_code == 404

    high = c.get("/api/news", params={"importance": "high"}).json()
    assert len(high) == 1 and high[0]["title"] == "AI item"


def test_sources_and_watchlist_crud(client):
    payload = [{"id": "x", "type": "rss", "name": "X", "url": "https://x/feed",
                "category_hint": "ai_tech", "enabled": True}]
    assert client.put("/api/sources", json=payload).status_code == 200
    got = client.get("/api/sources").json()
    assert got[0]["id"] == "x"

    assert client.put("/api/watchlist", json={"entities": ["OpenAI"], "keywords": []}).status_code == 200
    assert client.get("/api/watchlist").json()["entities"] == ["OpenAI"]


def test_trigger_run_calls_injected_fn(tmp_path):
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "sources.yaml").write_text("sources: []\n", encoding="utf-8")
    (cfg / "watchlist.yaml").write_text("entities: []\nkeywords: []\n", encoding="utf-8")
    settings = Settings(sqlite_path=str(tmp_path / "db.sqlite"),
                        config_dir=str(cfg), output_dir=str(tmp_path / "out"))
    called = {"n": 0}
    app = create_app(settings, run_digest_fn=lambda **kw: called.__setitem__("n", called["n"] + 1))
    c = TestClient(app)
    r = c.post("/api/runs")
    assert r.status_code == 202
    assert called["n"] == 1  # BackgroundTasks runs after response in TestClient


# ---------------------------------------------------------------------------
# /api/sources/resolve tests (fully offline — injected fakes, no network)
# ---------------------------------------------------------------------------

@pytest.fixture
def resolve_client(tmp_path):
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "sources.yaml").write_text("sources: []\n", encoding="utf-8")
    (cfg / "watchlist.yaml").write_text("entities: []\nkeywords: []\n", encoding="utf-8")
    settings = Settings(
        sqlite_path=str(tmp_path / "db.sqlite"),
        config_dir=str(cfg),
        output_dir=str(tmp_path / "out"),
    )
    app = create_app(
        settings,
        run_digest_fn=lambda **kw: None,
        resolve_channel_id_fn=lambda u: "UCxyz",
        discover_feed_fn=lambda u: "https://p.com/feed.xml",
    )
    return TestClient(app)


def test_resolve_youtube_success(resolve_client):
    r = resolve_client.post(
        "/api/sources/resolve",
        json={"type": "youtube", "url": "https://youtube.com/@x"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["channel_id"] == "UCxyz"


def test_resolve_rss_success(resolve_client):
    r = resolve_client.post(
        "/api/sources/resolve",
        json={"type": "rss", "url": "https://some-newspaper.com/"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["url"] == "https://p.com/feed.xml"


def test_resolve_youtube_returns_none_yields_422(tmp_path):
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "sources.yaml").write_text("sources: []\n", encoding="utf-8")
    (cfg / "watchlist.yaml").write_text("entities: []\nkeywords: []\n", encoding="utf-8")
    settings = Settings(
        sqlite_path=str(tmp_path / "db.sqlite"),
        config_dir=str(cfg),
        output_dir=str(tmp_path / "out"),
    )
    app = create_app(
        settings,
        run_digest_fn=lambda **kw: None,
        resolve_channel_id_fn=lambda u: None,
        discover_feed_fn=lambda u: None,
    )
    c = TestClient(app)
    r = c.post("/api/sources/resolve", json={"type": "youtube", "url": "https://youtube.com/@bad"})
    assert r.status_code == 422


def test_resolve_rss_returns_none_yields_422(tmp_path):
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "sources.yaml").write_text("sources: []\n", encoding="utf-8")
    (cfg / "watchlist.yaml").write_text("entities: []\nkeywords: []\n", encoding="utf-8")
    settings = Settings(
        sqlite_path=str(tmp_path / "db.sqlite"),
        config_dir=str(cfg),
        output_dir=str(tmp_path / "out"),
    )
    app = create_app(
        settings,
        run_digest_fn=lambda **kw: None,
        resolve_channel_id_fn=lambda u: None,
        discover_feed_fn=lambda u: None,
    )
    c = TestClient(app)
    r = c.post("/api/sources/resolve", json={"type": "rss", "url": "https://no-feed.com/"})
    assert r.status_code == 422


def test_resolve_unsupported_type_yields_400(resolve_client):
    r = resolve_client.post(
        "/api/sources/resolve",
        json={"type": "scrape", "url": "https://example.com/"},
    )
    assert r.status_code == 400


def test_resolve_exception_mapped_to_422(tmp_path):
    """Exceptions from the resolver function are mapped to 422 (not 500)."""
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "sources.yaml").write_text("sources: []\n", encoding="utf-8")
    (cfg / "watchlist.yaml").write_text("entities: []\nkeywords: []\n", encoding="utf-8")
    settings = Settings(
        sqlite_path=str(tmp_path / "db.sqlite"),
        config_dir=str(cfg),
        output_dir=str(tmp_path / "out"),
    )

    def boom(u):
        raise ValueError("SSRF: private address")

    app = create_app(
        settings,
        run_digest_fn=lambda **kw: None,
        resolve_channel_id_fn=boom,
        discover_feed_fn=boom,
    )
    c = TestClient(app, raise_server_exceptions=False)
    r = c.post("/api/sources/resolve", json={"type": "youtube", "url": "http://192.168.1.1/"})
    assert r.status_code == 422
    assert "SSRF" in r.json()["detail"]

    r2 = c.post("/api/sources/resolve", json={"type": "rss", "url": "http://192.168.1.1/"})
    assert r2.status_code == 422
    assert "SSRF" in r2.json()["detail"]
