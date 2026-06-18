"""Firestore StorageBackend adapter (optional [firestore] extra).

Takes an injectable client so the same code runs against a real
google.cloud.firestore.Client (prod) and an in-memory fake (tests). Queries use
positional where(field, op, value) and order_by(field, "DESCENDING") so no
google.cloud import is needed at adapter scope. (Real Firestore deprecates
positional where in favor of FieldFilter; swap that during emulator validation
before any real deploy — see tests/integration/test_firestore_emulator.py.)
Flagged-exclusion uses a derived is_flagged boolean (equality), because the
backing store can't combine an inequality filter with an order_by on a
different field.
"""
from __future__ import annotations

from app.core.domain import DigestRun, NewsItem
from app.core.ports.storage import StorageBackend

_DESC = "DESCENDING"  # equals google.cloud.firestore.Query.DESCENDING
_BATCH_LIMIT = 500    # batch-write cap


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
        return {i for i in ids if col.document(i).get().exists}

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
        q = self._items().where("digest_run_id", "==", run_id)
        if not include_flagged:
            q = q.where("is_flagged", "==", False)
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
            q = q.where("category", "==", category.value)
        if importance is not None:
            q = q.where("importance", "==", importance.value)
        if not include_flagged:
            q = q.where("is_flagged", "==", False)
        q = q.order_by("collected_at", _DESC).offset(offset).limit(limit)
        return [NewsItem.model_validate(s.to_dict()) for s in q.stream()]
