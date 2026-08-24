"""QA suite for providers.base — shared pydantic contracts + adapter interface."""
from __future__ import annotations

import os
import sys

import pytest
from pydantic import ValidationError

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from providers.base import (
    AIProviderAdapter,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionChunk,
    ImageGenerationRequest,
    ImageGenerationResponse,
    VideoGenerationRequest,
    VideoGenerationResponse,
    EmbeddingRequest,
    EmbeddingResponse,
    Model,
    ProviderHealth,
    ProviderStatus,
)


# --- ChatCompletionRequest --------------------------------------------------

def test_chat_request_requires_model_and_messages():
    with pytest.raises(ValidationError):
        ChatCompletionRequest()


def test_chat_request_defaults():
    req = ChatCompletionRequest(model="m", messages=[{"role": "user", "content": "hi"}])
    assert req.temperature == 0.7
    assert req.max_tokens is None
    assert req.top_p == 1.0
    assert req.stream is False


@pytest.mark.parametrize("temperature", [0.0, 0.5, 1.0, 2.0])
def test_chat_request_accepts_temperature(temperature):
    req = ChatCompletionRequest(model="m", messages=[], temperature=temperature)
    assert req.temperature == temperature


# --- ChatCompletionResponse / Chunk -----------------------------------------

def test_chat_response_requires_fields():
    with pytest.raises(ValidationError):
        ChatCompletionResponse()


def test_chat_response_defaults():
    resp = ChatCompletionResponse(id="1", model="m", choices=[])
    assert resp.object == "chat.completion"
    assert resp.usage == {}
    assert resp.created > 0


def test_chat_chunk_requires_fields():
    with pytest.raises(ValidationError):
        ChatCompletionChunk()


def test_chat_chunk_object_default():
    chunk = ChatCompletionChunk(id="1", model="m", choices=[])
    assert chunk.object == "chat.completion.chunk"


# --- Image ------------------------------------------------------------------

def test_image_request_requires_prompt_and_model():
    with pytest.raises(ValidationError):
        ImageGenerationRequest()


def test_image_request_defaults():
    req = ImageGenerationRequest(prompt="p", model="m")
    assert req.n == 1
    assert req.size == "1024x1024"
    assert req.response_format == "url"


def test_image_response_defaults():
    resp = ImageGenerationResponse(data=[])
    assert resp.data == []
    assert resp.created > 0


# --- Video ------------------------------------------------------------------

def test_video_request_requires_prompt_and_model():
    with pytest.raises(ValidationError):
        VideoGenerationRequest()


def test_video_request_frames_optional():
    req = VideoGenerationRequest(prompt="p", model="m")
    assert req.first_frame is None
    assert req.last_frame is None


def test_video_response_defaults():
    assert VideoGenerationResponse(data=[]).created > 0


# --- Embedding --------------------------------------------------------------

def test_embedding_request_requires_model():
    with pytest.raises(ValidationError):
        EmbeddingRequest(input="x")


def test_embedding_request_accepts_string_input():
    assert EmbeddingRequest(input="hello", model="m").input == "hello"


def test_embedding_request_accepts_list_input():
    assert EmbeddingRequest(input=["a", "b"], model="m").input == ["a", "b"]


def test_embedding_response_defaults():
    resp = EmbeddingResponse(data=[], model="m")
    assert resp.object == "list"
    assert resp.usage == {}


# --- Model ------------------------------------------------------------------

def test_model_requires_id():
    with pytest.raises(ValidationError):
        Model()


def test_model_defaults():
    m = Model(id="x")
    assert m.object == "model"
    assert m.created == 0
    assert m.owned_by == ""


# --- ProviderStatus / ProviderHealth ----------------------------------------

def test_provider_status_has_four_states():
    assert {s.value for s in ProviderStatus} == {"healthy", "degraded", "unhealthy", "unknown"}


@pytest.mark.parametrize("status", list(ProviderStatus))
def test_provider_status_roundtrips(status):
    assert ProviderStatus(status.value) is status


def test_provider_health_defaults():
    h = ProviderHealth()
    assert h.status == ProviderStatus.UNKNOWN
    assert h.latency_ms == 0.0
    assert h.error == ""


# --- Adapter interface ------------------------------------------------------

def test_adapter_is_abstract():
    with pytest.raises(TypeError):
        AIProviderAdapter()


@pytest.mark.parametrize("method", [
    "chat_completion", "chat_completion_stream", "generate_image",
    "generate_video", "create_embedding", "list_models", "health_check",
    "get_provider_name",
])
def test_adapter_defines_method(method):
    assert hasattr(AIProviderAdapter, method)
