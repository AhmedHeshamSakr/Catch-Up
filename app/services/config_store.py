from __future__ import annotations

import contextlib
import io
import os
import tempfile
import threading
from collections.abc import Iterator
from pathlib import Path

import yaml
from ruamel.yaml import YAML

from app.core.config import SourceConfig
from app.services.watchlist import Watchlist

try:
    import fcntl
except ImportError:  # pragma: no cover — non-POSIX (e.g. Windows)
    fcntl = None  # type: ignore[assignment]

# Serializes config writers IN THIS PROCESS across the whole read-modify-write,
# so two concurrent PUTs can't both read the pre-image and lose one update.
# Reentrant so a write helper can call another lock-guarded helper. A separate
# cross-process file lock (below) covers multiple instances/processes.
_write_lock = threading.RLock()


@contextlib.contextmanager
def _file_lock(path: Path) -> Iterator[None]:
    """Cross-process advisory lock for a config write (held IN ADDITION to the
    in-process RLock), so concurrent workers/CLI/instances can't lose an update
    via a racing read-modify-write. No-op where fcntl is unavailable (Windows)."""
    if fcntl is None:
        yield
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.parent / ".config.lock"
    with open(lock_path, "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


def _fsync_dir(directory: Path) -> None:
    """fsync a directory fd so a rename into it is durable across a crash."""
    try:
        dfd = os.open(str(directory), os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    except OSError:  # pragma: no cover — platform-dependent (e.g. Windows)
        pass


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
            fh.flush()
            os.fsync(fh.fileno())  # contents durable BEFORE the rename
        os.replace(tmp, path)
        _fsync_dir(path.parent)  # the rename itself durable across a crash
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
    # Hold both locks across load -> modify -> atomic replace so concurrent
    # writers (in-process AND cross-process) serialize and no update is lost.
    with _write_lock, _file_lock(path):
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
    with _write_lock, _file_lock(path):
        _atomic_write(path, text)
