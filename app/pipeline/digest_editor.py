from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from google.adk.agents import Agent
from google.genai import types

from app.core.config import Settings
from app.core.domain import NewsItem
from app.llm.parse import parse_model_json
from app.llm.runtime import run_agent_text
from app.llm.schema import DigestNarrative

NarrateFn = Callable[[list[NewsItem]], str]

_PROMPT = (Path(__file__).resolve().parents[1] / "prompts" / "digest_editor.md").read_text(
    encoding="utf-8"
)


def write_narrative(items: list[NewsItem], generate: NarrateFn, top_n: int = 12) -> str:
    if not items:
        return ""
    ranked = sorted(items, key=lambda i: i.importance_score or 0.0, reverse=True)[:top_n]
    return generate(ranked)


def build_editor_agent(model: str, temperature: float = 0.0) -> Agent:
    return Agent(
        name="digest_editor",
        model=model,
        instruction=_PROMPT,
        output_schema=DigestNarrative,
        output_key="digest_narrative",
        generate_content_config=types.GenerateContentConfig(temperature=temperature),
    )


def adk_narrate(items: list[NewsItem], settings: Settings) -> str:
    agent = build_editor_agent(settings.llm_model, settings.llm_temperature)
    payload = json.dumps(
        [{"title": i.title, "summary": i.summary_en,
          "category": (i.category.value if i.category else None)} for i in items],
        ensure_ascii=False)
    text = run_agent_text(agent, payload, settings)
    return parse_model_json(text, DigestNarrative).narrative
