"""Firestore StorageBackend adapter (optional [firestore] extra).

Takes an injectable client so the same code runs against a real
google.cloud.firestore.Client (prod) and an in-memory fake (tests). Filtered
queries go through ``_where``, which uses the non-deprecated ``FieldFilter``
when google-cloud-firestore is importable (real backend) and falls back to the
positional ``where(field, op, value)`` form for the in-memory fake (which has no
FieldFilter). order_by uses "DESCENDING".

Flagged-exclusion uses a derived ``is_flagged`` boolean (equality), because the
backing store can't combine an inequality filter with an order_by on a different
field; ``backfill_is_flagged`` sets it on any legacy doc that predates the field
(a missing field does NOT match ``== False`` in real Firestore — unlike SQLite's
NULL handling). Production also needs the composite indexes in
``firestore.indexes.json``; the emulator builds them on the fly.
"""
from __future__ import annotations

from app.core.domain import DigestRun, NewsItem
from app.core.ports.storage import StorageBackend

_DESC = "DESCENDING"  # equals google.cloud.firestore.Query.DESCENDING
_BATCH_LIMIT = 500    # batch-write cap


def _where(query, field: str, op: str, value):
    """Apply a filter, preferring the non-deprecated FieldFilter when
    google-cloud-firestore is installed (real backend); else positional (fake)."""
    try:
        from google.cloud.firestore_v1.base_query import FieldFilter
    except ImportError:
        return query.where(field, op, value)
    return query.where(filter=FieldFilter(field, op, value))


class FirestoreBackend(StorageBackend):
    def __init__(
        self, client, *, items_collection: str = "news_items",
        runs_collection: str = "digest_runs",
    ) -> None:
        self._client = client
        self._items_name = items_collection
        self._runs_name = runs_collection

    def _items(self):
        return self._client.collection(self._items_name)

    def _runs(self):
        return self._client.collection(self._runs_name)

    def init_schema(self) -> None:
        return None  # schemaless

    def existing_ids(self, ids: list[str]) -> set[str]:
        if not ids:
            return set()
        col = self._items()
        # One batched read instead of one get() per id (was O(N) round-trips).
        snaps = self._client.get_all([col.document(i) for i in ids])
        return {s.id for s in snaps if s.exists}

    @staticmethod
    def _item_doc(item: NewsItem) -> dict:
        data = item.model_dump(mode="json")
        data["is_flagged"] = item.status == "flagged"
        return data

    def save_items(self, items: list[NewsItem]) -> None:
        if not items:
            return
        col = self._items()
        for start in range(0, len(items), _BATCH_LIMIT):
            batch = self._client.batch()
            for item in items[start: start + _BATCH_LIMIT]:
                batch.set(col.document(item.id), self._item_doc(item))
            batch.commit()

    def get_items_for_run(
        self, run_id: str, *, include_flagged: bool = False
    ) -> list[NewsItem]:
        q = _where(self._items(), "digest_run_id", "==", run_id)
        if not include_flagged:
            q = _where(q, "is_flagged", "==", False)
        return [NewsItem.model_validate(s.to_dict()) for s in q.stream()]

    def create_run(self, run: DigestRun) -> None:
        self._runs().document(run.run_id).set(run.model_dump(mode="json"))

    def finalize_run(self, run: DigestRun) -> None:
        self.create_run(run)

    def get_run(self, run_id: str) -> DigestRun | None:
        snap = self._runs().document(run_id).get()
        return DigestRun.model_validate(snap.to_dict()) if snap.exists else None

    def list_runs(self, limit: int = 20, offset: int = 0) -> list[DigestRun]:
        q = self._runs().order_by("started_at", _DESC).offset(offset).limit(limit)
        return [DigestRun.model_validate(s.to_dict()) for s in q.stream()]

    def list_news(
        self, *, category=None, importance=None, limit: int = 50, offset: int = 0,
        include_flagged: bool = False,
    ) -> list[NewsItem]:
        q = self._items()
        if category is not None:
            q = _where(q, "category", "==", category.value)
        if importance is not None:
            q = _where(q, "importance", "==", importance.value)
        if not include_flagged:
            q = _where(q, "is_flagged", "==", False)
        q = q.order_by("collected_at", _DESC).offset(offset).limit(limit)
        return [NewsItem.model_validate(s.to_dict()) for s in q.stream()]

    def backfill_is_flagged(self) -> int:
        """One-time migration: set ``is_flagged`` on item docs missing it.

        Real Firestore's ``is_flagged == False`` filter does NOT match a missing
        field, so legacy docs written before the field existed would silently drop
        out of default queries. Scan all item docs and set it where absent, deriving
        the value from the stored ``status`` (a flagged legacy doc must STAY hidden —
        hardcoding ``False`` would un-flag it and leak it into default reads).
        Returns the number of docs updated. (New writes always set it; see
        ``_item_doc``.) Intended as a one-time migration on a quiescent
        collection — for very large collections, page by document id (a single
        ``stream()`` has an RPC time limit).
        """
        col = self._items()
        updated = 0
        for snap in col.stream():
            data = snap.to_dict() or {}
            if "is_flagged" not in data:
                # update() merges ONLY this field — set({**data,...}) would rewrite
                # the whole doc and could clobber a concurrent change.
                col.document(snap.id).update(
                    {"is_flagged": data.get("status") == "flagged"}
                )
                updated += 1
        return updated
