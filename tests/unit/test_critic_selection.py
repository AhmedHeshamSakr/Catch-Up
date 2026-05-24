"""Unit tests for select_for_critique — B2. Fully offline."""
from __future__ import annotations

from app.core.config import Settings
from app.core.domain import Category, Entity, Importance, NewsItem, RawItem, SourceType
from app.pipeline.critic import select_for_critique
from app.services.watchlist import Watchlist


def _item(url: str, title: str, importance: Importance | None = None,
          importance_score: float | None = None, entities=None,
          summary_en: str = "") -> NewsItem:
    raw = RawItem(source_id="s", source_type=SourceType.RSS, source_name="S",
                  url=url, title=title, category_hint=Category.AI_TECH)
    it = NewsItem.from_raw(raw)
    it.importance = importance
    it.importance_score = importance_score
    it.entities = entities or []
    it.summary_en = summary_en
    return it


def _settings(**kwargs) -> Settings:
    defaults = {
        "google_api_key": "",
        "sqlite_path": ":memory:",
        "config_dir": "/tmp",
        "output_dir": "/tmp",
        "critic_enabled": True,
        "critic_min_importance": Importance.HIGH,
        "critic_check_watchlisted": True,
        "critic_action": "downrank",
    }
    defaults.update(kwargs)
    return Settings(**defaults)


def test_high_importance_item_is_selected():
    item = _item("https://a.com/1", "Big news", importance=Importance.HIGH, importance_score=0.9)
    settings = _settings()
    selected = select_for_critique([item], Watchlist(), settings)
    assert item in selected


def test_medium_non_watchlisted_not_selected():
    item = _item("https://a.com/2", "Meh news", importance=Importance.MEDIUM, importance_score=0.5)
    settings = _settings()
    selected = select_for_critique([item], Watchlist(), settings)
    assert item not in selected


def test_medium_watchlisted_is_selected_when_check_enabled():
    item = _item("https://a.com/3", "OpenAI medium story",
                 importance=Importance.MEDIUM, importance_score=0.5,
                 entities=[Entity(name="OpenAI", type="org")])
    wl = Watchlist(entities=["OpenAI"], keywords=[])
    settings = _settings(critic_check_watchlisted=True)
    selected = select_for_critique([item], wl, settings)
    assert item in selected


def test_medium_watchlisted_not_selected_when_check_disabled():
    item = _item("https://a.com/4", "OpenAI medium story",
                 importance=Importance.MEDIUM, importance_score=0.5,
                 entities=[Entity(name="OpenAI", type="org")])
    wl = Watchlist(entities=["OpenAI"], keywords=[])
    settings = _settings(critic_check_watchlisted=False)
    selected = select_for_critique([item], wl, settings)
    assert item not in selected


def test_critic_disabled_returns_empty():
    item = _item("https://a.com/5", "Big news", importance=Importance.HIGH, importance_score=0.9)
    settings = _settings(critic_enabled=False)
    selected = select_for_critique([item], Watchlist(), settings)
    assert selected == []


def test_importance_none_not_selected_by_importance_rule():
    item = _item("https://a.com/6", "Unknown importance")
    item.importance = None
    settings = _settings()
    selected = select_for_critique([item], Watchlist(), settings)
    assert item not in selected


def test_importance_ordering_medium_min_includes_high():
    """When critic_min_importance=MEDIUM, both MEDIUM and HIGH items qualify."""
    high_item = _item("https://a.com/7", "High news", importance=Importance.HIGH, importance_score=0.9)
    medium_item = _item("https://a.com/8", "Medium news", importance=Importance.MEDIUM, importance_score=0.5)
    low_item = _item("https://a.com/9", "Low news", importance=Importance.LOW, importance_score=0.1)
    settings = _settings(critic_min_importance=Importance.MEDIUM)
    selected = select_for_critique([high_item, medium_item, low_item], Watchlist(), settings)
    assert high_item in selected
    assert medium_item in selected
    assert low_item not in selected


def test_low_importance_with_keyword_match_selected():
    item = _item("https://a.com/10", "acquisition news",
                 importance=Importance.LOW, importance_score=0.1)
    wl = Watchlist(entities=[], keywords=["acquisition"])
    settings = _settings(critic_check_watchlisted=True)
    selected = select_for_critique([item], wl, settings)
    assert item in selected
