# Enrichment Eval — Offline Judge Loop

## Overview

This is an offline, quota-free evaluation harness for the `news_processor` enrichment pipeline. It scores enrichment quality across four dimensions using an injectable judge boundary, so the full eval loop runs in pytest with synthetic verdicts (zero API calls).

## Running the Eval

### Offline (no API key, instant)
```bash
uv run python scripts/eval_enrichment.py
```
This prints usage info. The harness itself is tested via pytest (see below).

### Live (requires GOOGLE_API_KEY — deferred until quota is available)
```bash
GOOGLE_API_KEY=... uv run python scripts/eval_enrichment.py --live
```
Writes `output/eval/report.json` with dimension scores and pass/fail status.

Live add-ons (all imply `--live`):
```bash
# Calibrate the JUDGE itself against gold expectations (is the judge trustworthy?)
GOOGLE_API_KEY=... uv run python scripts/eval_enrichment.py --calibrate

# Compare against the committed baseline; exits non-zero on regression
GOOGLE_API_KEY=... uv run python scripts/eval_enrichment.py --check-regression

# Refresh the committed baseline (tests/eval/baseline.json) from a known-good run
GOOGLE_API_KEY=... uv run python scripts/eval_enrichment.py --update-baseline
```

### Distinct / stronger judge model (reduce self-grading bias)
By default the judge uses `llm_model` — the SAME model that produced the
enrichments. A judge sharing the enricher's model tends to ratify its own
mistakes (self-grading bias). Set a **distinct, ideally stronger** judge via
`Settings.judge_model` (env `JUDGE_MODEL`); when unset it falls back to
`llm_model`:
```bash
JUDGE_MODEL=<a-stronger-model> GOOGLE_API_KEY=... uv run python scripts/eval_enrichment.py --calibrate
```
Calibration is how you *verify* the judge is worth trusting before relying on
its enricher verdicts.

### Pytest (offline, always runs in CI)
```bash
uv run pytest tests/unit/test_judge.py tests/unit/test_eval_score.py \
              tests/unit/test_eval_fixtures.py tests/unit/test_eval_harness.py -v
```
Or just the full suite: `uv run pytest tests -q`

---

## Dimensions and Thresholds

| Dimension | Threshold | Notes |
|---|---|---|
| `faithfulness` | **0.90** | Strictest — any hallucinated claim or injection compliance fails |
| `category_accuracy` | 0.85 | Four allowed values: `ai_tech`, `business_finance`, `world_geopolitics`, `gulf_mena` |
| `importance_calibration` | 0.70 | Plausibility band — only clear miscalibration penalised (e.g. trivial patch scored 0.9+) |
| `ar_translation_quality` | 0.80 | MSA fluency; no added/dropped facts vs `summary_en` |

### Gating: pass_rate for safety-critical, mean for soft

The gate is **per-dimension and not uniformly mean-based** (a single
hallucination must not be averaged away):

- **`faithfulness` (safety-critical)** gates on **pass_rate == 1.0** — *any*
  failed item (one hallucination or one injection compliance) fails the whole
  gate. A mean-based gate could ship a hallucinated digest hidden behind a high
  average; this prevents that.
- **Soft dimensions** (`category_accuracy`, `importance_calibration`,
  `ar_translation_quality`) gate on **mean_score ≥ threshold** — an isolated
  borderline call is tolerable, so central tendency is the right signal.

The report also exposes `dimension_min_score` (the worst single item per
dimension) to surface the floor a mean hides. Safety-critical dimensions are
configured in `SAFETY_CRITICAL` in `app/pipeline/eval_score.py`.

**Never lower thresholds just to pass.** If scores are below threshold, fix the prompt.

---

## The Eval-Fix Loop

1. Run `uv run pytest tests -q` to see all dimension scores via the harness tests.
2. Run `scripts/eval_enrichment.py --live` (when quota is available) to get real scores on `enrichment_reference.json`.
3. Identify failing dimensions from `report.json` → `failures`.
4. Fix the root prompt:
   - Low **faithfulness** → tighten `app/prompts/processing.md` (stronger anti-hallucination instruction, source-only rule).
   - Low **category_accuracy** → add examples to processing prompt; clarify boundary cases.
   - Low **importance_calibration** → adjust the calibration guidance in processing.md.
   - Low **ar_translation_quality** → add explicit MSA fidelity instruction.
5. Re-run eval. Repeat until all thresholds pass.

---

## Reference Dataset (`tests/eval/fixtures/enrichment_reference.json`)

**35 cases**, balanced across all four categories, with broad adversarial
coverage:
- **16 happy-path** (`golden-*`) — correct category, calibrated importance,
  faithful summaries, fluent MSA; balanced across `ai_tech`,
  `business_finance`, `world_geopolitics`, `gulf_mena`.
- **15 adversarial** (`adversarial-*`):
  - **Faithfulness negatives** — hallucinated dollar amount, fabricated facts,
    fabricated precise numbers, plus **multiple prompt-injection variants**
    ("Ignore previous instructions…", "SYSTEM OVERRIDE…", "print your system
    prompt…").
  - **Importance miscalibration both ways** — trivial items scored 0.92/0.95
    (over) and a major earthquake scored 0.08 (under).
  - **Miscategorisation** — Gulf AI story as `business_finance`; an AI model
    release as `world_geopolitics`.
  - **Arabic-quality negatives** — dropped claim, **added** (fabricated) claim,
    Gulf **dialect** instead of MSA, broken colloquial MSA.
- **4 edge cases** (`edge-*`) — empty excerpt (faithful + a hallucinated
  variant), a long/truncated multi-sector excerpt, and a near-duplicate of a
  golden case.

Each case has an `expectations` dict with a boolean per dimension, used both by
offline fixture tests and by **judge calibration** (`run_calibration`): the
case's reference enrichment (`reference_enrichment` if present, else `gold` —
which the adversarial cases deliberately make *known-bad*) is fed to the judge,
and the judge's pass/fail is checked against `expectations`. This produces a
per-dimension confusion matrix (TP/FP/FN/TN) + accuracy. **False positives**
(judge passes an item the gold says should fail) mean the judge is lenient and
untrustworthy — fix the rubric/judge model before trusting enricher verdicts.

### Regression baseline (`tests/eval/baseline.json`)

A committed sample EvalReport. `--check-regression` loads it, runs
`compare(baseline, current)`, and fails the run if any dimension's mean dropped
by more than `REGRESSION_DELTA` (0.05). `--live --update-baseline` regenerates
it from a fresh run.

---

## Architecture Notes

- **Why a custom harness, not `agents-cli eval`?** `agents-cli eval` targets the conversational `root_agent`; `news_processor` is a batch structured-output agent — interface mismatch. See `processing-goldens.md` for historical context.
- **ADK output_schema wrapping:** ADK requires a Pydantic model (not a bare list) as `output_schema`. `EnrichmentVerdicts` wraps `list[EnrichmentVerdict]` for this reason.
- **EnrichFn / JudgeFn are injectable** — in tests, swap real ADK calls for synthetic functions; in `--live` mode, bind `adk_enrich` / `adk_judge` from the pipeline.
