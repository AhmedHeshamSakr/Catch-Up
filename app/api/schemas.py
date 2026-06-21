from __future__ import annotations

from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator

from app.core.domain import DigestRun, NewsItem


class DashboardOut(BaseModel):
    latest_run: DigestRun | None
    recent_runs: list[DigestRun]
    category_counts: dict[str, int]
    total_items: int


class RunDetail(BaseModel):
    run: DigestRun
    items: list[NewsItem]


class ResolveIn(BaseModel):
    type: str = Field(max_length=32)
    url: str = Field(max_length=2048)

    @field_validator("url")
    @classmethod
    def _reject_dangerous_scheme(cls, value: str) -> str:
        # The resolve input may be a full URL, a YouTube @handle, or a bare
        # channel id. Only reject values that carry an explicit, non-http(s)
        # scheme (e.g. file:, javascript:); schemeless handles/ids pass through.
        scheme = urlparse(value).scheme
        if scheme and scheme not in ("http", "https"):
            raise ValueError(f"url scheme not allowed: {scheme!r}")
        return value


class ResolveOut(BaseModel):
    channel_id: str | None = None
    url: str | None = None
    name: str | None = None
