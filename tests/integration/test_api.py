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


def test_api_omits_flagged_items(tmp_path):
    """GET /api/runs/{id} and GET /api/news must not serve flagged items."""
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "sources.yaml").write_text("sources: []\n", encoding="utf-8")
    (cfg / "watchlist.yaml").write_text("entities: []\nkeywords: []\n", encoding="utf-8")
    settings = Settings(sqlite_path=str(tmp_path / "db.sqlite"),
                        config_dir=str(cfg), output_dir=str(tmp_path / "out"))

    st = SqliteBackend(settings.sqlite_path)
    st.init_schema()
    run = DigestRun(run_id="r1")
    st.create_run(run)

    def mk(url, status):
        raw = RawItem(source_id="s", source_type=SourceType.RSS, source_name="S",
                      url=url, title="t")
        it = NewsItem.from_raw(raw, run_id="r1")
        it.category = Category.AI_TECH
        it.importance = Importance.HIGH
        it.status = status
        return it

    st.save_items([mk("https://a/ok", "processed"), mk("https://a/bad", "flagged")])

    app = create_app(settings, run_digest_fn=lambda **kw: None)
    c = TestClient(app)

    detail = c.get("/api/runs/r1").json()
    assert [i["url"] for i in detail["items"]] == ["https://a/ok"]

    news = c.get("/api/news").json()
    assert [i["url"] for i in news] == ["https://a/ok"]

    # Dashboard category counts must also exclude the flagged item.
    d = c.get("/api/dashboard").json()
    assert d["total_items"] == 1
    assert d["category_counts"]["ai_tech"] == 1


def test_news_runs_limit_over_cap_returns_422(client):
    # limit above the 200 cap is rejected by FastAPI Query validation.
    assert client.get("/api/news", params={"limit": 9999}).status_code == 422
    assert client.get("/api/runs", params={"limit": 9999}).status_code == 422
    # limit below 1 and negative offset are also rejected.
    assert client.get("/api/news", params={"limit": 0}).status_code == 422
    assert client.get("/api/news", params={"offset": -1}).status_code == 422


def test_news_valid_limit_and_offset(tmp_path):
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "sources.yaml").write_text("sources: []\n", encoding="utf-8")
    (cfg / "watchlist.yaml").write_text("entities: []\nkeywords: []\n", encoding="utf-8")
    settings = Settings(sqlite_path=str(tmp_path / "db.sqlite"),
                        config_dir=str(cfg), output_dir=str(tmp_path / "out"))

    from datetime import UTC, datetime
    st = SqliteBackend(settings.sqlite_path)
    st.init_schema()
    items = []
    for i in range(3):
        raw = RawItem(source_id="s", source_type=SourceType.RSS, source_name="S",
                      url=f"https://a/{i}", title=f"item {i}")
        it = NewsItem.from_raw(raw, run_id="r1")
        it.category = Category.AI_TECH
        it.collected_at = datetime(2026, 5, 21 + i, tzinfo=UTC)
        items.append(it)
    st.save_items(items)

    app = create_app(settings, run_digest_fn=lambda **kw: None)
    c = TestClient(app)

    # limit caps the page size; newest collected_at first.
    page = c.get("/api/news", params={"limit": 2}).json()
    assert [i["url"] for i in page] == ["https://a/2", "https://a/1"]
    # offset skips the first result.
    page2 = c.get("/api/news", params={"limit": 2, "offset": 1}).json()
    assert [i["url"] for i in page2] == ["https://a/1", "https://a/0"]


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
    done = __import__("threading").Event()

    def _run(**kw):
        called["n"] += 1
        done.set()

    app = create_app(settings, run_digest_fn=_run)
    c = TestClient(app)
    r = c.post("/api/runs")
    assert r.status_code == 202
    assert done.wait(timeout=5)  # run executes on a detached worker thread
    assert called["n"] == 1


def _runs_settings(tmp_path):
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "sources.yaml").write_text("sources: []\n", encoding="utf-8")
    (cfg / "watchlist.yaml").write_text("entities: []\nkeywords: []\n", encoding="utf-8")
    return Settings(sqlite_path=str(tmp_path / "db.sqlite"),
                    config_dir=str(cfg), output_dir=str(tmp_path / "out"))


