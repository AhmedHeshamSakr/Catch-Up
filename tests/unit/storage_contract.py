from datetime import datetime, timezone

from app.core.domain import (
    Category, DigestRun, NewsItem, RawItem, RunStatus, SourceType,
)


class StorageContract:
    """Reusable contract. Subclasses set self.backend (fresh, schema-inited)."""

    backend = None  # set by subclass fixture

    def _item(self, url: str = "https://x.com/a", title: str = "t") -> NewsItem:
        raw = RawItem(
            source_id="s", source_type=SourceType.RSS, source_name="S",
            url=url, title=title, category_hint=Category.AI_TECH,
        )
        return NewsItem.from_raw(raw, run_id="r1")

    def test_save_and_get_items_for_run(self):
        self.backend.save_items([self._item()])
        items = self.backend.get_items_for_run("r1")
        assert len(items) == 1
        assert items[0].url == "https://x.com/a"

    def test_existing_ids_detects_only_saved(self):
        item = self._item()
        self.backend.save_items([item])
        assert self.backend.existing_ids([item.id, "missing"]) == {item.id}

    def test_existing_ids_empty_input(self):
        assert self.backend.existing_ids([]) == set()

    def test_create_and_finalize_run_roundtrip(self):
        run = DigestRun(run_id="r1")
        self.backend.create_run(run)
        run.status = RunStatus.SUCCESS
        run.finished_at = datetime.now(timezone.utc)
        run.collected = 5
        self.backend.finalize_run(run)
        got = self.backend.get_run("r1")
        assert got is not None
        assert got.status == RunStatus.SUCCESS
        assert got.collected == 5

    def test_get_missing_run_returns_none(self):
        assert self.backend.get_run("nope") is None
