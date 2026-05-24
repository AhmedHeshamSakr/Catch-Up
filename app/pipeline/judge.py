from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from google.adk.agents import Agent

from app.core.config import Settings
from app.core.domain import NewsItem
from app.llm.runtime import run_agent_text
from app.llm.schema import ItemEnrichment
from app.pipeline.eval_schema import EnrichmentVerdict, EnrichmentVerdicts

_PROMPTS = Path(__file__).resolve().parents[1] / "prompts"
# faithfulness_rubric.md is the single source of the rubric, shared with the runtime
# critic (Phase B). Compose it into the judge frame so the two never diverge.
_RUBRIC = (_PROMPTS / "faithfulness_rubric.md").read_text(encoding="utf-8")
_JUDGE_PROMPT = (
    (_PROMPTS / "judge.md").read_text(encoding="utf-8").replace("{{RUBRIC}}", _RUBRIC)
)

JudgeFn = Callable[[list[tuple[NewsItem, ItemEnrichment]]], list[EnrichmentVerdict]]


def build_judge_agent(model: str) -> Agent:
    return Agent(
        name="enrichment_judge",
        model=model,
        instruction=_JUDGE_PROMPT,
        output_schema=EnrichmentVerdicts,
        output_key="verdicts",
    )


def _judge_payload(pairs: list[tuple[NewsItem, ItemEnrichment]]) -> str:
    """Serialize pairs into JSON for the judge agent."""
    records = [
        {
            "id": item.id,
            "title": item.title,
            "excerpt": (item.excerpt or ""),
            "enrichment": {
                "category": enrichment.category,
                "importance_score": enrichment.importance_score,
                "summary_en": enrichment.summary_en,
                "summary_ar": enrichment.summary_ar,
            },
        }
        for item, enrichment in pairs
    ]
    return json.dumps(records, ensure_ascii=False)


def adk_judge(pairs: list[tuple[NewsItem, ItemEnrichment]], settings: Settings) -> list[EnrichmentVerdict]:
    """Real LLM call. Requires GOOGLE_API_KEY."""
    agent = build_judge_agent(settings.llm_model)
    text = run_agent_text(agent, _judge_payload(pairs), settings)
    return EnrichmentVerdicts.model_validate_json(text).verdicts
