from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.adapters.storage.sqlite_backend import SqliteBackend
from app.core.config import Settings, SourceConfig, load_sources
from app.core.domain import DigestRun, RawItem, RunStatus, SourceType
from app.core.ports.storage import StorageBackend
from app.services import normalize, rss
from app.services.render import markdown


def build_storage(settings: Settings) -> StorageBackend:
    backend = SqliteBackend(settings.sqlite_path)
    backend.init_schema()
    return backend


def _collect(source: SourceConfig) -> list[RawItem]:
    if source.type == SourceType.RSS:
        return rss.collect(source)
    return []  # SCRAPE / API / SEARCH arrive in Plan 3


def run_digest(
    settings: Settings | None = None, storage: StorageBackend | None = None
) -> DigestRun:
    settings = settings or Settings()
    storage = storage or build_storage(settings)

    run = DigestRun(run_id=uuid.uuid4().hex[:12])
    storage.create_run(run)

    raws: list[RawItem] = []
    for source in load_sources(settings.config_dir):
        if not source.enabled:
            continue
        try:
            raws.extend(_collect(source))
        except Exception as exc:  # per-source isolation
            run.source_errors.append(
                {
                    "source_id": source.id,
                    "error": str(exc),
                    "ts": datetime.now(UTC).isoformat(),
                }
            )

    run.collected = len(raws)
    new_items = normalize.normalize_and_dedup(raws, storage, run.run_id)
    for item in new_items:
        item.status = "processed"  # skeleton: real LLM processing in Plan 2
    run.new = len(new_items)
    run.processed = len(new_items)
    storage.save_items(new_items)

    run.outputs["md"] = markdown.write_markdown(run, new_items, settings.output_dir)
    run.status = RunStatus.PARTIAL if run.source_errors else RunStatus.SUCCESS
    run.finished_at = datetime.now(UTC)
    storage.finalize_run(run)
    return run
