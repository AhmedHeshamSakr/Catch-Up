from app.core.domain import Category, NewsItem, RawItem, SourceType
from app.pipeline import digest_editor


def _item(title):
    raw = RawItem(source_id="s", source_type=SourceType.RSS, source_name="S",
                  url="https://a.com/1", title=title, category_hint=Category.AI_TECH)
    return NewsItem.from_raw(raw)


def test_write_narrative_uses_injected_generator_and_passes_top_items():
    captured = {}

    def fake_generate(items):
        captured["n"] = len(items)
        return "Today's headline."

    out = digest_editor.write_narrative([_item("a"), _item("b")], fake_generate, top_n=5)
    assert out == "Today's headline."
    assert captured["n"] == 2


def test_write_narrative_empty_returns_empty_string():
    assert digest_editor.write_narrative([], lambda x: "x", top_n=5) == ""
