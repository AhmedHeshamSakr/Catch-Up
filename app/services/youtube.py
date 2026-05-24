from __future__ import annotations

import calendar
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import feedparser

from app.core.config import Settings, SourceConfig
from app.core.domain import RawItem, SourceType, make_item_id
from app.llm.runtime import run_agent_text
from app.services.net import safe_get

log = logging.getLogger(__name__)

_HEADERS = {"User-Agent": "CatchUp/0.1 (+https://github.com/AhmedHeshamSakr/Catch-Up)"}

_PROMPT = (Path(__file__).resolve().parents[1] / "prompts" / "youtube_summary.md").read_text(
    encoding="utf-8"
)

# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------


@dataclass
class Video:
    video_id: str
    url: str
    title: str
    published_at: datetime | None = None
    description: str = field(default="")


# ---------------------------------------------------------------------------
# Feed utilities
# ---------------------------------------------------------------------------


def channel_feed_url(channel_id: str) -> str:
    return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"


def _default_fetch(channel_id: str, *, resolver=None) -> bytes:
    url = channel_feed_url(channel_id)
    kwargs = {"timeout": 15.0, "headers": _HEADERS}
    if resolver is not None:
        kwargs["resolver"] = resolver
    resp = safe_get(url, **kwargs)
    resp.raise_for_status()
    return resp.content


def fetch_channel_feed(channel_id: str, *, fetch: Callable[[str], bytes] = _default_fetch) -> bytes:
    return fetch(channel_id)


def parse_channel_feed(content: bytes) -> list[Video]:
    """Parse a YouTube Atom/RSS feed into Video objects. Pure; offline-testable."""
    parsed = feedparser.parse(content)
    videos: list[Video] = []
    for entry in parsed.entries:
        link = getattr(entry, "link", None)
        title = getattr(entry, "title", None)
        if not link or not title:
            continue

        # YouTube feeds expose yt:videoId via feedparser as yt_videoid
        video_id = getattr(entry, "yt_videoid", None)
        if not video_id:
            # Fallback: extract from URL ?v=…
            if "v=" in link:
                video_id = link.split("v=")[-1].split("&")[0]
            else:
                video_id = ""

        published_at: datetime | None = None
        if getattr(entry, "published_parsed", None):
            published_at = datetime.fromtimestamp(
                calendar.timegm(entry.published_parsed), tz=UTC
            )

        # Description: feedparser surfaces media:description at the entry level.
        description = (
            getattr(entry, "media_description", "")
            or getattr(entry, "summary", "")
            or ""
        )

        videos.append(Video(
            video_id=video_id,
            url=link,
            title=title.strip(),
            published_at=published_at,
            description=description.strip(),
        ))
    return videos


# ---------------------------------------------------------------------------
# Transcript
# ---------------------------------------------------------------------------


