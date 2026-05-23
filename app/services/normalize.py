from __future__ import annotations

from app.core.domain import NewsItem, RawItem
from app.core.ports.storage import StorageBackend


def _norm_title(title: str) -> str:
    return " ".join(title.lower().split())


def normalize_and_dedup(
    raws: list[RawItem], storage: StorageBackend, run_id: str
) -> list[NewsItem]:
    seen_ids: set[str] = set()
    seen_titles: set[str] = set()
    candidates: list[NewsItem] = []
    for raw in raws:
        item = NewsItem.from_raw(raw, run_id=run_id)
        title_key = _norm_title(raw.title)
        if item.id in seen_ids or title_key in seen_titles:
            continue
        seen_ids.add(item.id)
        seen_titles.add(title_key)
        candidates.append(item)
    already = storage.existing_ids([c.id for c in candidates])
    return [c for c in candidates if c.id not in already]
