from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import Settings, SourceConfig
from app.core.domain import Category, SourceType
from app.services import youtube as yt

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_FIXTURE_XML = (
    Path(__file__).parent / "fixtures" / "youtube_channel.xml"
).read_bytes()

_CHANNEL_ID = "UCBJycsmduvYEL83R_U4JriQ"

_SETTINGS = Settings()


def _source(**kwargs) -> SourceConfig:
    defaults: dict = {
        "id": "youtube-mkbhd",
        "type": SourceType.YOUTUBE,
        "name": "MKBHD (YouTube)",
        "channel_id": _CHANNEL_ID,
        "category_hint": Category.AI_TECH,
        "enabled": True,
    }
    defaults.update(kwargs)
    return SourceConfig(**defaults)


# ---------------------------------------------------------------------------
# channel_feed_url
# ---------------------------------------------------------------------------

def test_channel_feed_url():
    url = yt.channel_feed_url(_CHANNEL_ID)
    assert "youtube.com/feeds/videos.xml" in url
    assert _CHANNEL_ID in url


# ---------------------------------------------------------------------------
# parse_channel_feed
# ---------------------------------------------------------------------------

def test_parse_channel_feed_returns_two_videos():
    videos = yt.parse_channel_feed(_FIXTURE_XML)
    assert len(videos) == 2


def test_parse_channel_feed_first_video_fields():
    videos = yt.parse_channel_feed(_FIXTURE_XML)
    v = videos[0]
    assert v.video_id == "dQw4w9WgXcQ"
    assert v.url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert v.title == "The Best Smartphone of 2026!"
    assert v.published_at is not None
    assert v.published_at.year == 2026
    assert v.published_at.month == 5
    assert v.published_at.day == 20


def test_parse_channel_feed_second_video_fields():
    videos = yt.parse_channel_feed(_FIXTURE_XML)
    v = videos[1]
    assert v.video_id == "abc123XYZ99"
    assert "abc123XYZ99" in v.url
    assert v.title == "Why AI Will Change Everything"
    assert v.published_at is not None


def test_parse_channel_feed_description_populated():
    videos = yt.parse_channel_feed(_FIXTURE_XML)
    assert videos[0].description  # media:description present
    assert "smartphone" in videos[0].description.lower()


def test_parse_channel_feed_extracts_thumbnail_image_url():
    videos = yt.parse_channel_feed(_FIXTURE_XML)
    assert videos[0].image_url == "https://i2.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg"
    assert videos[1].image_url == "https://i2.ytimg.com/vi/abc123XYZ99/hqdefault.jpg"


def test_collect_propagates_image_url():
    items = yt.collect(
        _source(),
        _SETTINGS,
        fetch=_fake_fetch,
        transcript=_fake_transcript,
        summarize=_fake_summarize,
    )
    assert all(i.image_url for i in items)
    assert items[0].image_url == "https://i2.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg"


# ---------------------------------------------------------------------------
# collect — happy path (injected fetch + transcript + summarize)
# ---------------------------------------------------------------------------

def _fake_fetch(channel_id: str) -> bytes:
    return _FIXTURE_XML


def _fake_transcript(video_id: str) -> str | None:
    return "fake transcript text"


def _fake_summarize(text: str, settings: Settings) -> str:
    return "BLURB"


def test_collect_returns_two_raw_items():
    items = yt.collect(
        _source(),
        _SETTINGS,
        fetch=_fake_fetch,
        transcript=_fake_transcript,
        summarize=_fake_summarize,
    )
    assert len(items) == 2


def test_collect_source_type_is_youtube():
    items = yt.collect(
        _source(),
        _SETTINGS,
        fetch=_fake_fetch,
        transcript=_fake_transcript,
        summarize=_fake_summarize,
    )
    assert all(i.source_type == SourceType.YOUTUBE for i in items)


def test_collect_excerpt_is_summary_blurb():
    items = yt.collect(
        _source(),
        _SETTINGS,
        fetch=_fake_fetch,
        transcript=_fake_transcript,
        summarize=_fake_summarize,
    )
    assert all(i.excerpt == "BLURB" for i in items)


def test_collect_category_hint_propagated():
    items = yt.collect(
        _source(),
        _SETTINGS,
        fetch=_fake_fetch,
        transcript=_fake_transcript,
        summarize=_fake_summarize,
    )
    assert all(i.category_hint == Category.AI_TECH for i in items)


def test_collect_source_name_propagated():
    items = yt.collect(
        _source(),
        _SETTINGS,
        fetch=_fake_fetch,
        transcript=_fake_transcript,
        summarize=_fake_summarize,
    )
    assert all(i.source_name == "MKBHD (YouTube)" for i in items)


