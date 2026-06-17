from __future__ import annotations

import logging

from app.core.domain import NewsItem, RawItem
from app.core.ports.storage import StorageBackend

log = logging.getLogger(__name__)


def _norm_title(title: str) -> str:
    return " ".join(title.lower().split())


def normalize_and_dedup(
    raws: list[RawItem], storage: StorageBackend, run_id: str
) -> list[NewsItem]:
    seen_ids: set[str] = set()
    # Title dedup is keyed by (normalized_title, source_id): it removes intra-feed
    # repeats but NO LONGER collapses distinct same-headline stories from DIFFERENT
    # sources (e.g. two unrelated "Market Update" items), which the old global
    # title set silently dropped order-dependently. Cross-source reprint dedup
    # (fuzzy/source-aware) is a later plan. Each TITLE collapse is logged so that
    # near-miss loss is auditable; exact-URL (item.id) and already-stored drops
    # below are unsurprising identity dedup and stay silent. (source_id, not
    # source_name — two sources can share a display name.)
    seen_titles: set[tuple[str, str]] = set()
    candidates: list[NewsItem] = []
    for raw in raws:
        item = NewsItem.from_raw(raw, run_id=run_id)
        if item.id in seen_ids:
            continue
        title_key = (_norm_title(raw.title), raw.source_id)
        if title_key in seen_titles:
            log.info(
                "dedup: dropped repeat title %r from source_id %r",
                raw.title, raw.source_id,
            )
            continue
        seen_ids.add(item.id)
        seen_titles.add(title_key)
        candidates.append(item)
    already = storage.existing_ids([c.id for c in candidates])
    return [c for c in candidates if c.id not in already]