def test_trigger_run_returns_run_id(tmp_path):
    import threading

    captured: dict = {}
    done = threading.Event()

    def _run(**kw):
        captured.update(kw)
        done.set()

    app = create_app(_runs_settings(tmp_path), run_digest_fn=_run)
    c = TestClient(app)
    r = c.post("/api/runs")
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "started"
    assert isinstance(body["run_id"], str) and len(body["run_id"]) == 12
    assert done.wait(timeout=5)
    # The id returned to the client is the SAME one handed to run_digest.
    assert captured["run_id"] == body["run_id"]


def test_trigger_run_is_single_flight(tmp_path):
    """A second trigger while one run is in flight gets 409, not a 2nd pipeline."""
    import threading

    started = threading.Event()
    release = threading.Event()

    def blocking_run(**kw):
        started.set()
        release.wait(timeout=5)

    app = create_app(_runs_settings(tmp_path), run_digest_fn=blocking_run)
    client = TestClient(app)
    # The run executes on a detached thread, so this returns 202 immediately
    # while the run holds the single-flight lock.
    first = client.post("/api/runs")
    assert first.status_code == 202
    assert started.wait(timeout=5), "first run never started"
    # Second request arrives while the first still holds the lock.
    assert client.post("/api/runs").status_code == 409
    release.set()


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


def test_resolve_rejects_non_http_scheme(resolve_client):
    for bad in ("file:///etc/passwd", "javascript:alert(1)"):
        r = resolve_client.post(
            "/api/sources/resolve",
            json={"type": "rss", "url": bad},
        )
        assert r.status_code == 422, bad


def test_put_sources_rejects_non_http_url(client):
    payload = [{"id": "x", "type": "rss", "name": "X", "url": "file:///etc/passwd",
                "category_hint": "ai_tech", "enabled": True}]
    assert client.put("/api/sources", json=payload).status_code == 422
    payload2 = [{"id": "y", "type": "rss", "name": "Y", "url": "javascript:alert(1)",
                 "category_hint": "ai_tech", "enabled": True}]
    assert client.put("/api/sources", json=payload2).status_code == 422


def test_put_sources_allows_none_url(client):
    # Sources without a url (e.g. api/query sources) must still be accepted.
    payload = [{"id": "q", "type": "api", "name": "Q", "query": "ai", "enabled": True}]
    assert client.put("/api/sources", json=payload).status_code == 200


def test_resolve_unsupported_type_yields_400(resolve_client):
    r = resolve_client.post(
        "/api/sources/resolve",
        json={"type": "scrape", "url": "https://example.com/"},
    )
    assert r.status_code == 400


def test_resolve_exception_returns_generic_message(tmp_path):
    """Resolver exceptions map to a 4xx with a GENERIC message (no internals leaked)."""
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
        raise ValueError("SSRF: private address 192.168.1.1")

    app = create_app(
        settings,
        run_digest_fn=lambda **kw: None,
        resolve_channel_id_fn=boom,
        discover_feed_fn=boom,
    )
    c = TestClient(app, raise_server_exceptions=False)
    r = c.post("/api/sources/resolve", json={"type": "youtube", "url": "http://example.com/"})
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert "SSRF" not in detail  # internal exception text must NOT leak
    assert "192.168" not in detail
    assert detail == "could not resolve source"

    r2 = c.post("/api/sources/resolve", json={"type": "rss", "url": "http://example.com/"})
    assert r2.status_code == 400
    detail2 = r2.json()["detail"]
    assert "SSRF" not in detail2
    assert detail2 == "could not resolve source"


# ---------------------------------------------------------------------------
# API-key auth (optional; open when settings.api_key is unset)
# ---------------------------------------------------------------------------


def _auth_client(tmp_path, api_key):
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "sources.yaml").write_text("sources: []\n", encoding="utf-8")
    (cfg / "watchlist.yaml").write_text("entities: []\nkeywords: []\n", encoding="utf-8")
    settings = Settings(
        sqlite_path=str(tmp_path / "db.sqlite"),
        config_dir=str(cfg),
        output_dir=str(tmp_path / "out"),
        api_key=api_key,
    )
    app = create_app(
        settings,
        run_digest_fn=lambda **kw: None,
        resolve_channel_id_fn=lambda u: "UCxyz",
        discover_feed_fn=lambda u: "https://p.com/feed.xml",
    )
    return TestClient(app)


