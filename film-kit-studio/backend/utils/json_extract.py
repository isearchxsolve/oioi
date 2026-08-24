"""
JSON array extraction from LLM responses.

Migrated from film_kit.py — handles markdown fences, preamble,
postamble, and nested objects inside the array.
"""

import json
import re
from typing import Any


def extract_json_array(text: str) -> list[dict[str, Any]]:
    """
    Extract the first valid JSON array from an LLM response string.

    The model may wrap output in markdown fences or add preamble/postamble.
    Strategy: strip fences, try full text, then fall back to balanced
    bracket walking for robust extraction.
    """
    # Strip markdown code fences
    stripped = re.sub(r"```(?:json)?\s*", "", text).strip()

    # Try parsing the whole cleaned string first
    if stripped.startswith("["):
        try:
            result = json.loads(stripped)
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

    # Walk char-by-char to find balanced brackets — robust against
    # nested objects inside the array.
    start = stripped.find("[")
    if start == -1:
        raise ValueError("No JSON array found in model response.")

    depth = 0
    for i, ch in enumerate(stripped[start:], start):
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                try:
                    result = json.loads(stripped[start : i + 1])
                    if isinstance(result, list):
                        return result
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"JSON parse error in model response: {exc}"
                    ) from exc

    raise ValueError("Unbalanced brackets in model response.")
