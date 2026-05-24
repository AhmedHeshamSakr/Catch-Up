from app.core.config import SourceConfig, load_sources
from app.core.domain import Category, SourceType
from app.services import config_store
from app.services.watchlist import Watchlist, load_watchlist


def test_write_then_read_sources_roundtrip(tmp_path):
    sources = [
        SourceConfig(id="a", type=SourceType.RSS, name="A", url="https://a/feed",
                     category_hint=Category.AI_TECH, enabled=True),
        SourceConfig(id="b", type=SourceType.API, name="B", query="x",
                     category_hint=Category.GULF_MENA, enabled=False),
    ]
    config_store.write_sources(tmp_path, sources)
    loaded = load_sources(tmp_path)
    assert [s.id for s in loaded] == ["a", "b"]
    assert loaded[1].type == SourceType.API and loaded[1].enabled is False


def test_write_then_read_watchlist_roundtrip(tmp_path):
    config_store.write_watchlist(tmp_path, Watchlist(entities=["OpenAI"], keywords=["merger"]))
    wl = load_watchlist(tmp_path)
    assert wl.entities == ["OpenAI"] and wl.keywords == ["merger"]


def test_write_sources_preserves_existing_comments(tmp_path):
    """A comment in an existing sources.yaml must survive a write_sources call."""
    existing = (
        "# Seed sources. Replace with your curated list anytime.\n"
        "sources:\n"
        "  - id: techcrunch\n"
        "    type: rss\n"
        "    name: TechCrunch\n"
        "    url: https://techcrunch.com/feed/\n"
        "    category_hint: ai_tech\n"
        "    enabled: true\n"
    )
    path = tmp_path / "sources.yaml"
    path.write_text(existing, encoding="utf-8")

    sources = [
        SourceConfig(id="a", type=SourceType.RSS, name="A", url="https://a/feed",
                     category_hint=Category.AI_TECH, enabled=True),
    ]
    config_store.write_sources(tmp_path, sources)

    written = path.read_text(encoding="utf-8")
    assert "# Seed sources. Replace with your curated list anytime." in written

    # The serialized shape must remain loadable by load_sources.
    loaded = load_sources(tmp_path)
    assert [s.id for s in loaded] == ["a"]
