from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import ClassVar

from app.core.domain import DigestRun, NewsItem
from app.core.ports.storage import StorageBackend


class SqliteBackend(StorageBackend):
    # Columns added after the original schema — migrated in on existing DBs.
    _NEWS_COLUMNS: ClassVar[dict[str, str]] = {
        "category": "TEXT", "importance": "TEXT", "collected_at": "TEXT",
    }
    _RUN_COLUMNS: ClassVar[dict[str, str]] = {"started_at": "TEXT"}

    def __init__(self, path: str) -> None:
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _ensure_columns(
        conn: sqlite3.Connection, table: str, columns: dict[str, str]
    ) -> None:
        existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        for name, coltype in columns.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {coltype}")

    def init_schema(self) -> None:
        with self._conn() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS news_items ("
                "id TEXT PRIMARY KEY, run_id TEXT, org_id TEXT, category TEXT, "
                "importance TEXT, collected_at TEXT, data TEXT NOT NULL)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS digest_runs ("
                "run_id TEXT PRIMARY KEY, org_id TEXT, status TEXT, "
                "started_at TEXT, data TEXT NOT NULL)"
            )
            # Migrate older databases that predate the query columns.
            self._ensure_columns(conn, "news_items", self._NEWS_COLUMNS)
            self._ensure_columns(conn, "digest_runs", self._RUN_COLUMNS)
            for col in ("category", "importance", "collected_at", "run_id"):
                conn.execute(
                    f"CREATE INDEX IF NOT EXISTS idx_news_{col} ON news_items({col})"
                )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_runs_started ON digest_runs(started_at)"
            )

    def existing_ids(self, ids: list[str]) -> set[str]:
        if not ids:
            return set()
        placeholders = ",".join("?" * len(ids))
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT id FROM news_items WHERE id IN ({placeholders})", ids
            ).fetchall()
        return {row["id"] for row in rows}

    def save_items(self, items: list[NewsItem]) -> None:
        with self._conn() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO news_items "
                "(id, run_id, org_id, category, importance, collected_at, data) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        i.id, i.digest_run_id, i.org_id,
                        i.category.value if i.category else None,
                        i.importance.value if i.importance else None,
                        i.collected_at.isoformat(),
                        i.model_dump_json(),
                    )
                    for i in items
                ],
            )

    def get_items_for_run(self, run_id: str) -> list[NewsItem]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT data FROM news_items WHERE run_id = ?", (run_id,)
            ).fetchall()
        return [NewsItem.model_validate_json(row["data"]) for row in rows]

    def create_run(self, run: DigestRun) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO digest_runs "
                "(run_id, org_id, status, started_at, data) VALUES (?, ?, ?, ?, ?)",
                (run.run_id, run.org_id, run.status.value, run.started_at.isoformat(),
                 run.model_dump_json()),
            )

    def finalize_run(self, run: DigestRun) -> None:
        self.create_run(run)

    def get_run(self, run_id: str) -> DigestRun | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT data FROM digest_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        return DigestRun.model_validate_json(row["data"]) if row else None

    def list_runs(self, limit: int = 20, offset: int = 0) -> list[DigestRun]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT data FROM digest_runs ORDER BY started_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [DigestRun.model_validate_json(r["data"]) for r in rows]

    def list_news(
        self, *, category=None, importance=None, limit: int = 50, offset: int = 0
    ) -> list[NewsItem]:
        clauses, params = [], []
        if category is not None:
            clauses.append("category = ?")
            params.append(category.value)
        if importance is not None:
            clauses.append("importance = ?")
            params.append(importance.value)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        params.extend([limit, offset])
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT data FROM news_items{where} "
                "ORDER BY collected_at DESC LIMIT ? OFFSET ?",
                params,
            ).fetchall()
        return [NewsItem.model_validate_json(r["data"]) for r in rows]
