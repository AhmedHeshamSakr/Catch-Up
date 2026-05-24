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
