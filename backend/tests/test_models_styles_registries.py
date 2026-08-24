import pytest
from models_registry import (
    MODELS,
    VIDEO_MODELS,
    IMAGE_MODELS,
    LLM_MODELS,
    group_by_category,
    get_models_by_category,
    count_models_by_category,
)
from styles_registry import STYLES, count_by_category, filter_by_category


def test_models_registry_counts():
    """Verify 25+ models per category and total models >= 75 (AC-4, AC-12)."""
    assert len(VIDEO_MODELS) >= 25
    assert len(IMAGE_MODELS) >= 25
    assert len(LLM_MODELS) >= 25
    assert len(MODELS) >= 75


def test_models_registry_no_example_com():
    """Verify no example.com placeholders exist in models registry (AC-12)."""
    for model in MODELS:
        url = model.get("url", "")
        assert "example.com" not in url, f"Model {model['id']} contains placeholder url: {url}"


def test_models_group_by_category():
    """Verify grouping and querying by category."""
    grouped = group_by_category(MODELS)
    assert "Video" in grouped
    assert "Image" in grouped
    assert "LLM" in grouped

    counts = count_models_by_category()
    assert counts["Video"] >= 25
    assert counts["Image"] >= 25
    assert counts["LLM"] >= 25


def test_styles_registry_150_plus():
    """Verify 150+ visual animation styles with prompt suffixes (AC-5, AC-11)."""
    assert len(STYLES) >= 150
    for style in STYLES:
        assert "id" in style
        assert "name" in style
        assert "category" in style
        assert "promptSuffix" in style
        assert len(style["promptSuffix"]) > 0


def test_styles_filter_and_count():
    """Verify style filtering and category count."""
    counts = count_by_category(STYLES)
    assert len(counts) > 5
    anime_styles = filter_by_category(STYLES, "Anime")
    assert len(anime_styles) > 0
