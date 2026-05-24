from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

BaseModelT = TypeVar("BaseModelT", bound=BaseModel)


class LLMOutputError(ValueError):
    """Raised when an LLM's text output cannot be parsed into the target model."""


def _strip_code_fences(text: str) -> str:
    """Remove a surrounding Markdown code fence (```json ... ``` or ``` ... ```)."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    # Drop the opening fence line (which may carry a language tag like ```json).
    newline = stripped.find("\n")
    if newline == -1:
        return stripped
    body = stripped[newline + 1 :]
    # Drop a trailing closing fence if present.
    closing = body.rfind("```")
    if closing != -1:
        body = body[:closing]
    return body.strip()


def _extract_first_json_value(text: str) -> str | None:
    """Return the first balanced JSON object/array substring, or None.

    Tracks brace/bracket depth while respecting string literals and escapes so
    that braces inside strings do not affect nesting.
    """
    start = -1
    opener = ""
    closer = ""
    for i, ch in enumerate(text):
        if ch == "{":
            start, opener, closer = i, "{", "}"
            break
        if ch == "[":
            start, opener, closer = i, "[", "]"
            break
    if start == -1:
        return None

    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def parse_model_json(text: str, model: type[BaseModelT]) -> BaseModelT:
    """Parse ``text`` into ``model``, repairing common LLM output noise.

    Handles None/empty/whitespace, Markdown code fences, and prose surrounding a
    JSON value. Raises :class:`LLMOutputError` (chaining the original) on failure.
    """
    if text is None or not text.strip():
        raise LLMOutputError("empty model output")

    cleaned = _strip_code_fences(text)
    try:
        return model.model_validate_json(cleaned)
    except Exception as first_error:  # fall through to the JSON-repair path below
        candidate = _extract_first_json_value(cleaned)
        if candidate is not None:
            try:
                return model.model_validate_json(candidate)
            except Exception as second_error:
                raise LLMOutputError(
                    f"could not parse model output into {model.__name__}"
                ) from second_error
        raise LLMOutputError(
            f"could not parse model output into {model.__name__}"
        ) from first_error
