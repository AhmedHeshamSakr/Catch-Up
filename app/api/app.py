from __future__ import annotations

import hmac
import importlib.metadata
import logging
import os
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    Request,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.api.schemas import DashboardOut, ResolveIn, ResolveOut, RunDetail
from app.api.static import mount_console
from app.core.config import REPO_ROOT, Settings, SourceConfig, detect_env_shadow, load_sources
from app.core.domain import Category, Importance
from app.core.env_store import upsert_env
from app.llm.runtime import configure_genai
from app.run_trigger import try_start_run
from app.runner import build_storage, run_digest
from app.services import config_store, feed_discovery, youtube_resolve
from app.services.ratelimit import TokenBucket
from app.services.scheduler import build_scheduler
from app.services.watchlist import Watchlist, load_watchlist

logger = logging.getLogger(__name__)

# Identity returned by /api/health so the desktop launcher can tell "our app is
# already on this port" (reuse) apart from an unrelated local service (Codex #9).
APP_MARKER = "catch-up"
try:
    APP_VERSION = importlib.metadata.version("catch-up")
except importlib.metadata.PackageNotFoundError:  # pragma: no cover
    APP_VERSION = "0.0.0"

# Loopback identities for the Settings write guard.
_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}
_LOOPBACK_IPS = {"127.0.0.1", "::1"}


def _hostname(value: str) -> str:
    """Lowercased hostname of a ``host[:port]`` or full URL ('' if unparseable)."""
    return (urlsplit(value if "//" in value else f"//{value}").hostname or "").lower()


def _require_local_write(request: Request) -> None:
    """Gate the Settings surface to local, same-origin callers.

    The Settings endpoints persist secrets to disk, so loopback bind alone is not
    enough on a local web server. Require: a loopback connecting socket, a loopback
    ``Host`` header (DNS-rebinding defense), and a loopback ``Origin``/``Referer``
    when present (CSRF defense).
    """
    client_host = request.client.host if request.client else ""
    if client_host not in _LOOPBACK_IPS:
        raise HTTPException(status_code=403, detail="settings are local-only")
    if _hostname(request.headers.get("host", "")) not in _LOOPBACK_HOSTS:
        raise HTTPException(status_code=403, detail="settings are local-only")
    ref = request.headers.get("origin") or request.headers.get("referer")
    if ref and _hostname(ref) not in _LOOPBACK_HOSTS:
        raise HTTPException(status_code=403, detail="settings are local-only")


class SettingsPatch(BaseModel):
    """Body for PUT /api/settings. Both fields optional (patch semantics)."""

    google_api_key: str | None = None
    app_port: int | None = Field(default=None, ge=1024, le=65535)


# Cap on the number of news items pulled to compute dashboard category counts.
# Bounded so the dashboard stays cheap; the full list is paginated via /api/news.
_DASHBOARD_NEWS_LIMIT = 500


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
        # Constant-time compare to avoid leaking the key via response timing.
        if not hmac.compare_digest(supplied, settings.api_key):
            raise HTTPException(status_code=401, detail="invalid or missing API key")

    return dep


def _rate_limiter(bucket: TokenBucket):
    """Dependency factory: enforce a shared per-process token bucket."""

    def dep() -> None:
        if not bucket.try_acquire():
            raise HTTPException(status_code=429, detail="rate limit exceeded")

    return dep


