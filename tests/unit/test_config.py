from app.core.config import Settings, SourceConfig, load_sources
from app.core.domain import Category, SourceType


def test_load_sources_parses_yaml(tmp_path):
    (tmp_path / "sources.yaml").write_text(
        "sources:\n"
        "  - id: techcrunch\n"
        "    type: rss\n"
        "    name: TechCrunch\n"
        "    url: https://techcrunch.com/feed/\n"
        "    category_hint: ai_tech\n"
        "    enabled: true\n",
        encoding="utf-8",
    )
    sources = load_sources(tmp_path)
    assert len(sources) == 1
    s = sources[0]
    assert isinstance(s, SourceConfig)
    assert s.id == "techcrunch"
    assert s.type == SourceType.RSS
    assert s.category_hint == Category.AI_TECH
    assert s.enabled is True


def test_settings_loads_key_from_app_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / ".env").write_text("GOOGLE_API_KEY=from_app_env\n", encoding="utf-8")
    # No ./.env present; key must still load from app/.env
    s = Settings()
    assert s.google_api_key == "from_app_env"


def test_root_env_overrides_app_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    (tmp_path / ".env").write_text("GOOGLE_API_KEY=root\n", encoding="utf-8")
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / ".env").write_text("GOOGLE_API_KEY=app\n", encoding="utf-8")
    # Root .env should win when both are present
    s = Settings()
    assert s.google_api_key == "root"


def test_allow_origins_parses_comma_separated_env(monkeypatch):
    monkeypatch.setenv("ALLOW_ORIGINS", "https://a.example , https://b.example")
    s = Settings(_env_file=None)
    assert s.allow_origins == ["https://a.example", "https://b.example"]


def test_allow_origins_defaults_to_localhost(monkeypatch):
    monkeypatch.delenv("ALLOW_ORIGINS", raising=False)
    assert Settings(_env_file=None).allow_origins == ["http://localhost:3000"]


def test_session_defaults(monkeypatch):
    # Clear so the conftest's suite-wide SESSION_BACKEND=memory (and any CI env)
    # doesn't mask the real field defaults.
    monkeypatch.delenv("SESSION_BACKEND", raising=False)
    monkeypatch.delenv("SESSION_DB_URL", raising=False)
    s = Settings(_env_file=None)
    assert s.session_backend == "database"
    assert s.session_db_url == ""


def test_greenlet_and_aiosqlite_importable():
    # DatabaseSessionService's async SQLite engine needs both at runtime.
    import aiosqlite  # noqa: F401
    import greenlet  # noqa: F401
