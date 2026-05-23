# Catch-Up — News Intelligence Agent

A production-grade, **multi-agent global news monitoring & catch-up platform** built on the
Google Agent Development Kit (ADK). It collects news from RSS, web scraping, news APIs, and
Google Search grounding; uses Gemini to categorize, importance-score, summarize (EN/AR), and
extract entities; and delivers structured catch-up digests as **Excel, an HTML dashboard, and
Markdown** through a **Next.js** web console.

Built **free to run locally**, architected to scale to **Google Cloud production** (Cloud Run +
Cloud Scheduler + Vertex AI + Firestore) by configuration — not a rewrite.

## Status

🚧 Early development. Design is approved — see
[`docs/superpowers/specs/2026-05-23-adk-catchup-agent-design.md`](docs/superpowers/specs/2026-05-23-adk-catchup-agent-design.md).

## Architecture (at a glance)

```
Next.js console  ⇄  FastAPI API  ⇄  run_digest()/ADK Runner  ⇄  services  ⇄  Storage

NewsCatchUpPipeline (ADK SequentialAgent)
  Collection (ParallelAgent: RSS · Scrape · API · Search-Grounding)
  → NormalizeDedup → Processing (LLM) → DigestEditor (LLM) → Render (xlsx/HTML/MD)
```

## Tech

ADK · Gemini (AI Studio → Vertex) · FastAPI · SQLite → Firestore · APScheduler → Cloud Scheduler ·
Next.js + shadcn/ui + Tailwind.

## License

Private.