def get_transcript(video_id: str, settings: Settings, *, lang_pref: str | None = None) -> str | None:
    """Fetch transcript for a YouTube video.

    Tries:
    1. youtube-transcript-api (free, no download needed)
    2. Whisper fallback via yt-dlp + faster-whisper (only if settings.youtube_whisper_enabled
       and the whisper extra is installed — lazy import so the default env stays light).

    Returns plain text or None if unavailable.
    """
    # --- Attempt 1: youtube-transcript-api ---
    try:
        from youtube_transcript_api import YouTubeTranscriptApi  # type: ignore[import]
        from youtube_transcript_api._errors import (  # type: ignore[import]
            NoTranscriptFound,
            TranscriptsDisabled,
        )

        langs = []
        if lang_pref:
            langs.append(lang_pref)
        # Always try Arabic + English as fallback priorities
        for lang_code in ("ar", "en", "en-US", "en-GB"):
            if lang_code not in langs:
                langs.append(lang_code)

        api = YouTubeTranscriptApi()
        try:
            transcript_list = api.list(video_id)
            # Try preferred languages first; then fall back to any available
            transcript = None
            for lang_code in langs:
                try:
                    transcript = transcript_list.find_transcript([lang_code])
                    break
                except Exception:
                    continue
            if transcript is None:
                # Accept whatever is available
                transcripts = list(transcript_list)
                if transcripts:
                    transcript = transcripts[0]
            if transcript is not None:
                fetched = transcript.fetch()
                return " ".join(seg.text for seg in fetched).strip() or None
        except (TranscriptsDisabled, NoTranscriptFound):
            pass  # expected — video simply has no transcript
        except Exception as exc:
            # Real problems (IP block, video unavailable, network) — surface to the operator.
            log.warning("youtube-transcript-api error for %s: %s", video_id, exc)
    except ImportError:
        log.debug("youtube-transcript-api not installed")

    # --- Attempt 2: Whisper fallback ---
    if settings.youtube_whisper_enabled:
        try:
            import yt_dlp  # type: ignore[import]
            from faster_whisper import WhisperModel  # type: ignore[import]
        except ImportError:
            log.debug("Whisper extra not installed (yt-dlp / faster-whisper missing); skipping.")
            return None

        try:
            import os
            import tempfile

            with tempfile.TemporaryDirectory() as tmpdir:
                audio_path = os.path.join(tmpdir, f"{video_id}.mp3")
                ydl_opts = {
                    "format": "bestaudio/best",
                    "outtmpl": audio_path,
                    "quiet": True,
                    "no_warnings": True,
                    "postprocessors": [{
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                    }],
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([f"https://www.youtube.com/watch?v={video_id}"])

                model = WhisperModel(settings.whisper_model, device="cpu", compute_type="int8")
                # yt-dlp may append .mp3 to the path
                actual_path = audio_path if os.path.exists(audio_path) else audio_path + ".mp3"
                segments, _ = model.transcribe(actual_path, beam_size=1)
                text = " ".join(seg.text for seg in segments).strip()
                return text or None
        except Exception as exc:
            log.debug("Whisper fallback failed for %s: %s", video_id, exc)
            return None

    return None


# ---------------------------------------------------------------------------
# Summarizer agent
# ---------------------------------------------------------------------------


def build_youtube_summary_agent(model: str):
    """Build a search-free ADK agent that summarizes a transcript."""
    from google.adk.agents import Agent

    from app.llm.schema import DigestNarrative  # reuse {narrative: str} shape

    return Agent(
        name="youtube_summarizer",
        model=model,
        instruction=_PROMPT,
        output_schema=DigestNarrative,
        output_key="youtube_summary",
    )


def adk_summarize(text: str, settings: Settings) -> str:
    """Run the summarizer agent on ``text`` and return a short blurb."""
    from app.llm.schema import DigestNarrative

    agent = build_youtube_summary_agent(settings.llm_model)
    raw = run_agent_text(agent, text, settings)
    return DigestNarrative.model_validate_json(raw).narrative


# ---------------------------------------------------------------------------
# Collector
# ---------------------------------------------------------------------------

# Type aliases for injectable boundaries
ChannelFetchFn = Callable[[str], bytes]
TranscriptFn = Callable[[str], str | None]
SummarizeFn = Callable[[str, Settings], str]


def collect(
    source: SourceConfig,
    settings: Settings,
    *,
    storage=None,
    fetch: ChannelFetchFn = _default_fetch,
    transcript: TranscriptFn | None = None,
    summarize: SummarizeFn = adk_summarize,
) -> list[RawItem]:
    """Collect new YouTube videos from a channel's RSS feed as RawItems.

    Injectable boundaries:
    - ``fetch(channel_id) -> bytes``  — returns raw RSS feed bytes.
    - ``transcript(video_id) -> str | None``  — returns transcript text or None.
    - ``summarize(text, settings) -> str``  — returns a short summary blurb.
    - ``storage``  — any object with ``existing_ids(ids) -> set[str]``; used for dedup.
    """
    from app.services.youtube_resolve import resolve_channel_id

    # Resolve channel id (uses resolve_channel_id's SSRF-guarded default fetch)
    channel_id = source.channel_id
    if not channel_id and source.url:
        channel_id = resolve_channel_id(source.url)
    if not channel_id:
        log.warning("YouTube source %s: no channel_id and could not resolve from url", source.id)
        return []

    content = fetch(channel_id)
    videos = parse_channel_feed(content)

    transcript_fn: TranscriptFn = transcript or (
        lambda vid: get_transcript(vid, settings)
    )

    items: list[RawItem] = []
    for video in videos:
        item_id = make_item_id(video.url)

        # Dedup check — skip costly transcript/summarize for already-seen items
        if storage is not None and item_id in storage.existing_ids([item_id]):
            continue

        t = transcript_fn(video.video_id)
        if t:
            excerpt: str | None = summarize(t, settings)
        else:
            excerpt = video.description or None

        items.append(RawItem(
            source_id=source.id,
            source_type=SourceType.YOUTUBE,
            source_name=source.name,
            url=video.url,
            title=video.title,
            excerpt=excerpt,
            published_at=video.published_at,
            category_hint=source.category_hint,
        ))

    return items
