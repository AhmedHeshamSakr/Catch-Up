import pytest

from app.adapters.storage.firestore_backend import FirestoreBackend
from tests.unit.fake_firestore import FakeFirestoreClient
from tests.unit.storage_contract import StorageContract


class TestFirestoreBackend(StorageContract):
    @pytest.fixture(autouse=True)
    def _setup(self):
        self.backend = FirestoreBackend(FakeFirestoreClient())
        self.backend.init_schema()  # no-op, must not raise


def test_save_items_sets_is_flagged_field():
    from app.core.domain import NewsItem, RawItem, SourceType
    client = FakeFirestoreClient()
    be = FirestoreBackend(client)
    raw = RawItem(source_id="s", source_type=SourceType.RSS, source_name="S",
                  url="https://a/1", title="t")
    item = NewsItem.from_raw(raw, run_id="r1")
    item.status = "flagged"
    be.save_items([item])
    doc = client.collection("news_items").document(item.id).get().to_dict()
    assert doc["is_flagged"] is True


def test_backfill_is_flagged_recovers_legacy_docs():
    """A legacy doc missing is_flagged is invisible to default queries (a missing
    field doesn't match == False) until backfilled."""
    client = FakeFirestoreClient()
    be = FirestoreBackend(client)
    legacy = {
        "id": "legacy1", "source_id": "s", "source_type": "rss", "source_name": "S",
        "url": "https://a/legacy", "title": "t", "category": "ai_tech",
        "collected_at": "2026-05-01T00:00:00+00:00", "status": "processed",
        "digest_run_id": "r1",
    }
    client.collection("news_items").document("legacy1").set(legacy)
    # Missing is_flagged → filtered out by the default is_flagged == False query.
    assert be.list_news() == []
    assert be.backfill_is_flagged() == 1
    assert {i.url for i in be.list_news()} == {"https://a/legacy"}
    # Idempotent: a second run updates nothing.
    assert be.backfill_is_flagged() == 0
