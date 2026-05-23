from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.api.schemas import DashboardOut, RunDetail
from app.core.config import Settings, SourceConfig, load_sources
from app.core.domain import Category, Importance
from app.runner import build_storage, run_digest
from app.services import config_store
from app.services.watchlist import Watchlist, load_watchlist


def create_app(
    settings: Settings | None = None,
    *,
    run_digest_fn: Callable[..., object] = run_digest,
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

    @api.put("/sources")
    def put_sources(sources: list[SourceConfig]):
        config_store.write_sources(settings.config_dir, sources)
        return {"status": "ok", "count": len(sources)}

    @api.get("/watchlist", response_model=Watchlist)
    def get_watchlist() -> Watchlist:
        return load_watchlist(settings.config_dir)

    @api.put("/watchlist")
    def put_watchlist(watchlist: Watchlist):
        config_store.write_watchlist(settings.config_dir, watchlist)
        return {"status": "ok"}

    @api.post("/runs", status_code=202)
    def trigger_run(background: BackgroundTasks):
        background.add_task(run_digest_fn, settings=settings)
        return {"status": "started"}

    app.include_router(api)
    return app
