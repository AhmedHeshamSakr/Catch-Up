"""Single-port static serving: FastAPI serves the Next.js export (frontend/out)
with a Next-aware resolver + SPA fallback, without shadowing /api/*."""

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.static import resolve_static_file
from app.core.config import Settings


def _console(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "index.html").write_text("<html>HOME</html>", encoding="utf-8")
    (out / "digests.html").write_text("<html>DIGESTS</html>", encoding="utf-8")
    (out / "settings").mkdir()
    (out / "settings" / "index.html").write_text("<html>SETTINGS</html>", encoding="utf-8")
    (out / "assets").mkdir()
    (out / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    return out


def _client(tmp_path, console_dir):
    cfg = tmp_path / "config"
    cfg.mkdir(exist_ok=True)
    (cfg / "sources.yaml").write_text("sources: []\n", encoding="utf-8")
    (cfg / "watchlist.yaml").write_text("entities: []\nkeywords: []\n", encoding="utf-8")
    settings = Settings(
        _env_file=None,
        sqlite_path=str(tmp_path / "db.sqlite"),
        config_dir=str(cfg),
        output_dir=str(tmp_path / "outdir"),
        console_dir=str(console_dir),
    )
    return TestClient(create_app(settings, run_digest_fn=lambda **kw: None))


def test_serves_index_at_root(tmp_path):
    c = _client(tmp_path, _console(tmp_path))
    r = c.get("/")
    assert r.status_code == 200
    assert "HOME" in r.text


def test_serves_clean_url_as_html(tmp_path):
    c = _client(tmp_path, _console(tmp_path))
    r = c.get("/digests")
    assert r.status_code == 200
    assert "DIGESTS" in r.text


def test_serves_directory_index(tmp_path):
    c = _client(tmp_path, _console(tmp_path))
    r = c.get("/settings")
    assert r.status_code == 200
    assert "SETTINGS" in r.text


def test_serves_exact_asset(tmp_path):
    c = _client(tmp_path, _console(tmp_path))
    r = c.get("/assets/app.js")
    assert r.status_code == 200
    assert "console.log(1)" in r.text


def test_spa_fallback_for_unknown_path(tmp_path):
    c = _client(tmp_path, _console(tmp_path))
    r = c.get("/totally/unknown/route")
    assert r.status_code == 200
    assert "HOME" in r.text  # SPA shell


def test_unknown_api_does_not_fall_back_to_spa(tmp_path):
    c = _client(tmp_path, _console(tmp_path))
    assert c.get("/api/health").status_code == 200          # real API still works
    r = c.get("/api/nope")
    assert r.status_code == 404                              # NOT the SPA shell
    assert "HOME" not in r.text


def test_console_not_mounted_when_dir_missing(tmp_path):
    c = _client(tmp_path, tmp_path / "does-not-exist")
    assert c.get("/").status_code == 404                    # no catch-all mounted
    assert c.get("/api/health").status_code == 200          # API unaffected


def test_resolver_blocks_path_traversal(tmp_path):
    out = _console(tmp_path)
    assert resolve_static_file(out, "../../../etc/passwd") is None
    assert resolve_static_file(out, "..%2f..%2fsecret") is None
    # sanity: legitimate paths still resolve
    assert resolve_static_file(out, "digests").name == "digests.html"
    assert resolve_static_file(out, "").name == "index.html"
