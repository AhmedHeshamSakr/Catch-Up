from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.adapters.storage.sqlite_backend import SqliteBackend
from app.core.config import Settings, SourceConfig, load_sources
from app.core.domain import DigestRun, Importance, RawItem, RunStatus, SourceType
from app.core.ports.storage import StorageBackend
from app.pipeline import digest_editor, processing
from app.services import newsapi, normalize, rss, scrape
from app.services.render import excel, markdown
from app.services.render import html as html_render
from app.services.watchlist import load_watchlist


def build_storage(settings: Settings) -> StorageBackend:
    backend = SqliteBackend(settings.sqlite_path)
    backend.init_schema()
    return backend


def _collect(source: SourceConfig, settings: Settings) -> list[RawItem]:
    if source.type == SourceType.RSS:
        return rss.collect(source)
    if source.type == SourceType.API:
        return newsapi.collect(source, settings.gnews_api_key)
    if source.type == SourceType.SCRAPE:
        return scrape.collect(source)
    return []  # SEARCH grounding arrives in Plan 5


def _default_processor(settings: Settings):
    return lambda items: processing.adk_enrich(items, settings)


def _default_narrator(settings: Settings):
    return lambda items: digest_editor.adk_narrate(items, settings)


def run_digest(
    settings: Settings | None = None,
    storage: StorageBackend | None = None,
    processor=None,
    narrator=None,
) -> DigestRun:
    settings = settings or Settings()
    storage = storage or build_storage(settings)
    processor = processor or _default_processor(settings)
    narrator = narrator or _default_narrator(settings)

    run = DigestRun(run_id=uuid.uuid4().hex[:12])
    storage.create_run(run)

    try:
        raws: list[RawItem] = []
        for source in load_sources(settings.config_dir):
            if not source.enabled:
                continue
            try:
                raws.extend(_collect(source, settings))
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

        # --- Intelligence (graceful degradation: collection already succeeded) ---
        try:
            watchlist = load_watchlist(settings.config_dir)
            processing.process_items(
                new_items, processor, watchlist,
                settings.importance_threshold, settings.llm_batch_size)
        except Exception as exc:
            run.source_errors.append(
                {"stage": "processing", "error": str(exc), "ts": datetime.now(UTC).isoformat()})

        run.new = len(new_items)
        run.processed = sum(1 for i in new_items if i.status == "processed")
        run.high_importance = sum(1 for i in new_items if i.importance == Importance.HIGH)
        storage.save_items(new_items)

        rendered = [i for i in new_items if i.status == "processed"] or new_items
        try:
            run.narrative = narrator(rendered) if rendered else None
        except Exception as exc:
            run.source_errors.append(
                {"stage": "narrative", "error": str(exc), "ts": datetime.now(UTC).isoformat()})
        run.outputs["md"] = markdown.write_markdown(run, rendered, settings.output_dir)
        run.outputs["xlsx"] = excel.write_excel(run, rendered, settings.output_dir)
        run.outputs["html"] = html_render.write_html(run, rendered, settings.output_dir)

        run.status = RunStatus.PARTIAL if run.source_errors else RunStatus.SUCCESS
        run.finished_at = datetime.now(UTC)
        storage.finalize_run(run)
    except Exception as exc:
        run.status = RunStatus.FAILED
        run.finished_at = datetime.now(UTC)
        run.source_errors.append({"error": str(exc), "ts": datetime.now(UTC).isoformat()})
        storage.finalize_run(run)
        raise

    return run
