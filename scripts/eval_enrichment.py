"""eval_enrichment.py — offline enrichment eval harness.

Usage (offline, no API key):
    uv run python scripts/eval_enrichment.py

Usage (live, needs GOOGLE_API_KEY):
    uv run python scripts/eval_enrichment.py --live

The offline mode does nothing useful on its own (enrich/judge must be injected).
Use the --live flag to run with real ADK agents; report is written to output/eval/report.json.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.core.domain import Category, NewsItem, Sentiment, SourceType
from app.pipeline.eval_schema import EnrichmentVerdict
from app.pipeline.eval_score import EvalReport, aggregate
from app.pipeline.judge import JudgeFn
from app.pipeline.processing import EnrichFn
from app.pipeline.schema import ItemEnrichment, ProcessingResult

_REFERENCE_PATH = Path(__file__).resolve().parents[1] / "tests" / "eval" / "fixtures" / "enrichment_reference.json"


def load_reference(path: str | Path = _REFERENCE_PATH) -> list[dict]:
    """Load the enrichment reference fixture from disk."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _build_news_item(item_dict: dict) -> NewsItem:
    """Construct a minimal NewsItem from a fixture item dict."""
    return NewsItem(
        id=item_dict["id"],
        source_id="eval",
        source_type=SourceType.RSS,
        source_name="eval",
        url=f"https://eval.local/{item_dict['id']}",
        title=item_dict["title"],
        excerpt=item_dict.get("excerpt"),
    )


def _build_item_enrichment(gold_dict: dict) -> ItemEnrichment:
    """Construct an ItemEnrichment from a fixture gold dict."""
    return ItemEnrichment(
        id=gold_dict["id"],
        category=Category(gold_dict["category"]),
        importance_score=gold_dict["importance_score"],
        summary_en=gold_dict["summary_en"],
        summary_ar=gold_dict["summary_ar"],
        entities=gold_dict.get("entities", []),
        sentiment=Sentiment(gold_dict["sentiment"]),
    )


def run_eval(
    *,
    enrich: EnrichFn,
    judge: JudgeFn,
    reference: list[dict],
) -> EvalReport:
    """Run the full eval loop and return an EvalReport.

    Args:
        enrich: callable matching EnrichFn — takes list[NewsItem], returns ProcessingResult.
        judge:  callable matching JudgeFn — takes list[tuple[NewsItem, ItemEnrichment]], returns list[EnrichmentVerdict].
        reference: list of dicts loaded from enrichment_reference.json.
    """
    # Build NewsItem list and id→gold map
    news_items: list[NewsItem] = [_build_news_item(case["item"]) for case in reference]
    gold_by_id: dict[str, ItemEnrichment] = {
        case["gold"]["id"]: _build_item_enrichment(case["gold"]) for case in reference
    }

    # Enrich all items in one batch (eval uses gold or fake enrich)
    processing_result: ProcessingResult = enrich(news_items)
    enrichment_by_id: dict[str, ItemEnrichment] = {e.id: e for e in processing_result.items}

    # Pair each NewsItem with its enrichment result (fall back to gold if missing)
    pairs: list[tuple[NewsItem, ItemEnrichment]] = []
    for item in news_items:
        enrichment = enrichment_by_id.get(item.id) or gold_by_id.get(item.id)
        if enrichment is not None:
            pairs.append((item, enrichment))

    # Judge all pairs
    verdicts: list[EnrichmentVerdict] = judge(pairs)

    return aggregate(verdicts)


def _main() -> None:
    parser = argparse.ArgumentParser(description="Enrichment quality eval harness")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run with real ADK agents (requires GOOGLE_API_KEY). Writes output/eval/report.json.",
    )
    parser.add_argument(
        "--reference",
        default=str(_REFERENCE_PATH),
        help="Path to enrichment_reference.json fixture.",
    )
    args = parser.parse_args()

    if not args.live:
        print("Offline mode: no live model calls. Use --live to run against the real enrichment pipeline.")
        print(f"Reference fixture: {args.reference}")
        return

    # Live mode — import real implementations
    import os

    from app.core.config import Settings
    from app.pipeline.judge import adk_judge
    from app.pipeline.processing import adk_enrich

    settings = Settings()
    if not settings.google_api_key and not os.environ.get("GOOGLE_API_KEY"):
        raise SystemExit("ERROR: GOOGLE_API_KEY is required for --live mode.")
    reference = load_reference(args.reference)

    def enrich_fn(items):
        return adk_enrich(items, settings)

    def judge_fn(pairs):
        return adk_judge(pairs, settings)

    report = run_eval(enrich=enrich_fn, judge=judge_fn, reference=reference)

    out_dir = Path("output") / "eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "report.json"
    out_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    print(f"Eval report written to {out_path}")
    print(f"Overall passed: {report.passed}")
    print(f"n={report.n}, failures={report.failures}")
    for dim, score in report.dimension_mean_score.items():
        print(f"  {dim}: mean_score={score:.3f}  pass_rate={report.dimension_pass_rate[dim]:.3f}")


if __name__ == "__main__":
    _main()
