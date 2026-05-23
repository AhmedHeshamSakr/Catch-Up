from datetime import UTC, datetime

from app.core.domain import (
    Category,
    DigestRun,
    NewsItem,
    RawItem,
    RunStatus,
    SourceType,
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
        run.finished_at = datetime.now(UTC)
        run.collected = 5
        self.backend.finalize_run(run)
        got = self.backend.get_run("r1")
        assert got is not None
        assert got.status == RunStatus.SUCCESS
        assert got.collected == 5

    def test_get_missing_run_returns_none(self):
        assert self.backend.get_run("nope") is None

    def test_list_runs_most_recent_first(self):
        from datetime import UTC, datetime

        from app.core.domain import DigestRun
        for i, rid in enumerate(["r1", "r2", "r3"]):
            run = DigestRun(run_id=rid, started_at=datetime(2026, 5, 20 + i, tzinfo=UTC))
            self.backend.create_run(run)
        runs = self.backend.list_runs(limit=2)
        assert [r.run_id for r in runs] == ["r3", "r2"]

    def test_list_news_filters_by_category_and_importance(self):
        from app.core.domain import Category, Importance, NewsItem, RawItem, SourceType
        def mk(url, cat, imp):
            raw = RawItem(source_id="s", source_type=SourceType.RSS, source_name="S", url=url, title="t")
            it = NewsItem.from_raw(raw, run_id="r1")
            it.category = cat
            it.importance = imp
            return it
        self.backend.save_items([
            mk("https://a/1", Category.AI_TECH, Importance.HIGH),
            mk("https://a/2", Category.AI_TECH, Importance.LOW),
            mk("https://a/3", Category.GULF_MENA, Importance.HIGH),
        ])
        ai = self.backend.list_news(category=Category.AI_TECH)
        assert {i.url for i in ai} == {"https://a/1", "https://a/2"}
        high = self.backend.list_news(importance=Importance.HIGH)
        assert {i.url for i in high} == {"https://a/1", "https://a/3"}
        assert len(self.backend.list_news()) == 3

    def test_list_news_combined_filter_and_ordering(self):
        from datetime import UTC, datetime

        from app.core.domain import Category, Importance, NewsItem, RawItem, SourceType

        def mk(url, cat, imp, when):
            raw = RawItem(source_id="s", source_type=SourceType.RSS,
                          source_name="S", url=url, title="t")
            it = NewsItem.from_raw(raw, run_id="r1")
            it.category = cat
            it.importance = imp
            it.collected_at = when
            return it

        self.backend.save_items([
            mk("https://a/1", Category.AI_TECH, Importance.HIGH, datetime(2026, 5, 21, tzinfo=UTC)),
            mk("https://a/2", Category.AI_TECH, Importance.HIGH, datetime(2026, 5, 23, tzinfo=UTC)),
            mk("https://a/3", Category.AI_TECH, Importance.LOW, datetime(2026, 5, 22, tzinfo=UTC)),
        ])
        # combined AND filter → only the two HIGH AI items, newest (collected_at) first
        both = self.backend.list_news(category=Category.AI_TECH, importance=Importance.HIGH)
        assert [i.url for i in both] == ["https://a/2", "https://a/1"]
        # limit respected
        assert len(self.backend.list_news(limit=1)) == 1
