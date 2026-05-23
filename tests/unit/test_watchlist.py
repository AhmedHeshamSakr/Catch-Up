from app.core.domain import Category, Entity, NewsItem, RawItem, SourceType
from app.services.watchlist import Watchlist, apply_boost, load_watchlist


def _item(title="x", entities=None, score=0.2):
    raw = RawItem(source_id="s", source_type=SourceType.RSS, source_name="S",
                  url="https://a.com/1", title=title, category_hint=Category.AI_TECH)
    it = NewsItem.from_raw(raw)
    it.importance_score = score
    it.entities = entities or []
    return it


def test_load_watchlist(tmp_path):
    (tmp_path / "watchlist.yaml").write_text(
        "entities: [OpenAI, Qatar]\nkeywords: [acquisition]\n", encoding="utf-8")
    wl = load_watchlist(tmp_path)
    assert "openai" in wl.entities_lower
    assert "acquisition" in wl.keywords_lower


def test_boost_on_entity_match_increases_score_and_caps_at_one():
    wl = Watchlist(entities=["OpenAI"], keywords=[])
    it = _item(entities=[Entity(name="OpenAI", type="org")], score=0.9)
    apply_boost(it, wl)
    assert it.importance_score == 1.0  # 0.9 + 0.25 capped


def test_boost_on_keyword_in_title():
    wl = Watchlist(entities=[], keywords=["acquisition"])
    it = _item(title="Big Acquisition announced", score=0.2)
    apply_boost(it, wl)
    assert abs(it.importance_score - 0.45) < 1e-9


def test_no_boost_when_no_match():
    wl = Watchlist(entities=["Nvidia"], keywords=["merger"])
    it = _item(title="unrelated", score=0.3)
    apply_boost(it, wl)
    assert it.importance_score == 0.3
