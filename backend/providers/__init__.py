"""Provider adapter package.

Re-exports the unified adapter interface and the provider registry so the
rest of the backend can do `from backend.providers import AIProviderAdapter,
ProviderRegistry` without reaching into submodules.

NVIDIA NIM is a TOTAL NO-GO (AC-10) and is never imported here.
"""
from __future__ import annotations

from .base import (
    AIProviderAdapter,
    ChatCompletionChunk,
    ChatCompletionRequest,
    ChatCompletionResponse,
    EmbeddingRequest,
    EmbeddingResponse,
    ImageGenerationRequest,
    ImageGenerationResponse,
    Model,
    ProviderHealth,
    ProviderStatus,
    VideoGenerationRequest,
    VideoGenerationResponse,
)
from .registry import ProviderRegistry, get_registry, reset_registry

__all__ = [
    "AIProviderAdapter",
    "ChatCompletionChunk",
    "ChatCompletionRequest",
    "ChatCompletionResponse",
    "EmbeddingRequest",
    "EmbeddingResponse",
    "ImageGenerationRequest",
    "ImageGenerationResponse",
    "Model",
    "ProviderHealth",
    "ProviderStatus",
    "VideoGenerationRequest",
    "VideoGenerationResponse",
    "ProviderRegistry",
    "get_registry",
    "reset_registry",
]
