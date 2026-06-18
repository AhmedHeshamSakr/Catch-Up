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
