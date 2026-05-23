from app.core.config import SourceConfig, load_sources
from app.core.domain import Category, SourceType


def test_load_sources_parses_yaml(tmp_path):
    (tmp_path / "sources.yaml").write_text(
        "sources:\n"
        "  - id: techcrunch\n"
        "    type: rss\n"
        "    name: TechCrunch\n"
        "    url: https://techcrunch.com/feed/\n"
        "    category_hint: ai_tech\n"
        "    enabled: true\n",
        encoding="utf-8",
    )
    sources = load_sources(tmp_path)
    assert len(sources) == 1
    s = sources[0]
    assert isinstance(s, SourceConfig)
    assert s.id == "techcrunch"
    assert s.type == SourceType.RSS
    assert s.category_hint == Category.AI_TECH
    assert s.enabled is True
