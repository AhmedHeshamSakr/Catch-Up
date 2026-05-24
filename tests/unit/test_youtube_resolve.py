from __future__ import annotations

from app.services.youtube_resolve import resolve_channel_id

# A realistic channel id fixture
_CHANNEL_ID = "UCBJycsmduvYEL83R_U4JriQ"  # MKBHD

# Minimal HTML that a YouTube channel page might return — includes channelId
_HANDLE_HTML = b"""
<!DOCTYPE html>
<html>
<head><title>MKBHD</title></head>
<body>
<script>var data = {"channelId":"UCBJycsmduvYEL83R_U4JriQ","title":"MKBHD"};</script>
</body>
</html>
"""

# HTML with externalId pattern instead
_EXTERNAL_ID_HTML = b"""
<html><head></head><body>
<script>{"externalId":"UCBJycsmduvYEL83R_U4JriQ"}</script>
</body></html>
"""

# HTML with no channel id at all
_NO_ID_HTML = b"""<html><body><p>Nothing here</p></body></html>"""


def _fake_fetch(response: bytes):
    """Return a fetch function that always returns the given bytes."""
    def _fetch(url: str) -> bytes:
        return response
    return _fetch


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_channel_id_passthrough():
    """A value that already IS a UC… id (len 24, starts with UC) is returned as-is."""
    result = resolve_channel_id(_CHANNEL_ID)
    assert result == _CHANNEL_ID


def test_channel_id_passthrough_no_network():
    """Passthrough must NOT call fetch at all."""
    calls = []

    def spy_fetch(url: str) -> bytes:
        calls.append(url)
        return b""

    resolve_channel_id(_CHANNEL_ID, fetch=spy_fetch)
    assert calls == [], "fetch should not be called for a raw channel id"


def test_handle_resolves_from_channelId_in_html():
    """@handle → fetch channel page → parse channelId JSON key."""
    result = resolve_channel_id("@mkbhd", fetch=_fake_fetch(_HANDLE_HTML))
    assert result == _CHANNEL_ID


def test_url_resolves_from_channelId_in_html():
    """Full YouTube URL → fetch page → parse channelId."""
    result = resolve_channel_id(
        "https://www.youtube.com/@mkbhd",
        fetch=_fake_fetch(_HANDLE_HTML),
    )
    assert result == _CHANNEL_ID


def test_resolves_from_externalId_pattern():
    """Falls back to externalId if channelId key is absent."""
    result = resolve_channel_id("@mkbhd", fetch=_fake_fetch(_EXTERNAL_ID_HTML))
    assert result == _CHANNEL_ID


def test_no_match_returns_none():
    """HTML with no UC… id → None."""
    result = resolve_channel_id("@unknown", fetch=_fake_fetch(_NO_ID_HTML))
    assert result is None


def test_handle_fetch_url_uses_youtube_domain():
    """When given a @handle, the fetched URL should be youtube.com/<handle>."""
    fetched = []

    def spy_fetch(url: str) -> bytes:
        fetched.append(url)
        return _HANDLE_HTML

    resolve_channel_id("@mkbhd", fetch=spy_fetch)
    assert fetched, "fetch should be called"
    assert "youtube.com" in fetched[0]
    assert "mkbhd" in fetched[0]
