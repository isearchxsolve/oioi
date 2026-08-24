"""QA suite for styles_registry (AC-5).

Parameterized over every registered style. Real invariants: unique ids, valid
categories, keyless Pollinations preview URLs, non-empty prompt suffixes, and
no banned-provider references.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from styles_registry import (
    STYLES,
    get_style,
    count_by_category,
    filter_by_category,
)

VALID_CATEGORIES = {
    "Anime", "3D/CG", "Illustrated", "Pixel/Retro",
    "Painting", "Photographic", "Cyberpunk", "Minimalist",
}


def _ids(styles):
    return [s["id"] for s in styles]


def test_at_least_150_styles():
    assert len(STYLES) >= 150


@pytest.mark.parametrize("style", STYLES, ids=_ids(STYLES))
def test_style_has_nonempty_id(style):
    assert isinstance(style["id"], str) and style["id"].strip()


@pytest.mark.parametrize("style", STYLES, ids=_ids(STYLES))
def test_style_has_nonempty_name(style):
    assert isinstance(style["name"], str) and style["name"].strip()


@pytest.mark.parametrize("style", STYLES, ids=_ids(STYLES))
def test_style_has_valid_category(style):
    assert style["category"] in VALID_CATEGORIES


@pytest.mark.parametrize("style", STYLES, ids=_ids(STYLES))
def test_style_preview_is_keyless_pollinations(style):
    assert style["previewUrl"].startswith("https://image.pollinations.ai/")


@pytest.mark.parametrize("style", STYLES, ids=_ids(STYLES))
def test_style_thumbnail_matches_preview(style):
    assert style["thumbnail"] == style["previewUrl"]


@pytest.mark.parametrize("style", STYLES, ids=_ids(STYLES))
def test_style_has_prompt_suffix(style):
    assert isinstance(style["promptSuffix"], str) and style["promptSuffix"].strip()


@pytest.mark.parametrize("style", STYLES, ids=_ids(STYLES))
def test_style_is_builtin(style):
    assert style["isBuiltIn"] is True


@pytest.mark.parametrize("style", STYLES, ids=_ids(STYLES))
def test_style_has_no_banned_provider_reference(style):
    blob = " ".join([
        str(style["id"]), str(style["name"]), str(style["previewUrl"]),
    ]).lower()
    assert "nvidia" not in blob


def test_style_ids_are_unique():
    ids = _ids(STYLES)
    assert len(ids) == len(set(ids))


def test_get_style_returns_known_style():
    style = get_style(STYLES[0]["id"])
    assert style["id"] == STYLES[0]["id"]


def test_get_style_returns_empty_for_unknown():
    assert get_style("does-not-exist") == {}


def test_count_by_category_sums_to_total():
    counts = count_by_category(STYLES)
    assert sum(counts.values()) == len(STYLES)


@pytest.mark.parametrize("category", sorted(VALID_CATEGORIES))
def test_filter_by_category_only_returns_matching(category):
    filtered = filter_by_category(STYLES, category)
    assert len(filtered) > 0
    assert all(s["category"] == category for s in filtered)
