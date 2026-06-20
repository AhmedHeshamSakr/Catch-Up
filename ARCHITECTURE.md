# Catch-Up — Architecture

A multi-agent news catch-up platform on the **Google Agent Development Kit (ADK)**.
It collects news from many sources, uses **Gemini** to categorize / score / summarize
(EN + AR) and fact-check, then renders catch-up digests — served through a **Next.js**
console and a **FastAPI** backend. Built to run **free locally** and scale to **Google
Cloud** by configuration, not a rewrite.

---

## High-level layers

```mermaid
flowchart TB
    subgraph L1["🖥️  Client"]
        A1["Next.js console — Dashboard · News · Digests · Sources · Watchlist · Settings"]
        A2["Desktop app — Catch-Up.app · PWA · single-port launcher"]
    end
    subgraph L2["⚡  API — FastAPI"]
        B1["Product REST API · /api/*"]
        B2["ADK deploy surface — Agent Engine / Cloud Run"]
    end
    subgraph L3["🧠  Orchestration — Google ADK"]
        C1["ADK Runner + run_digest()"]
        C2["NewsCatchUpPipeline — SequentialAgent"]
        C3["Scheduler — APScheduler → Cloud Scheduler"]
    end
    subgraph L4["🔧  Services & domain"]
        D1["Collectors — RSS · Scrape · GNews · Search · YouTube"]
        D2["Enrichment — Processing · Critic · Judge · DigestEditor"]
        D3["Render — Excel · HTML · Markdown"]
    end
    subgraph L5["☁️  Models & storage"]
        E1["Gemini — AI Studio → Vertex AI"]
        E2["Storage port — SQLite → Firestore"]
        E3["ADK sessions — DatabaseSessionService"]
    end

    A2 --> A1
    A1 --> B1
    B1 --> C1
    B2 --> C1
    C3 --> C1
    C1 --> C2
    C2 --> D1
    C2 --> D2
    C2 --> D3
    D2 --> E1
    D1 --> E2
    D3 --> E2
    C1 --> E3

    classDef llm fill:#d1fae5,stroke:#059669,color:#064e3b;
    classDef store fill:#e0e7ff,stroke:#4f46e5,color:#312e81;
    class D2,E1 llm;
    class E2,E3 store;
```

Each layer talks to the next through a narrow interface, so any one can change
without breaking the others: swap **SQLite → Firestore**, **AI Studio → Vertex AI**,
or **APScheduler → Cloud Scheduler** by config alone.

---

## The agent pipeline

A run is triggered by the **console** (`POST /api/runs`), the **scheduler**, or the
**CLI**. `run_digest()` builds the agent tree and executes it on an **ADK Runner**;
every stage reads and writes shared run state via `EventActions.state_delta`.

```mermaid
flowchart LR
    S["run_digest()<br/>ADK Runner"] --> P1["1 · PipelineInit<br/>create DigestRun"]
    P1 --> CS
    subgraph CS["2 · CollectSources — ParallelAgent (concurrent)"]
        direction TB
        R["CollectRss"]
        SC["CollectScrape"]
        AP["CollectApi · GNews"]
        SE["CollectSearch · Google grounding"]
        YT["CollectYoutube"]
    end
    CS --> P3["3 · NormalizeDedup<br/>merge · normalize · dedup"]
    P3 --> P4["4 · Processing 🤖<br/>category · importance · EN/AR summary · entities"]
    P4 --> P5["5 · GuardrailCritic 🤖<br/>faithfulness check · flag/redact · reflection"]
    P5 --> P6["6 · DigestEditor 🤖<br/>narrative — what matters most"]
    P6 --> P7["7 · Render<br/>xlsx · HTML · Markdown · finalize"]

    classDef llm fill:#d1fae5,stroke:#059669,color:#064e3b;
    class P4,P5,P6 llm;
```

> **At a glance:** one root `SequentialAgent` runs **7 stages** in order. Stage 2 is a
> `ParallelAgent` that fans out to **up to 5 source collectors** concurrently. **3 stages
> are LLM-backed** (Gemini) — marked 🤖.

---

## Agents at a glance

| # | Agent | ADK type | What it does |
|---|-------|----------|--------------|
| 1 | **PipelineInit** | `BaseAgent` | Creates the `DigestRun` and seeds run state (`run_id`). |
| 2 | **CollectSources** | `ParallelAgent` | Fans out one collector per enabled source type, run concurrently. |
| ↳ | **SourceCollector ×N** | `BaseAgent` | Collects raw items from **one** source type (RSS · Scrape · GNews · Search · YouTube) into its own state key. |
| 3 | **NormalizeDedup** | `BaseAgent` | Merges all collected items, normalizes them, removes duplicates. |
| 4 | **Processing** 🤖 | `BaseAgent` (LLM) | Gemini enrichment: category, importance score, EN + AR summaries, entities, watchlist boosts. |
| 5 | **GuardrailCritic** 🤖 | `BaseAgent` (LLM) | Faithfulness fact-check of high-importance / watchlisted items; flags + redacts unfaithful summaries; bounded re-summarize (reflection). |
| 6 | **DigestEditor** 🤖 | `BaseAgent` (LLM) | Generates the narrative "what matters most" digest summary. |
| 7 | **Render** | `BaseAgent` | Writes Excel / HTML / Markdown outputs and finalizes the run. |

---

## Components by layer

| Layer | Key components |
|-------|----------------|
| **Client** | Next.js 16 console (React 19, Tailwind v4, shadcn/base-ui, SWR), PWA, `Catch-Up.app` single-port desktop launcher. |
| **API** | FastAPI product API `/api/*` (runs, news, sources, watchlist, settings, health, resolve) + the ADK deploy surface. |
| **Orchestration** | ADK `Runner` + `run_digest()` → `NewsCatchUpPipeline`; single-flight run trigger; APScheduler. |
| **Services & domain** | Collectors (`rss`, `scrape`, `newsapi`, `youtube`, `search`, `feed_discovery`), LLM runtime (`app/llm`), enrichment (`processing`, `critic`, `judge`, `digest_editor`), render (Excel/HTML/Markdown), SSRF-guarded `net`, rate limiter, config store. |
| **Models** | Gemini via `google-genai` (AI Studio → Vertex AI). |
| **Storage** | `StorageBackend` port → SQLite (default) / Firestore adapter; ADK sessions via `DatabaseSessionService` (SQLite). |
| **Cross-cutting** | Settings/config, telemetry/observability, security (API key, localhost write-guard, SSRF guard, rate limit), eval + runtime faithfulness guardrail. |

---

## Quality guardrails

Two LLM-as-judge safeguards protect summary quality, sharing one rubric
(`app/prompts/faithfulness_rubric.md`):

- **Offline eval loop** — scores enrichment against a reference dataset on faithfulness,
  category accuracy, importance calibration, and Arabic translation quality.
- **Runtime critic** (stage 5) — fact-checks high-importance / watchlisted items at digest
  time; unfaithful summaries are **never shown** (flagged + redacted), with bounded
  self-correction.

See **[docs/ADK-GUIDE.md](docs/ADK-GUIDE.md)** for the full ADK architecture & integration guide.
