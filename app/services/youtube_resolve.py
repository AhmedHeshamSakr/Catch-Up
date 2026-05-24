from __future__ import annotations

import re
from collections.abc import Callable

from app.services.net import safe_get

_HEADERS = {"User-Agent": "CatchUp/0.1 (+https://github.com/AhmedHeshamSakr/Catch-Up)"}

# Matches a YouTube channel id: "UC" followed by exactly 22 alphanumeric/dash/underscore chars
_CHANNEL_ID_RE = re.compile(r'"(?:channelId|externalId|browseId)"\s*:\s*"(UC[\w-]{22})"')
_RAW_UC_RE = re.compile(r"UC[\w-]{22}")


def _is_channel_id(value: str) -> bool:
    """Return True if value is already a bare UC… channel id (len == 24)."""
    return bool(_RAW_UC_RE.fullmatch(value))


def _fetch(url: str) -> bytes:
    # SSRF guard — per-hop validation rejects private/loopback/non-http(s) hosts
    resp = safe_get(url, timeout=15.0, headers=_HEADERS)
    resp.raise_for_status()
    return resp.content


def _resolve_url(value: str) -> str:
    """Convert a @handle or URL into the canonical YouTube channel page URL to fetch."""
    if value.startswith("http://") or value.startswith("https://"):
        return value
    # @handle or bare handle
    handle = value.lstrip("@")
    return f"https://www.youtube.com/@{handle}"


def resolve_channel_id(
    value: str,
    *,
    fetch: Callable[[str], bytes] = _fetch,
) -> str | None:
    """Resolve a channel id, @handle, or YouTube URL to a UC… channel id.

    - If ``value`` already looks like a channel id (``UC`` + 22 chars, len 24) it is
      returned immediately without any network call.
    - Otherwise the channel page is fetched and the first ``UC…`` id found in JSON
      keys (``channelId``, ``externalId``, ``browseId``) is returned.
    - Returns ``None`` when no id can be found.
    """
    value = value.strip()

    if _is_channel_id(value):
        return value

    url = _resolve_url(value)
    html = fetch(url)

    if isinstance(html, bytes):
        text = html.decode("utf-8", errors="replace")
    else:
        text = html

    match = _CHANNEL_ID_RE.search(text)
    if match:
        return match.group(1)
    return None