def test_mutating_routes_require_api_key_when_set(tmp_path):
    c = _auth_client(tmp_path, api_key="secret")
    src = [{"id": "x", "type": "rss", "name": "X", "url": "https://x/feed", "enabled": True}]

    # No header -> 401
    assert c.put("/api/sources", json=src).status_code == 401
    assert c.put("/api/watchlist", json={"entities": [], "keywords": []}).status_code == 401
    assert c.post("/api/runs").status_code == 401
    assert c.post("/api/sources/resolve",
                  json={"type": "youtube", "url": "https://youtube.com/@x"}).status_code == 401

    # X-API-Key header -> allowed
    h = {"X-API-Key": "secret"}
    assert c.put("/api/sources", json=src, headers=h).status_code == 200
    assert c.put("/api/watchlist", json={"entities": [], "keywords": []}, headers=h).status_code == 200
    assert c.post("/api/runs", headers=h).status_code == 202
    assert c.post("/api/sources/resolve",
                  json={"type": "youtube", "url": "https://youtube.com/@x"},
                  headers=h).status_code == 200

    # Authorization: Bearer header -> allowed
    hb = {"Authorization": "Bearer secret"}
    assert c.post("/api/runs", headers=hb).status_code == 202

    # Wrong key -> 401
    assert c.post("/api/runs", headers={"X-API-Key": "nope"}).status_code == 401


def test_read_routes_require_api_key_when_set(tmp_path):
    """When api_key is configured, EVERY route except /health requires it."""
    c = _auth_client(tmp_path, api_key="secret")
    # /health stays public (liveness probe).
    assert c.get("/api/health").status_code == 200
    # Reads now 401 without the key...
    for path in ("/api/dashboard", "/api/runs", "/api/runs/r1", "/api/news",
                 "/api/sources", "/api/watchlist"):
        assert c.get(path).status_code == 401, path
    # ...and succeed with it (404 for the missing run is still "authorized").
    h = {"X-API-Key": "secret"}
    assert c.get("/api/dashboard", headers=h).status_code == 200
    assert c.get("/api/runs", headers=h).status_code == 200
    assert c.get("/api/news", headers=h).status_code == 200
    assert c.get("/api/sources", headers=h).status_code == 200
    assert c.get("/api/watchlist", headers=h).status_code == 200
    assert c.get("/api/runs/r1", headers=h).status_code == 404


def test_auth_default_open_when_unset(tmp_path):
    c = _auth_client(tmp_path, api_key=None)
    src = [{"id": "x", "type": "rss", "name": "X", "url": "https://x/feed", "enabled": True}]
    assert c.put("/api/sources", json=src).status_code == 200
    assert c.post("/api/runs").status_code == 202


# ---------------------------------------------------------------------------
# Rate limiting on /runs and /resolve
# ---------------------------------------------------------------------------


def test_runs_rate_limited(tmp_path):
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "sources.yaml").write_text("sources: []\n", encoding="utf-8")
    (cfg / "watchlist.yaml").write_text("entities: []\nkeywords: []\n", encoding="utf-8")
    settings = Settings(
        sqlite_path=str(tmp_path / "db.sqlite"),
        config_dir=str(cfg),
        output_dir=str(tmp_path / "out"),
        rate_limit_burst=1,
        rate_limit_refill_per_sec=0.0,
    )
    app = create_app(settings, run_digest_fn=lambda **kw: None)
    c = TestClient(app)
    assert c.post("/api/runs").status_code == 202
    r = c.post("/api/runs")
    assert r.status_code == 429
    assert r.json()["detail"] == "rate limit exceeded"


def test_resolve_rate_limited(tmp_path):
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "sources.yaml").write_text("sources: []\n", encoding="utf-8")
    (cfg / "watchlist.yaml").write_text("entities: []\nkeywords: []\n", encoding="utf-8")
    settings = Settings(
        sqlite_path=str(tmp_path / "db.sqlite"),
        config_dir=str(cfg),
        output_dir=str(tmp_path / "out"),
        rate_limit_burst=1,
        rate_limit_refill_per_sec=0.0,
    )
    app = create_app(
        settings,
        run_digest_fn=lambda **kw: None,
        resolve_channel_id_fn=lambda u: "UCxyz",
        discover_feed_fn=lambda u: "https://p.com/feed.xml",
    )
    c = TestClient(app)
    body = {"type": "youtube", "url": "https://youtube.com/@x"}
    assert c.post("/api/sources/resolve", json=body).status_code == 200
    r = c.post("/api/sources/resolve", json=body)
    assert r.status_code == 429
    assert r.json()["detail"] == "rate limit exceeded"


