from __future__ import annotations

import logging
from collections.abc import Callable

from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.api.schemas import DashboardOut, ResolveIn, ResolveOut, RunDetail
from app.core.config import Settings, SourceConfig, load_sources
from app.core.domain import Category, Importance
from app.runner import build_storage, run_digest
from app.services import config_store, feed_discovery, youtube_resolve
from app.services.ratelimit import TokenBucket
from app.services.watchlist import Watchlist, load_watchlist

logger = logging.getLogger(__name__)


def _require_api_key(settings: Settings):
    """Dependency factory: enforce an API key on mutating routes when configured.

    Open (no-op) when ``settings.api_key`` is unset, preserving local/dev behavior.
    Accepts either ``X-API-Key: <key>`` or ``Authorization: Bearer <key>``.
    """

    def dep(
        authorization: str | None = Header(None),
        x_api_key: str | None = Header(None),
    ) -> None:
        if not settings.api_key:
            return  # open when unset (local/dev)
        supplied = x_api_key or (authorization or "").removeprefix("Bearer ").strip()
        if supplied != settings.api_key:
            raise HTTPException(status_code=401, detail="invalid or missing API key")

    return dep


def _rate_limiter(bucket: TokenBucket):
    """Dependency factory: enforce a shared per-process token bucket."""

    def dep() -> None:
        if not bucket.try_acquire():
            raise HTTPException(status_code=429, detail="rate limit exceeded")

    return dep


def create_app(
    settings: Settings | None = None,
    *,
    run_digest_fn: Callable[..., object] = run_digest,
    resolve_channel_id_fn: Callable[..., object] = youtube_resolve.resolve_channel_id,
    discover_feed_fn: Callable[..., object] = feed_discovery.discover_feed,
) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="Catch-Up API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    api = APIRouter(prefix="/api")

    # Shared, per-process limiter for the expensive endpoints (/runs, /resolve).
    rate_bucket = TokenBucket(
        rate_per_sec=settings.rate_limit_refill_per_sec,
        capacity=settings.rate_limit_burst,
    )
    require_api_key = Depends(_require_api_key(settings))
    rate_limit = Depends(_rate_limiter(rate_bucket))

    def storage():
        return build_storage(settings)

    @api.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @api.get("/dashboard", response_model=DashboardOut)
    def dashboard() -> DashboardOut:
        st = storage()
        runs = st.list_runs(limit=10)
        items = st.list_news(limit=500)
        counts: dict[str, int] = {}
        for it in items:
            if it.category:
                counts[it.category.value] = counts.get(it.category.value, 0) + 1
        return DashboardOut(
            latest_run=runs[0] if runs else None,
            recent_runs=runs,
            category_counts=counts,
            total_items=len(items),
        )

    @api.get("/runs")
    def list_runs(limit: int = 20):
        return storage().list_runs(limit=limit)

    @api.get("/runs/{run_id}", response_model=RunDetail)
    def get_run(run_id: str) -> RunDetail:
        st = storage()
        run = st.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        return RunDetail(run=run, items=st.get_items_for_run(run_id))

    @api.get("/news")
    def list_news(category: Category | None = None, importance: Importance | None = None,
                  limit: int = 50):
        return storage().list_news(category=category, importance=importance, limit=limit)

    @api.get("/sources")
    def get_sources():
        return load_sources(settings.config_dir)

    @api.put("/sources", dependencies=[require_api_key])
    def put_sources(sources: list[SourceConfig]):
        config_store.write_sources(settings.config_dir, sources)
        return {"status": "ok", "count": len(sources)}

    @api.get("/watchlist", response_model=Watchlist)
    def get_watchlist() -> Watchlist:
        return load_watchlist(settings.config_dir)

    @api.put("/watchlist", dependencies=[require_api_key])
    def put_watchlist(watchlist: Watchlist):
        config_store.write_watchlist(settings.config_dir, watchlist)
        return {"status": "ok"}

    @api.post("/runs", status_code=202, dependencies=[require_api_key, rate_limit])
    def trigger_run(background: BackgroundTasks):
        background.add_task(run_digest_fn, settings=settings)
        return {"status": "started"}

    @api.post("/sources/resolve", response_model=ResolveOut,
              dependencies=[require_api_key, rate_limit])
    def resolve_source(body: ResolveIn) -> ResolveOut:
        if body.type == "youtube":
            try:
                cid = resolve_channel_id_fn(body.url)
            except HTTPException:
                raise
            except Exception as exc:
                # Log the real cause server-side; return a generic message so we
                # don't leak internals (e.g. SSRF target addresses) to clients.
                logger.warning("youtube resolve failed for %r: %s", body.url, exc)
                raise HTTPException(status_code=400, detail="could not resolve source") from exc
            if not cid:
                raise HTTPException(status_code=422, detail="Could not resolve a YouTube channel from that link")
            return ResolveOut(channel_id=cid)
        elif body.type == "rss":
            try:
                feed = discover_feed_fn(body.url)
            except HTTPException:
                raise
            except Exception as exc:
                logger.warning("rss discover failed for %r: %s", body.url, exc)
                raise HTTPException(status_code=400, detail="could not resolve source") from exc
            if not feed:
                raise HTTPException(status_code=422, detail="No RSS feed found at that URL")
            return ResolveOut(url=feed)
        else:
            raise HTTPException(status_code=400, detail="resolve is not supported for this source type")

    app.include_router(api)
    return app
