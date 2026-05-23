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
