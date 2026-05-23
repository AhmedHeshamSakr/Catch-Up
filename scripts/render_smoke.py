"""render_smoke.py — produce sample md/xlsx/html outputs without any API key.

Usage:
    uv run python scripts/render_smoke.py

Writes three files to output/ and prints their paths.
"""
from __future__ import annotations

from app.core.domain import (
    Category,
    DigestRun,
    Entity,
    Importance,
    NewsItem,
    RawItem,
    Sentiment,
    SourceType,
)
from app.services.render import excel, markdown
from app.services.render import html as html_render

OUTPUT_DIR = "output"


def _item(
    title: str,
    cat: Category,
    source: str,
    url: str,
    summary_en: str,
    summary_ar: str,
    importance: Importance,
    entities: list[Entity],
    sentiment: Sentiment,
) -> NewsItem:
    raw = RawItem(
        source_id=source.lower().replace(" ", "_"),
        source_type=SourceType.RSS,
        source_name=source,
        url=url,
        title=title,
        category_hint=cat,
    )
    item = NewsItem.from_raw(raw, run_id="smoke01")
    item.category = cat
    item.summary_en = summary_en
    item.summary_ar = summary_ar
    item.importance = importance
    item.entities = entities
    item.sentiment = sentiment
    item.status = "processed"
    return item


def build_sample_items() -> list[NewsItem]:
    return [
        _item(
            title="OpenAI releases GPT-5 with multimodal reasoning",
            cat=Category.AI_TECH,
            source="TechCrunch",
            url="https://techcrunch.com/2026/05/23/openai-gpt5",
            summary_en="OpenAI has launched GPT-5, featuring improved multimodal reasoning "
                       "and a 2M-token context window, available via API immediately.",
            summary_ar="أطلقت OpenAI نموذج GPT-5 بقدرات استدلال متعددة الوسائط ونافذة سياق 2M رمز.",
            importance=Importance.HIGH,
            entities=[Entity(name="OpenAI", type="org"), Entity(name="GPT-5", type="product")],
            sentiment=Sentiment.POSITIVE,
        ),
        _item(
            title="Google Cloud expands Vertex AI to three new regions",
            cat=Category.AI_TECH,
            source="Google Blog",
            url="https://cloud.google.com/blog/vertex-ai-expansion-2026",
            summary_en="Vertex AI is now available in Doha, Lagos, and Jakarta, reducing "
                       "latency for enterprise customers across the Gulf, Africa, and Southeast Asia.",
            summary_ar="توسّع Vertex AI إلى الدوحة ولاغوس وجاكرتا لخدمة عملاء المؤسسات في المنطقة.",
            importance=Importance.MEDIUM,
            entities=[Entity(name="Google Cloud", type="org"), Entity(name="Vertex AI", type="product")],
            sentiment=Sentiment.POSITIVE,
        ),
        _item(
            title="Saudi Arabia's PIF acquires 5% stake in Nvidia",
            cat=Category.GULF_MENA,
            source="Reuters",
            url="https://reuters.com/markets/pif-nvidia-2026-05-23",
            summary_en="The Public Investment Fund of Saudi Arabia has acquired a 5 percent stake "
                       "in Nvidia worth approximately $18 billion, marking its largest tech bet.",
            summary_ar="اقتنى صندوق الاستثمارات العامة السعودي حصة 5% في Nvidia بقيمة 18 مليار دولار.",
            importance=Importance.HIGH,
            entities=[Entity(name="PIF", type="org"), Entity(name="Nvidia", type="org")],
            sentiment=Sentiment.POSITIVE,
        ),
        _item(
            title="Global inflation eases to 2.1% as central banks hold rates",
            cat=Category.BUSINESS_FINANCE,
            source="Financial Times",
            url="https://ft.com/content/global-inflation-2026-05",
            summary_en="IMF data shows global inflation fell to 2.1% in April 2026, as G7 central "
                       "banks held rates steady amid cautious optimism about a soft landing.",
            summary_ar="تراجع التضخم العالمي إلى 2.1% في أبريل 2026 بينما أبقت البنوك المركزية على الفائدة.",
            importance=Importance.MEDIUM,
            entities=[Entity(name="IMF", type="org"), Entity(name="G7", type="org")],
            sentiment=Sentiment.NEUTRAL,
        ),
    ]


def main() -> None:
    run = DigestRun(
        run_id="smoke01",
        narrative=(
            "AI infrastructure investment accelerates globally: OpenAI's GPT-5 launch and "
            "Google Cloud's Gulf expansion signal a pivotal week for enterprise AI. "
            "Saudi Arabia's massive Nvidia stake underscores the Gulf's strategic bet on AI compute."
        ),
    )
    items = build_sample_items()

    md_path = markdown.write_markdown(run, items, OUTPUT_DIR)
    xlsx_path = excel.write_excel(run, items, OUTPUT_DIR)
    html_path = html_render.write_html(run, items, OUTPUT_DIR)

    print(md_path)
    print(xlsx_path)
    print(html_path)


if __name__ == "__main__":
    main()
