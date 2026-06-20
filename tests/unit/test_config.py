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


def test_schedule_defaults(monkeypatch):
    for k in ("SCHEDULE_ENABLED", "SCHEDULE_CRON", "SCHEDULE_TIMEZONE"):
        monkeypatch.delenv(k, raising=False)
    s = Settings(_env_file=None)
    assert s.schedule_enabled is False
    assert s.schedule_cron == ""
    assert s.schedule_timezone == "UTC"


def test_apscheduler_importable():
    import apscheduler  # noqa: F401


def test_vertex_defaults(monkeypatch):
    for k in ("USE_VERTEXAI", "GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION"):
        monkeypatch.delenv(k, raising=False)
    s = Settings(_env_file=None)
    assert s.use_vertexai is False
    assert s.google_cloud_project == ""
    assert s.google_cloud_location == "global"


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


def test_app_port_host_defaults(monkeypatch):
    # Desktop single-port launcher reads these; default to localhost:8000.
    for k in ("APP_PORT", "APP_HOST"):
        monkeypatch.delenv(k, raising=False)
    s = Settings(_env_file=None)
    assert s.app_port == 8000
    assert s.app_host == "127.0.0.1"


def test_app_port_host_from_env(monkeypatch):
    monkeypatch.setenv("APP_PORT", "9123")
    monkeypatch.setenv("APP_HOST", "0.0.0.0")
    s = Settings(_env_file=None)
    assert s.app_port == 9123
    assert s.app_host == "0.0.0.0"


def test_detect_env_shadow_returns_overlapping_keys(tmp_path):
    # A root .env that re-defines a key in app/.env silently wins (pydantic
    # env_file later-file precedence), which would make a UI key-save look broken.
    from app.core.config import detect_env_shadow

    (tmp_path / ".env").write_text("GOOGLE_API_KEY=root\nUNIQUE_ROOT=1\n", encoding="utf-8")
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / ".env").write_text(
        "GOOGLE_API_KEY=app\n# comment\nAPP_PORT=8000\n", encoding="utf-8"
    )
    assert detect_env_shadow(tmp_path) == ["GOOGLE_API_KEY"]


def test_detect_env_shadow_empty_without_root_env(tmp_path):
    from app.core.config import detect_env_shadow

    (tmp_path / "app").mkdir()
    (tmp_path / "app" / ".env").write_text("GOOGLE_API_KEY=app\n", encoding="utf-8")
    assert detect_env_shadow(tmp_path) == []


def test_detect_env_shadow_flags_root_managed_key_even_if_app_lacks_it(tmp_path):
    # The nastier case: root .env owns the key, app/.env doesn't define it yet — a
    # UI save to app/.env is still overridden, so it MUST be flagged.
    from app.core.config import detect_env_shadow

    (tmp_path / ".env").write_text("GOOGLE_API_KEY=root\nAPP_PORT=9000\n", encoding="utf-8")
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / ".env").write_text("APP_HOST=127.0.0.1\n", encoding="utf-8")
    assert detect_env_shadow(tmp_path) == ["APP_PORT", "GOOGLE_API_KEY"]


def test_detect_env_shadow_ignores_unmanaged_root_keys(tmp_path):
    from app.core.config import detect_env_shadow

    (tmp_path / ".env").write_text("SOME_OTHER=1\n", encoding="utf-8")
    assert detect_env_shadow(tmp_path) == []