def test_scheduler_starts_when_enabled(tmp_path):
    cfg = _runs_settings(tmp_path)
    settings = Settings(
        _env_file=None, schedule_enabled=True, schedule_cron="0 7 * * *",
        sqlite_path=cfg.sqlite_path, config_dir=cfg.config_dir, output_dir=cfg.output_dir,
    )
    app = create_app(settings, run_digest_fn=lambda **kw: None)
    with TestClient(app):
        assert app.state.scheduler is not None
        assert app.state.scheduler.running
    # lifespan shutdown stopped it
    assert not app.state.scheduler.running


def test_scheduler_absent_by_default(tmp_path):
    app = create_app(_runs_settings(tmp_path), run_digest_fn=lambda **kw: None)
    with TestClient(app):
        assert app.state.scheduler is None


# ---------------------------------------------------------------------------
# Fail-closed: a non-loopback bind without API_KEY must refuse to start
# ---------------------------------------------------------------------------


def test_require_api_key_for_nonlocal_raises_without_key():
    from app.api.app import require_api_key_for_nonlocal

    s = Settings(_env_file=None, api_key=None, app_host="0.0.0.0")
    with pytest.raises(RuntimeError, match="API_KEY"):
        require_api_key_for_nonlocal(s, s.app_host)
    # An explicit LAN address is also non-loopback.
    with pytest.raises(RuntimeError, match="API_KEY"):
        require_api_key_for_nonlocal(s, "192.168.1.10")


def test_require_api_key_for_nonlocal_allows_loopback():
    from app.api.app import require_api_key_for_nonlocal

    s = Settings(_env_file=None, api_key=None, app_host="127.0.0.1")
    # None of these raise (loopback identities stay open for local/dev).
    require_api_key_for_nonlocal(s, "127.0.0.1")
    require_api_key_for_nonlocal(s, "localhost")
    require_api_key_for_nonlocal(s, "::1")


def test_require_api_key_for_nonlocal_allows_nonlocal_with_key():
    from app.api.app import require_api_key_for_nonlocal

    s = Settings(_env_file=None, api_key="secret", app_host="0.0.0.0")
    require_api_key_for_nonlocal(s, s.app_host)  # no raise — key is set


def test_create_app_refuses_nonlocal_bind_without_key(tmp_path):
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "sources.yaml").write_text("sources: []\n", encoding="utf-8")
    (cfg / "watchlist.yaml").write_text("entities: []\nkeywords: []\n", encoding="utf-8")
    settings = Settings(
        _env_file=None,
        sqlite_path=str(tmp_path / "db.sqlite"),
        config_dir=str(cfg),
        output_dir=str(tmp_path / "out"),
        app_host="0.0.0.0",
        api_key=None,
    )
    with pytest.raises(RuntimeError, match="API_KEY"):
        create_app(settings, run_digest_fn=lambda **kw: None)


# ---------------------------------------------------------------------------
# CSRF: when the API is OPEN (no api_key), block cross-origin mutations
# ---------------------------------------------------------------------------


def test_open_api_blocks_cross_origin_mutation(tmp_path):
    c = _auth_client(tmp_path, api_key=None)  # open mode
    src = [{"id": "x", "type": "rss", "name": "X", "url": "https://x/feed", "enabled": True}]
    evil = {"Origin": "https://evil.example"}
    assert c.put("/api/sources", json=src, headers=evil).status_code == 403
    assert c.put("/api/watchlist", json={"entities": [], "keywords": []},
                 headers=evil).status_code == 403
    assert c.post("/api/runs", headers=evil).status_code == 403
    assert c.post("/api/sources/resolve",
                  json={"type": "youtube", "url": "https://youtube.com/@x"},
                  headers=evil).status_code == 403
    # Referer is honored too (some browsers omit Origin on some requests).
    assert c.post("/api/runs", headers={"Referer": "https://evil.example/page"}).status_code == 403


def test_open_api_allows_same_origin_and_no_origin(tmp_path):
    c = _auth_client(tmp_path, api_key=None)  # open; default allow_origins = localhost:3000
    src = [{"id": "x", "type": "rss", "name": "X", "url": "https://x/feed", "enabled": True}]
    # Allow-listed console origin passes.
    assert c.put("/api/sources", json=src,
                 headers={"Origin": "http://localhost:3000"}).status_code == 200
    # No Origin/Referer (CLI, curl, tests) passes — CSRF is browser-only.
    assert c.post("/api/runs").status_code == 202


def test_keyed_api_ignores_origin(tmp_path):
    # When api_key is set, the key is the control; cross-origin with a valid key is fine.
    c = _auth_client(tmp_path, api_key="secret")
    h = {"X-API-Key": "secret", "Origin": "https://evil.example"}
    assert c.post("/api/runs", headers=h).status_code == 202
