from __future__ import annotations

from pathlib import Path

import yaml
from ruamel.yaml import YAML

from app.core.config import SourceConfig
from app.services.watchlist import Watchlist


def _ruamel() -> YAML:
    y = YAML()  # round-trip mode (default) — preserves comments and formatting
    y.preserve_quotes = True
    y.indent(mapping=2, sequence=4, offset=2)
    y.allow_unicode = True
    return y


def write_sources(config_dir: str | Path, sources: list[SourceConfig]) -> None:
    """Persist the sources list, preserving existing comments via round-trip YAML.

    When ``sources.yaml`` already exists we load it in ruamel round-trip mode
    and replace only the ``sources`` value, so top-level/header comments survive
    the write. When it does not exist yet we write a fresh document.
    """
    rows = [s.model_dump(exclude_none=True, mode="json") for s in sources]
    path = Path(config_dir) / "sources.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)

    yml = _ruamel()
    if path.exists():
        data = yml.load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            data = {}
    else:
        data = {}
    data["sources"] = rows

    with path.open("w", encoding="utf-8") as fh:
        yml.dump(data, fh)


def write_watchlist(config_dir: str | Path, watchlist: Watchlist) -> None:
    payload = {"entities": watchlist.entities, "keywords": watchlist.keywords}
    path = Path(config_dir) / "watchlist.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")
