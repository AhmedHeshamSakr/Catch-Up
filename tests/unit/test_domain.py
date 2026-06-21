from app.core.domain import (
    Category,
    NewsItem,
    RawItem,
    SourceType,
    make_item_id,
)


def test_make_item_id_is_stable_and_url_normalized():
    assert make_item_id("https://A.com/x ") == make_item_id("https://a.com/x")
    assert len(make_item_id("https://a.com/x")) == 16


def test_newsitem_from_raw_sets_id_category_and_status():
    raw = RawItem(
        source_id="tc", source_type=SourceType.RSS, source_name="TechCrunch",
        url="https://x.com/a", title="Hello", category_hint=Category.AI_TECH,
    )
    item = NewsItem.from_raw(raw, run_id="r1")
    assert item.id == make_item_id("https://x.com/a")
    assert item.category == Category.AI_TECH
    assert item.status == "raw"
    assert item.digest_run_id == "r1"


def test_newsitem_from_raw_copies_image_url():
    raw = RawItem(
        source_id="tc", source_type=SourceType.RSS, source_name="TechCrunch",
        url="https://x.com/a", title="Hello",
        image_url="https://img.example/thumb.jpg",
    )
    item = NewsItem.from_raw(raw, run_id="r1")
    assert item.image_url == "https://img.example/thumb.jpg"


def test_newsitem_image_url_defaults_none():
    raw = RawItem(
        source_id="tc", source_type=SourceType.RSS, source_name="TechCrunch",
        url="https://x.com/a", title="Hello",
    )
    assert raw.image_url is None
    assert NewsItem.from_raw(raw, run_id="r1").image_url is None
