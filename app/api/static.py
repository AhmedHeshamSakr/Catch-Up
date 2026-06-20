"""Serve the built Next.js console (``frontend/out``) from the same FastAPI
process as ``/api/*`` (single-port desktop mode).

Next's static export (``output: 'export'``, default ``trailingSlash: false``)
emits ``digests.html`` rather than ``digests/index.html``, which a plain
``StaticFiles`` mount won't resolve. The resolver below tries, in order: the
exact file, ``<path>.html``, then ``<path>/index.html``, then falls back to the
SPA shell (``index.html``). ``/api/*`` is never served the shell.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response


def resolve_static_file(static_dir: str | Path, url_path: str) -> Path | None:
    """Map a URL path to a file under ``static_dir``, or None if none matches.

    Guards against path traversal: any candidate that resolves outside
    ``static_dir`` is rejected.
    """
    base = Path(static_dir).resolve()
    rel = url_path.strip("/")
    if rel:
        candidates = [base / rel, base / f"{rel}.html", base / rel / "index.html"]
    else:
        candidates = [base / "index.html"]
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except (OSError, RuntimeError, ValueError):
            continue
        if resolved != base and base not in resolved.parents:
            continue  # escaped the static root — reject
        if resolved.is_file():
            return resolved
    return None


def mount_console(app: FastAPI, static_dir: str | Path) -> None:
    """Register a catch-all that serves the exported console with SPA fallback.

    Must be called AFTER the ``/api`` router so API routes win; this only handles
    paths no API route claimed. Unknown ``/api/*`` paths 404 (never the shell).
    """
    base = Path(static_dir)

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_console(full_path: str, request: Request) -> Response:
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="not found")
        target = resolve_static_file(base, full_path)
        if target is not None:
            return FileResponse(target)
        index = base / "index.html"
        if index.is_file():
            return FileResponse(index)  # SPA shell
        raise HTTPException(status_code=404, detail="not found")