def register_product_routes(
    app: FastAPI,
    settings: Settings,
    *,
    run_digest_fn: Callable[..., object] = run_digest,
    resolve_channel_id_fn: Callable[..., object] = youtube_resolve.resolve_channel_id,
    discover_feed_fn: Callable[..., object] = feed_discovery.discover_feed,
) -> None:
    """Attach the product /api/* routes to an existing app (CORS NOT added here).

    Shared by ``create_app()`` (the ``catchup serve`` standalone API) and
    ``app/fast_api_app.py`` (so the deployed ADK container ALSO serves /api/*).
    CORS is the caller's responsibility: ``create_app`` adds its own
    ``CORSMiddleware``; the ADK deploy app passes ``settings.allow_origins`` to
    ``get_fast_api_app``, whose CORS + origin-check middleware already wrap these
    routes — adding a second ``CORSMiddleware`` here would duplicate CORS headers.
    """
    api = APIRouter(prefix="/api")

    # Shared, per-process limiter for the expensive endpoints (/runs, /resolve).
    rate_bucket = TokenBucket(
        rate_per_sec=settings.rate_limit_refill_per_sec,
        capacity=settings.rate_limit_burst,
    )
    require_api_key = Depends(_require_api_key(settings))
    rate_limit = Depends(_rate_limiter(rate_bucket))

    if not settings.api_key:
        logger.warning(
            "API_KEY is unset — the product API is OPEN (no auth on any route). "
            "Set API_KEY for any non-local deployment."
        )

    def storage():
        return build_storage(settings)

    require_local = Depends(_require_local_write)

    # /health is intentionally public (liveness probe). Every other route
    # requires the key WHEN one is configured (no-op when api_key is unset).
    @api.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "app": APP_MARKER, "version": APP_VERSION}

    # Local desktop Settings surface. Local-only (no api_key needed): the write
    # guard restricts both routes to loopback/same-origin callers.
    @api.get("/settings", dependencies=[require_local])
    def get_settings() -> dict[str, object]:
        # Non-secret only: the key value is NEVER returned, just whether one is set.
        return {
            "app_host": settings.app_host,
            "app_port": settings.app_port,
            "gemini_key_set": bool(settings.google_api_key),
        }

    @api.put("/settings", dependencies=[require_local])
    def put_settings(body: SettingsPatch) -> dict[str, list[str]]:
        applied: list[str] = []
        restart_required: list[str] = []
        updates: dict[str, str] = {}
        if body.google_api_key is not None:
            # Overwrite os.environ directly (configure_genai only sets-if-absent,
            # Codex #7); applies to the NEXT run / next genai client, not mid-run.
            settings.google_api_key = body.google_api_key
            os.environ["GOOGLE_API_KEY"] = body.google_api_key
            configure_genai(settings)
            updates["GOOGLE_API_KEY"] = body.google_api_key
            applied.append("google_api_key")
        if body.app_port is not None:
            settings.app_port = body.app_port
            updates["APP_PORT"] = str(body.app_port)
            restart_required.append("app_port")
        if updates:
            upsert_env(settings.env_path, updates)
        return {"applied": applied, "restart_required": restart_required}

    @api.get("/dashboard", response_model=DashboardOut, dependencies=[require_api_key])
    def dashboard() -> DashboardOut:
        st = storage()
        runs = st.list_runs(limit=10)
        items = st.list_news(limit=_DASHBOARD_NEWS_LIMIT)
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

    @api.get("/runs", dependencies=[require_api_key])
    def list_runs(
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ):
        return storage().list_runs(limit=limit, offset=offset)

    @api.get("/runs/{run_id}", response_model=RunDetail, dependencies=[require_api_key])
    def get_run(run_id: str) -> RunDetail:
        st = storage()
        run = st.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        return RunDetail(run=run, items=st.get_items_for_run(run_id))

    @api.get("/news", dependencies=[require_api_key])
    def list_news(category: Category | None = None, importance: Importance | None = None,
                  limit: int = Query(50, ge=1, le=200),
                  offset: int = Query(0, ge=0)):
        return storage().list_news(
            category=category, importance=importance, limit=limit, offset=offset
        )

    @api.get("/sources", dependencies=[require_api_key])
    def get_sources():
        return load_sources(settings.config_dir)

    @api.put("/sources", dependencies=[require_api_key])
    def put_sources(sources: list[SourceConfig]):
        config_store.write_sources(settings.config_dir, sources)
        return {"status": "ok", "count": len(sources)}

    @api.get("/watchlist", response_model=Watchlist, dependencies=[require_api_key])
    def get_watchlist() -> Watchlist:
        return load_watchlist(settings.config_dir)

    @api.put("/watchlist", dependencies=[require_api_key])
    def put_watchlist(watchlist: Watchlist):
        config_store.write_watchlist(settings.config_dir, watchlist)
        return {"status": "ok"}

    @api.post("/runs", status_code=202, dependencies=[require_api_key, rate_limit])
    def trigger_run():
        # Single-flight (shared with the scheduler via app.run_trigger): reject
        # with 409 if a run is already in progress so we don't fan out concurrent
        # pipelines onto one SQLite file.
        run_id = try_start_run(settings, run_digest_fn=run_digest_fn)
        if run_id is None:
            raise HTTPException(status_code=409, detail="a digest run is already in progress")
        return {"status": "started", "run_id": run_id}

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


def create_app(
    settings: Settings | None = None,
    *,
    run_digest_fn: Callable[..., object] = run_digest,
    resolve_channel_id_fn: Callable[..., object] = youtube_resolve.resolve_channel_id,
    discover_feed_fn: Callable[..., object] = feed_discovery.discover_feed,
) -> FastAPI:
    """Standalone product API (run by ``catchup serve``)."""
    settings = settings or Settings()

    # A stray root .env silently overrides app/.env (pydantic env_file precedence),
    # which would make UI/Settings key-saves to app/.env look ignored. Warn loudly.
    shadowed = detect_env_shadow(REPO_ROOT)
    if shadowed:
        logger.warning(
            "Root .env shadows app/.env for: %s. pydantic gives the root .env "
            "precedence, so Settings-page writes to app/.env are ignored for those "
            "keys. Remove them from the root .env (or edit the root .env instead).",
            ", ".join(shadowed),
        )

    @asynccontextmanager
    async def _lifespan(app: FastAPI):
        scheduler = build_scheduler(
            settings, lambda: try_start_run(settings, run_digest_fn=run_digest_fn)
        )
        if scheduler is not None:
            scheduler.start()
        app.state.scheduler = scheduler
        try:
            yield
        finally:
            if app.state.scheduler is not None:
                app.state.scheduler.shutdown(wait=False)

    app = FastAPI(title="Catch-Up API", version="0.1.0", lifespan=_lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allow_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_product_routes(
        app, settings,
        run_digest_fn=run_digest_fn,
        resolve_channel_id_fn=resolve_channel_id_fn,
        discover_feed_fn=discover_feed_fn,
    )
    # Single-port desktop mode: serve the built console at / (after /api so API
    # routes win). Only when the export exists — server/CI runs skip this.
    if Path(settings.console_dir).is_dir():
        mount_console(app, settings.console_dir)
    return app
