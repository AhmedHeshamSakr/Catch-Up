"""Atomic, dotenv-safe writer for the local config file (``app/.env``).

The desktop Settings page persists the Gemini key and port here. Writes must be
crash-safe (no half-written secrets), preserve unrelated lines/comments, quote
values so they round-trip through python-dotenv (the parser pydantic-settings
uses), keep the file private (0600), and serialize concurrent writers.
"""

from __future__ import annotations

import os
import tempfile
import threading
from pathlib import Path

# Serialize writers in-process so a read-modify-write never loses a concurrent
# update. (Cross-process contention isn't a concern for a single-user local app.)
_LOCK = threading.Lock()

# Characters that make an unquoted dotenv value ambiguous (whitespace, comment
# marker, quotes, assignment/expansion chars, escapes, newlines).
_NEEDS_QUOTING = set(" \t\"'#=$`\\\n\r")


def _format_value(value: str) -> str:
    """Render a value for a dotenv line, double-quoting + escaping when needed."""
    if value != "" and not any(c in _NEEDS_QUOTING for c in value):
        return value
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )
    return f'"{escaped}"'


def _line_key(stripped: str) -> tuple[str, str] | None:
    """For a non-comment ``KEY=...`` line, return (prefix, bare_key); else None."""
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return None
    key = stripped.split("=", 1)[0].strip()
    if key.startswith("export "):
        return "export ", key[len("export ") :].strip()
    return "", key


def upsert_env(path: str | Path, updates: dict[str, str]) -> None:
    """Atomically upsert ``KEY=VALUE`` pairs into the dotenv file at ``path``.

    Existing keys are rewritten in place (order preserved); new keys are appended.
    Comments and unrelated lines are kept verbatim. The file is written via a
    sibling temp file + ``os.replace`` (atomic) and forced to mode 0600.
    """
    path = Path(path)
    with _LOCK:
        existing = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
        remaining = dict(updates)
        out: list[str] = []
        for line in existing:
            parsed = _line_key(line.strip())
            if parsed is not None and parsed[1] in remaining:
                prefix, bare = parsed
                out.append(f"{prefix}{bare}={_format_value(remaining.pop(bare))}")
            else:
                out.append(line)
        for key, value in remaining.items():
            out.append(f"{key}={_format_value(value)}")
        data = "\n".join(out) + ("\n" if out else "")

        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".env.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.chmod(tmp, 0o600)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
