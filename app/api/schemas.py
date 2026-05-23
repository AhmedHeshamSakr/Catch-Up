from __future__ import annotations

from pydantic import BaseModel

from app.core.domain import DigestRun, NewsItem


class DashboardOut(BaseModel):
    latest_run: DigestRun | None
    recent_runs: list[DigestRun]
    category_counts: dict[str, int]
    total_items: int


class RunDetail(BaseModel):
    run: DigestRun
    items: list[NewsItem]
