from __future__ import annotations

import io
import os
import tempfile
import threading
from pathlib import Path

import yaml
from ruamel.yaml import YAML

from app.core.config import SourceConfig
from app.services.watchlist import Watchlist

# Serializes config writers IN THIS PROCESS across the whole read-modify-write,
# so two concurrent PUTs can't both read the pre-image and lose one update.
# Reentrant so a write helper can call another lock-guarded helper. Multi-
# instance deployments need a cross-process lock (production milestone).
_write_lock = threading.RLock()


def _ruamel() -> YAML:
    y = YAML()  # round-trip mode (default) — preserves comments and formatting
    y.preserve_quotes = True
    y.indent(mapping=2, sequence=4, offset=2)
    y.allow_unicode = True
    return y


def _atomic_write(path: Path, text: str) -> None:
    """Write to a unique temp file in the same dir, then os.replace() onto target.

    os.replace is atomic on POSIX and Windows, so a concurrent reader sees
    either the old or the new file in full — never a truncated/half-written one.
    ``mkstemp`` guarantees a collision-free temp name (no clobbering a stale
    file); the temp is removed if anything fails before the replace.
    """
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


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
    # Hold the lock across load -> modify -> atomic replace so concurrent writers
    # serialize and no update is lost to a read-modify-write race.
    with _write_lock:
        if path.exists():
            data = yml.load(path.read_text(encoding="utf-8")) or {}
            if not isinstance(data, dict):
                data = {}
        else:
            data = {}
        data["sources"] = rows
        buf = io.StringIO()
        yml.dump(data, buf)
        _atomic_write(path, buf.getvalue())


def write_watchlist(config_dir: str | Path, watchlist: Watchlist) -> None:
    payload = {"entities": watchlist.entities, "keywords": watchlist.keywords}
    path = Path(config_dir) / "watchlist.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
    with _write_lock:
        _atomic_write(path, text)