# ---------------------------------------------------------------------------
# collect — no-transcript path (excerpt falls back to description)
# ---------------------------------------------------------------------------

def _null_transcript(video_id: str) -> str | None:
    return None


def test_collect_no_transcript_uses_description():
    items = yt.collect(
        _source(),
        _SETTINGS,
        fetch=_fake_fetch,
        transcript=_null_transcript,
        summarize=_fake_summarize,
    )
    # Both entries have media:description in the fixture
    for item in items:
        assert item.excerpt is not None
        assert item.excerpt  # non-empty


def test_collect_no_transcript_does_not_call_summarize():
    summarize_calls = []

    def counting_summarize(text: str, settings: Settings) -> str:
        summarize_calls.append(text)
        return "SUMMARY"

    yt.collect(
        _source(),
        _SETTINGS,
        fetch=_fake_fetch,
        transcript=_null_transcript,
        summarize=counting_summarize,
    )
    assert summarize_calls == [], "summarize must NOT be called when there is no transcript"


# ---------------------------------------------------------------------------
# collect — dedup via storage
# ---------------------------------------------------------------------------

class _FakeStorage:
    """Fake StorageBackend that reports one id as already seen."""

    def __init__(self, seen_ids: set[str]):
        self._seen = seen_ids

    def existing_ids(self, ids: list[str]) -> set[str]:
        return self._seen & set(ids)


def test_collect_skips_seen_video():
    from app.core.domain import make_item_id
    videos = yt.parse_channel_feed(_FIXTURE_XML)
    seen_url = videos[0].url
    seen_id = make_item_id(seen_url)

    storage = _FakeStorage({seen_id})

    transcript_calls: list[str] = []
    summarize_calls: list[str] = []

    def counting_transcript(video_id: str) -> str | None:
        transcript_calls.append(video_id)
        return "transcript"

    def counting_summarize(text: str, settings: Settings) -> str:
        summarize_calls.append(text)
        return "BLURB"

    items = yt.collect(
        _source(),
        _SETTINGS,
        storage=storage,
        fetch=_fake_fetch,
        transcript=counting_transcript,
        summarize=counting_summarize,
    )

    # Only 1 item returned (the unseen one)
    assert len(items) == 1
    # transcript/summarize not called for the seen video
    assert videos[0].video_id not in transcript_calls
    assert len(summarize_calls) == 1  # only the remaining video


# ---------------------------------------------------------------------------
# collect — no channel_id and no url → returns empty list
# ---------------------------------------------------------------------------

def test_collect_returns_empty_when_no_channel():
    source = _source(channel_id=None, url=None)
    items = yt.collect(source, _SETTINGS, fetch=_fake_fetch, transcript=_fake_transcript, summarize=_fake_summarize)
    assert items == []


# ---------------------------------------------------------------------------
# SSRF guard — default channel feed fetch
# ---------------------------------------------------------------------------

def test_default_fetch_rejects_private_address():
    """The DEFAULT channel-feed fetch must reject a host resolving to a private IP.

    Injects a resolver that maps any host to a link-local metadata IP so no real
    DNS/network call happens — the SSRF guard must raise before the HTTP request.
    """
    from app.services.net import UnsafeURLError

    with pytest.raises(UnsafeURLError):
        yt._default_fetch(_CHANNEL_ID, resolver=lambda host: ["169.254.169.254"])


# ---------------------------------------------------------------------------
# get_transcript — language fallback
# ---------------------------------------------------------------------------

class _Seg:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeTranscript:
    def __init__(self, lang: str) -> None:
        self.language_code = lang

    def fetch(self):
        return [_Seg("bonjour le monde")]


class _FakeTranscriptList:
    def __init__(self, transcripts):
        self._t = transcripts

    def find_transcript(self, langs):
        raise Exception("no transcript for those languages")  # force the fallback

    def __iter__(self):
        return iter(self._t)


class _FakeApi:
    def list(self, video_id):
        return _FakeTranscriptList([_FakeTranscript("fr")])


def test_get_transcript_warns_when_falling_back_to_unpreferred_language(monkeypatch, caplog):
    import logging

    import youtube_transcript_api

    monkeypatch.setattr(youtube_transcript_api, "YouTubeTranscriptApi", _FakeApi)
    with caplog.at_level(logging.WARNING, logger="app.services.youtube"):
        text = yt.get_transcript("vidFR", _SETTINGS)  # no preferred lang available
    assert text == "bonjour le monde"  # still returns the fallback transcript
    assert any(
        "preferred-language" in r.message.lower() or "transcript instead" in r.message.lower()
        for r in caplog.records
    ), "expected a wrong-language warning"
