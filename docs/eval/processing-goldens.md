# Processing — Golden Seed (manual accuracy spot-checks)

A small set of representative headlines with the **expected category** and a rough **importance band**,
for eyeballing the processing agent's output during development. This is a lightweight stand-in until
the formal `agents-cli eval` loop is wired in (planned once the conversational root agent exists — see
the roadmap in the design spec). Run `uv run python -m app.cli run` with a `GOOGLE_API_KEY` set and
compare the enriched items against the bands below.

| # | Headline (example) | Expected category | Importance band |
|---|---|---|---|
| 1 | "OpenAI releases GPT-class model with on-prem enterprise tier" | `ai_tech` | high (0.7–1.0) |
| 2 | "Qatar Investment Authority anchors $2B regional AI infrastructure fund" | `gulf_mena` | high (0.7–1.0) |
| 3 | "US Federal Reserve holds interest rates steady" | `business_finance` | medium–high (0.5–0.8) |
| 4 | "Minor point-release patches a typo in a docs site" | `ai_tech` | low (0.0–0.2) |
| 5 | "UN Security Council convenes emergency session on regional conflict" | `world_geopolitics` | high (0.7–1.0) |

**What to check:**
- Category assignment matches the expected column.
- `importance_score` lands in the expected band (watchlist entities like *OpenAI*, *Qatar Investment
  Authority* should push items toward the top via the +0.25 boost).
- `summary_en` is a faithful 1–2 sentence summary; `summary_ar` is a correct MSA rendering.
- `entities` capture the obvious named orgs/people/places; `sentiment` is reasonable.

> Note: outputs are non-deterministic. Treat this as a calibration aid, not a pass/fail gate.
