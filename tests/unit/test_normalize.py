import pytest

from app.adapters.storage.sqlite_backend import SqliteBackend
from app.core.domain import Category, NewsItem, RawItem, SourceType
from app.services import normalize


@pytest.fixture
def storage(tmp_path):
    backend = SqliteBackend(str(tmp_path / "t.db"))
    backend.init_schema()
    return backend


def _raw(url: str, title: str) -> RawItem:
    return RawItem(
        source_id="s", source_type=SourceType.RSS, source_name="S",
        url=url, title=title, category_hint=Category.AI_TECH,
    )


def test_dedups_within_batch_by_url_and_title(storage):
    raws = [
        _raw("https://a.com/1", "Same Title"),
        _raw("https://a.com/1", "Same Title"),           # dup url
        _raw("https://a.com/2", "same   title"),          # dup title (normalized)
        _raw("https://a.com/3", "Different"),
    ]
    out = normalize.normalize_and_dedup(raws, storage, run_id="r1")
    urls = {i.url for i in out}
    assert urls == {"https://a.com/1", "https://a.com/3"}


def test_filters_items_already_in_storage(storage):
    existing = NewsItem.from_raw(_raw("https://a.com/1", "Old"), run_id="r0")
    storage.save_items([existing])
    out = normalize.normalize_and_dedup(
        [_raw("https://a.com/1", "Old"), _raw("https://a.com/9", "New")],
        storage, run_id="r1",
    )
    assert [i.url for i in out] == ["https://a.com/9"]
