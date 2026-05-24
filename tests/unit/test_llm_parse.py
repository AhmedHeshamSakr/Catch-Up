import pytest
from pydantic import BaseModel

from app.llm.parse import LLMOutputError, parse_model_json


class _Item(BaseModel):
    id: str
    score: float


class _Result(BaseModel):
    items: list[_Item]


class _ArrayModel(BaseModel):
    # RootModel-style not needed; test an array wrapped via a model below.
    pass


def test_parse_clean_json():
    out = parse_model_json('{"items": [{"id": "a", "score": 0.5}]}', _Result)
    assert out.items[0].id == "a"
    assert out.items[0].score == 0.5


def test_parse_fenced_json_block():
    text = "```json\n{\"items\": [{\"id\": \"b\", \"score\": 0.9}]}\n```"
    out = parse_model_json(text, _Result)
    assert out.items[0].id == "b"


def test_parse_bare_fence():
    text = "```\n{\"items\": []}\n```"
    out = parse_model_json(text, _Result)
    assert out.items == []


def test_parse_with_leading_and_trailing_prose():
    text = (
        "Sure, here is the result you asked for:\n"
        '{"items": [{"id": "c", "score": 0.1}]}\n'
        "Let me know if you need anything else."
    )
    out = parse_model_json(text, _Result)
    assert out.items[0].id == "c"


def test_parse_empty_string_raises():
    with pytest.raises(LLMOutputError):
        parse_model_json("", _Result)


def test_parse_whitespace_only_raises():
    with pytest.raises(LLMOutputError):
        parse_model_json("   \n\t ", _Result)


def test_parse_none_raises():
    with pytest.raises(LLMOutputError):
        parse_model_json(None, _Result)  # type: ignore[arg-type]


def test_parse_nonsense_raises():
    with pytest.raises(LLMOutputError):
        parse_model_json("this is not json at all", _Result)


def test_parse_array_model():
    # An array value embedded in prose; model is a RootModel over a list.
    from pydantic import RootModel

    class _Verdicts(RootModel[list[_Item]]):
        pass

    text = 'Here you go: [{"id": "x", "score": 0.2}, {"id": "y", "score": 0.3}] thanks'
    out = parse_model_json(text, _Verdicts)
    assert out.root[0].id == "x"
    assert out.root[1].id == "y"


def test_parse_object_with_nested_braces_in_string():
    # Brace/bracket tracking must respect string contents (no premature close).
    text = 'noise {"items": [{"id": "a {b}", "score": 0.4}]} tail'
    out = parse_model_json(text, _Result)
    assert out.items[0].id == "a {b}"
