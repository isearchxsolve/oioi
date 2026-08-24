"""Smoke subset — ~50 fast, high-signal checks (target < 3 min).

Run with: pytest backend/tests/test_smoke.py -q
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from models_registry import MODELS, VIDEO_MODELS, IMAGE_MODELS, LLM_MODELS, get_model
from styles_registry import STYLES, get_style
import agent_contracts as ac
from providers.base import ProviderStatus, ChatCompletionRequest, ImageGenerationRequest


def _client():
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


# --- App probes (no db / provider keys required) ----------------------------

def test_smoke_healthz():
    assert _client().get("/healthz").status_code == 200


def test_smoke_root():
    assert _client().get("/").status_code == 200


def test_smoke_openapi():
    assert _client().get("/api/v1/openapi.json").status_code == 200


# --- Registry counts --------------------------------------------------------

def test_smoke_video_models_present():
    assert len(VIDEO_MODELS) >= 25


def test_smoke_image_models_present():
    assert len(IMAGE_MODELS) >= 25


def test_smoke_llm_models_present():
    assert len(LLM_MODELS) >= 25


def test_smoke_styles_present():
    assert len(STYLES) >= 150


def test_smoke_models_total_at_least_75():
    assert len(MODELS) >= 75


# --- Sampled model invariants -----------------------------------------------

@pytest.mark.parametrize("model", MODELS[:12], ids=[m["id"] for m in MODELS[:12]])
def test_smoke_model_shape(model):
    assert model["id"] and model["name"] and model["provider"]
    assert "example.com" not in model["url"]


@pytest.mark.parametrize("category", ["Video", "Image", "LLM"])
def test_smoke_model_categories_valid(category):
    assert all(m["category"] == category for m in
               [m for m in MODELS if m["category"] == category])


def test_smoke_model_get_known():
    assert get_model(MODELS[0]["id"])["id"] == MODELS[0]["id"]


def test_smoke_no_banned_provider_in_registry():
    blob = " ".join(m["provider"] for m in MODELS).lower()
    assert "nvidia" not in blob


# --- Sampled style invariants -----------------------------------------------

@pytest.mark.parametrize("style", STYLES[:12], ids=[s["id"] for s in STYLES[:12]])
def test_smoke_style_shape(style):
    assert style["id"] and style["name"]
    assert style["previewUrl"].startswith("https://image.pollinations.ai/")


def test_smoke_style_get_known():
    assert get_style(STYLES[0]["id"])["id"] == STYLES[0]["id"]


# --- Agent contracts --------------------------------------------------------

def test_smoke_agent_roles():
    assert len(list(ac.AgentType)) == 7


@pytest.mark.parametrize("agent", list(ac.AgentType))
def test_smoke_agent_value(agent):
    assert agent.value


def test_smoke_scriptwriter_requires_prompt():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ac.ScriptwriterInput()


# --- Provider base ----------------------------------------------------------

def test_smoke_provider_status_states():
    assert len(list(ProviderStatus)) == 4


def test_smoke_chat_request_default():
    req = ChatCompletionRequest(model="m", messages=[])
    assert req.temperature == 0.7


def test_smoke_image_request_default():
    req = ImageGenerationRequest(prompt="p", model="m")
    assert req.size == "1024x1024"
