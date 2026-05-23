from __future__ import annotations

from pathlib import Path

import yaml

from app.core.config import SourceConfig
from app.services.watchlist import Watchlist


def write_sources(config_dir: str | Path, sources: list[SourceConfig]) -> None:
    payload = {"sources": [s.model_dump(exclude_none=True, mode="json") for s in sources]}
    path = Path(config_dir) / "sources.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")


def write_watchlist(config_dir: str | Path, watchlist: Watchlist) -> None:
    payload = {"entities": watchlist.entities, "keywords": watchlist.keywords}
    path = Path(config_dir) / "watchlist.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")
