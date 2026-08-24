"""QA suite for models_registry (AC-4, AC-12).

Parameterized over every registered model so each invariant is asserted per
model. These are real invariants the registry must hold: unique ids, valid
categories, real (non-placeholder) URLs, known free-tier providers, positive
latency/priority, and zero banned-provider references.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from models_registry import (
    MODELS,
    VIDEO_MODELS,
    IMAGE_MODELS,
    LLM_MODELS,
    get_model,
    get_models_by_category,
    count_models_by_category,
    group_by_category,
)

ALLOWED_PROVIDERS = {
    "local", "gemini", "pollinations", "openrouter",
    "cloudflare", "groq", "cerebras", "cohere",
}
VALID_CATEGORIES = {"Video", "Image", "LLM"}
BANNED_TOKENS = ("nvidia", "nim")


def _ids(models):
    return [m["id"] for m in models]


# --- Registry-level counts (AC-4: 25+ per category) -------------------------

def test_at_least_25_video_models():
    assert len(VIDEO_MODELS) >= 25


def test_at_least_25_image_models():
    assert len(IMAGE_MODELS) >= 25


def test_at_least_25_llm_models():
    assert len(LLM_MODELS) >= 25


def test_at_least_75_total_models():
    assert len(MODELS) >= 75


def test_models_is_concatenation_of_categories():
    assert len(MODELS) == len(VIDEO_MODELS) + len(IMAGE_MODELS) + len(LLM_MODELS)


# --- Per-model invariants (parameterized) -----------------------------------

@pytest.mark.parametrize("model", MODELS, ids=_ids(MODELS))
def test_model_has_nonempty_id(model):
    assert isinstance(model["id"], str) and model["id"].strip()


@pytest.mark.parametrize("model", MODELS, ids=_ids(MODELS))
def test_model_has_nonempty_name(model):
    assert isinstance(model["name"], str) and model["name"].strip()


@pytest.mark.parametrize("model", MODELS, ids=_ids(MODELS))
def test_model_has_valid_category(model):
    assert model["category"] in VALID_CATEGORIES


@pytest.mark.parametrize("model", MODELS, ids=_ids(MODELS))
def test_model_provider_is_allowed_free_tier(model):
    assert model["provider"] in ALLOWED_PROVIDERS


@pytest.mark.parametrize("model", MODELS, ids=_ids(MODELS))
def test_model_url_is_real_not_placeholder(model):
    url = model["url"]
    assert url.startswith("http")
    assert "example.com" not in url
    assert "placeholder" not in url.lower()


@pytest.mark.parametrize("model", MODELS, ids=_ids(MODELS))
def test_model_has_capabilities(model):
    assert isinstance(model["capabilities"], list) and len(model["capabilities"]) > 0


@pytest.mark.parametrize("model", MODELS, ids=_ids(MODELS))
def test_model_latency_is_positive(model):
    assert model["latency_ms_est"] > 0


@pytest.mark.parametrize("model", MODELS, ids=_ids(MODELS))
def test_model_priority_is_nonnegative(model):
    assert model["priority"] >= 0


@pytest.mark.parametrize("model", MODELS, ids=_ids(MODELS))
def test_model_is_enabled(model):
    assert model["enabled"] is True


@pytest.mark.parametrize("model", MODELS, ids=_ids(MODELS))
def test_model_has_no_banned_provider_reference(model):
    blob = " ".join([
        str(model["id"]), str(model["name"]),
        str(model["provider"]), str(model["url"]),
    ]).lower()
    for token in BANNED_TOKENS:
        assert token not in blob


# --- Aggregate invariants ---------------------------------------------------

def test_model_ids_are_unique():
    ids = _ids(MODELS)
    assert len(ids) == len(set(ids))


def test_get_model_returns_known_model():
    model = get_model(MODELS[0]["id"])
    assert model["id"] == MODELS[0]["id"]


def test_get_model_returns_empty_for_unknown():
    assert get_model("does-not-exist") == {}


@pytest.mark.parametrize("category", sorted(VALID_CATEGORIES))
def test_get_models_by_category_only_returns_matching(category):
    models = get_models_by_category(category)
    assert len(models) >= 25
    assert all(m["category"] == category for m in models)


def test_count_models_by_category_is_consistent():
    counts = count_models_by_category()
    assert counts["Video"] == len(VIDEO_MODELS)
    assert counts["Image"] == len(IMAGE_MODELS)
    assert counts["LLM"] == len(LLM_MODELS)
    assert counts["Total"] == len(MODELS)


def test_group_by_category_partitions_models():
    grouped = group_by_category(MODELS)
    assert set(grouped.keys()) == VALID_CATEGORIES
    assert sum(len(v) for v in grouped.values()) == len(MODELS)
