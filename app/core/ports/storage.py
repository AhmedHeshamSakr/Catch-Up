from __future__ import annotations

from abc import ABC, abstractmethod

from app.core.domain import DigestRun, NewsItem


class StorageBackend(ABC):
    """Persistence port. Adapters: SQLite (v1), Firestore (prod)."""

    @abstractmethod
    def init_schema(self) -> None: ...

    @abstractmethod
    def existing_ids(self, ids: list[str]) -> set[str]: ...

    @abstractmethod
    def save_items(self, items: list[NewsItem]) -> None: ...

    @abstractmethod
    def get_items_for_run(
        self, run_id: str, *, include_flagged: bool = False
    ) -> list[NewsItem]: ...

    @abstractmethod
    def create_run(self, run: DigestRun) -> None: ...

    @abstractmethod
    def finalize_run(self, run: DigestRun) -> None: ...

    @abstractmethod
    def get_run(self, run_id: str) -> DigestRun | None: ...

    @abstractmethod
    def list_runs(self, limit: int = 20, offset: int = 0) -> list[DigestRun]: ...

    @abstractmethod
    def list_news(
        self, *, category=None, importance=None, limit: int = 50, offset: int = 0,
        include_flagged: bool = False,
    ) -> list[NewsItem]: ...
