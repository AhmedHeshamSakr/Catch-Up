import pytest

from app.adapters.storage.sqlite_backend import SqliteBackend
from tests.unit.storage_contract import StorageContract


class TestSqliteBackend(StorageContract):
    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        self.backend = SqliteBackend(str(tmp_path / "t.db"))
        self.backend.init_schema()


def test_init_schema_migrates_old_database(tmp_path):
    """init_schema must ADD COLUMN onto a pre-existing original-schema DB."""
    import sqlite3

    from app.core.domain import (
        Category,
        DigestRun,
        Importance,
        NewsItem,
        RawItem,
        SourceType,
    )

    db = str(tmp_path / "old.db")
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE news_items "
        "(id TEXT PRIMARY KEY, run_id TEXT, org_id TEXT, data TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE digest_runs "
        "(run_id TEXT PRIMARY KEY, org_id TEXT, status TEXT, data TEXT NOT NULL)"
    )
    conn.commit()
    conn.close()

    backend = SqliteBackend(db)
    backend.init_schema()  # migrates: must not raise

    backend.create_run(DigestRun(run_id="r1"))
    raw = RawItem(source_id="s", source_type=SourceType.RSS, source_name="S",
                  url="https://a/1", title="t")
    item = NewsItem.from_raw(raw, run_id="r1")
    item.category = Category.AI_TECH
    item.importance = Importance.HIGH
    backend.save_items([item])

    assert backend.list_news(category=Category.AI_TECH)[0].url == "https://a/1"
    assert backend.list_runs()[0].run_id == "r1"


def test_init_schema_backfills_populated_legacy_rows(tmp_path):
    """Legacy rows (written before the query columns existed) must become visible
    to filters after migration, AND a legacy status='flagged' row must NOT leak
    into default reads. The empty-table migration test above can't catch this."""
    import sqlite3

    from app.core.domain import (
        Category,
        Importance,
        NewsItem,
        RawItem,
        SourceType,
    )

    db = str(tmp_path / "old.db")
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE news_items "
        "(id TEXT PRIMARY KEY, run_id TEXT, org_id TEXT, data TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE digest_runs "
        "(run_id TEXT PRIMARY KEY, org_id TEXT, status TEXT, data TEXT NOT NULL)"
    )

    def legacy_item(slug, status):
        raw = RawItem(source_id="s", source_type=SourceType.RSS, source_name="S",
                      url=f"https://a/{slug}", title=slug)
        it = NewsItem.from_raw(raw, run_id="r1")
        it.category = Category.AI_TECH
        it.importance = Importance.HIGH
        it.status = status
        return it

    for it in (legacy_item("visible", "processed"), legacy_item("flagged", "flagged")):
        conn.execute(
            "INSERT INTO news_items (id, run_id, org_id, data) VALUES (?, ?, ?, ?)",
            (it.id, it.digest_run_id, "default", it.model_dump_json()),
        )
    conn.commit()
    conn.close()

    backend = SqliteBackend(db)
    backend.init_schema()  # migrates + backfills the query columns from JSON

    urls = {i.url for i in backend.list_news(category=Category.AI_TECH)}
    assert "https://a/visible" in urls          # now findable by category filter
    assert "https://a/flagged" not in urls      # flagged legacy row does NOT leak
    assert "https://a/flagged" in {
        i.url for i in backend.list_news(category=Category.AI_TECH, include_flagged=True)
    }


def test_conn_enables_wal_and_busy_timeout(tmp_path):
    """WAL avoids reader/writer blocking; busy_timeout avoids instant SQLITE_BUSY."""
    from app.adapters.storage.sqlite_backend import SqliteBackend

    be = SqliteBackend(str(tmp_path / "t.db"))
    be.init_schema()
    with be._conn() as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        # >= 30000 confirms the explicit connect(timeout=30), not the ~5000 default.
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] >= 30000
