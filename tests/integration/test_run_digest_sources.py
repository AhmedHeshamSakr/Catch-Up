from app import runner
from app.core.config import Settings
from app.core.domain import Category, RawItem, RunStatus, SourceType
from app.pipeline.schema import ProcessingResult


def _settings(tmp_path, sources_yaml):
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "sources.yaml").write_text(sources_yaml, encoding="utf-8")
    (cfg / "watchlist.yaml").write_text("entities: []\nkeywords: []\n", encoding="utf-8")
    return Settings(sqlite_path=str(tmp_path / "db.sqlite"),
                    config_dir=str(cfg), output_dir=str(tmp_path / "out"),
                    gnews_api_key="TESTKEY")


def test_dispatch_collects_from_api_and_scrape(tmp_path, monkeypatch):
    yaml = (
        "sources:\n"
        "  - id: g\n    type: api\n    name: GNews\n    query: ai\n    category_hint: ai_tech\n    enabled: true\n"
        "  - id: s\n    type: scrape\n    name: Site\n    url: https://site.example/news\n"
        "    selector: a.headline\n    category_hint: business_finance\n    enabled: true\n"
    )
    settings = _settings(tmp_path, yaml)
    monkeypatch.setattr(runner.newsapi, "collect",
                        lambda source, key, **kw: [RawItem(source_id="g", source_type=SourceType.API,
                            source_name="GNews", url="https://n/1", title="API item",
                            category_hint=Category.AI_TECH)])
    monkeypatch.setattr(runner.scrape, "collect",
                        lambda source, **kw: [RawItem(source_id="s", source_type=SourceType.SCRAPE,
                            source_name="Site", url="https://n/2", title="Scraped item",
                            category_hint=Category.BUSINESS_FINANCE)])
    run = runner.run_digest(settings=settings,
                            processor=lambda items: ProcessingResult(items=[]),
                            narrator=lambda items: "",
                            critic=lambda items: [])
    assert run.status == RunStatus.SUCCESS
    assert run.collected == 2  # one from api, one from scrape
