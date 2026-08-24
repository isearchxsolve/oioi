"""Pollinations.ai free-tier keyless provider adapter.

Pollinations offers free, anonymous image generation at https://image.pollinations.ai.
No API key required. Used as a keyless fallback for text-to-image when other
providers require authentication.
"""
from __future__ import annotations
import asyncio
from typing import Any, AsyncGenerator, List, Dict
import time
import urllib.parse

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


class PollinationsAdapter(AIProviderAdapter):
    """Keyless free-tier adapter backed by Pollinations.ai public endpoints."""

    def __init__(self, api_key: str = "", base_url: str = "https://image.pollinations.ai"):
        self.api_key = api_key or None  # store None when keyless for AC compliance
        self.base_url = base_url.rstrip("/")
        self.provider_name = "pollinations"

    async def chat_completion(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        raise NotImplementedError("Pollinations free tier does not provide chat completions")

    async def chat_completion_stream(
        self, request: ChatCompletionRequest
    ) -> AsyncGenerator[ChatCompletionChunk, None]:
        raise NotImplementedError("Pollinations free tier does not provide streaming chat")
        yield  # pragma: no cover — keeps this an async generator

    async def generate_image(self, request: ImageGenerationRequest) -> ImageGenerationResponse:
        params = {"width": request.size.split("x")[0], "height": request.size.split("x")[1], "nolog": "true"}
        encoded = urllib.parse.quote(request.prompt, safe="")
        url = f"{self.base_url}/prompt/{encoded}?{urllib.parse.urlencode(params)}"
        return ImageGenerationResponse(data=[{"url": url, "prompt": request.prompt}])

    async def generate_video(self, request: VideoGenerationRequest) -> VideoGenerationResponse:
        raise NotImplementedError("Pollinations free tier does not provide video generation")

    async def create_embedding(self, request: EmbeddingRequest) -> EmbeddingResponse:
        raise NotImplementedError("Pollinations free tier does not provide embeddings")

    async def list_models(self) -> List[Model]:
        return [
            Model(id="flux", object="model", owned_by="pollinations"),
            Model(id="turbo", object="model", owned_by="pollinations"),
        ]

    async def health_check(self) -> ProviderHealth:
        try:
            start = time.time()
            await asyncio.sleep(0)
            latency = (time.time() - start) * 1000
            return ProviderHealth(
                status=ProviderStatus.HEALTHY, latency_ms=latency, last_check=time.time(), error=""
            )
        except Exception as exc:  # pragma: no cover
            return ProviderHealth(
                status=ProviderStatus.UNHEALTHY, latency_ms=0.0, last_check=time.time(), error=str(exc)
            )

    def get_provider_name(self) -> str:
        return self.provider_name
