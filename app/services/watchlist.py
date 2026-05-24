from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel

from app.core.domain import NewsItem

BOOST = 0.25


class Watchlist(BaseModel):
    entities: list[str] = []
    keywords: list[str] = []

    @property
    def entities_lower(self) -> set[str]:
        return {e.lower() for e in self.entities}

    @property
    def keywords_lower(self) -> set[str]:
        return {k.lower() for k in self.keywords}


def load_watchlist(config_dir: str | Path) -> Watchlist:
    path = Path(config_dir) / "watchlist.yaml"
    if not path.exists():
        return Watchlist()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return Watchlist(entities=data.get("entities") or [], keywords=data.get("keywords") or [])


def watchlist_matched(item: NewsItem, watchlist: Watchlist) -> bool:
    """Return True if the item matches any watchlist entity or keyword."""
    haystack = " ".join(
        [item.title.lower(), (item.summary_en or "").lower()]
        + [e.name.lower() for e in item.entities]
    )
    item_entity_names = {e.name.lower() for e in item.entities}
    return bool(watchlist.entities_lower & item_entity_names) or any(
        kw in haystack for kw in (watchlist.entities_lower | watchlist.keywords_lower)
    )


def apply_boost(item: NewsItem, watchlist: Watchlist) -> None:
    if item.importance_score is None:
        return
    if watchlist_matched(item, watchlist):
        item.importance_score = min(1.0, item.importance_score + BOOST)
