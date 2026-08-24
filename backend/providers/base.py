"""Abstract base class for free-tier LLM provider adapters.

This module defines the `AIProviderAdapter` interface that every provider
adapter (Groq, OpenRouter, Cerebras, Cohere, Cloudflare, ...) must implement.
It also defines the shared Pydantic request/response contracts and the
`ProviderHealth` / `ProviderStatus` runtime-health models used by the
`ProviderRegistry`.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, AsyncGenerator, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Shared request/response contracts (OpenAI-compatible)
# ---------------------------------------------------------------------------
class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[Dict[str, Any]]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = None
    top_p: Optional[float] = 1.0
    stream: bool = False
    # All 8 orchestrator call sites pass response_format={"type": "json_object"} but this field
    # was missing, so pydantic dropped it silently and no agent ever ran in JSON mode. Without it
    # the model emits malformed JSON (missing braces, prose leaking in) and _parse_json dies.
    response_format: Optional[Dict[str, Any]] = None


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: List[Dict[str, Any]]
    # Providers return nested usage details (e.g. OpenRouter's
    # prompt_tokens_details), so keep this permissive.
    usage: Dict[str, Any] = Field(default_factory=dict)


class ChatCompletionChunk(BaseModel):
    id: str
    object: str = "chat.completion.chunk"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: List[Dict[str, Any]]


class ImageGenerationRequest(BaseModel):
    prompt: str
    model: str
    n: int = 1
    size: str = "1024x1024"
    response_format: str = "url"


class ImageGenerationResponse(BaseModel):
    created: int = Field(default_factory=lambda: int(time.time()))
    data: List[Dict[str, Any]]


class VideoGenerationRequest(BaseModel):
    prompt: str
    model: str
    first_frame: Optional[str] = None
    last_frame: Optional[str] = None


class VideoGenerationResponse(BaseModel):
    created: int = Field(default_factory=lambda: int(time.time()))
    data: List[Dict[str, Any]]


class EmbeddingRequest(BaseModel):
    input: Any
    model: str


class EmbeddingResponse(BaseModel):
    object: str = "list"
    data: List[Dict[str, Any]]
    model: str
    usage: Dict[str, Any] = Field(default_factory=dict)


class Model(BaseModel):
    id: str
    object: str = "model"
    created: int = 0
    owned_by: str = ""


# ---------------------------------------------------------------------------
# Runtime health tracking
# ---------------------------------------------------------------------------
class ProviderStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class ProviderHealth(BaseModel):
    status: ProviderStatus = ProviderStatus.UNKNOWN
    latency_ms: float = 0.0
    last_check: float = 0.0
    error: str = ""


# ---------------------------------------------------------------------------
# Unified adapter interface
# ---------------------------------------------------------------------------
class AIProviderAdapter(ABC):
    """Unified interface every free-tier provider must implement."""

    @abstractmethod
    async def chat_completion(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        ...

    @abstractmethod
    async def chat_completion_stream(
        self, request: ChatCompletionRequest
    ) -> AsyncGenerator[ChatCompletionChunk, None]:
        ...

    @abstractmethod
    async def generate_image(self, request: ImageGenerationRequest) -> ImageGenerationResponse:
        ...

    @abstractmethod
    async def generate_video(self, request: VideoGenerationRequest) -> VideoGenerationResponse:
        ...

    @abstractmethod
    async def create_embedding(self, request: EmbeddingRequest) -> EmbeddingResponse:
        ...

    @abstractmethod
    async def list_models(self) -> List[Model]:
        ...

    @abstractmethod
    async def health_check(self) -> ProviderHealth:
        ...

    @abstractmethod
    def get_provider_name(self) -> str:
        ...
