"""Cloudflare Workers AI adapter — free-tier LLM provider.

Base URL: https://api.cloudflare.com/client/v4/accounts/{account_id}/ai
Cloudflare Workers AI offers Llama, Mistral, and embedding models with a
free tier of 10k neurons/day (~100k req/day). Reuses the contracts defined
in `backend.providers.base`. NVIDIA NIM is NOT used.
"""
from __future__ import annotations

from typing import AsyncGenerator, List

import httpx

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


class CloudflareAdapter(AIProviderAdapter):
    """Adapter for Cloudflare Workers AI (OpenAI-compatible v1 endpoint)."""

    def __init__(
        self,
        api_key: str,
        account_id: str,
        base_url: str = "https://api.cloudflare.com/client/v4",
    ) -> None:
        self.api_key = api_key
        self.account_id = account_id
        self.base_url = base_url
        self.ai_base = f"{self.base_url}/accounts/{self.account_id}/ai"
        self.client = httpx.AsyncClient(
            base_url=self.ai_base,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )

    async def chat_completion(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        # Cloudflare exposes an OpenAI-compatible endpoint at /v1/chat/completions
        resp = await self.client.post("/v1/chat/completions", json=request.model_dump())
        resp.raise_for_status()
        return ChatCompletionResponse(**resp.json())

    async def chat_completion_stream(
        self, request: ChatCompletionRequest
    ) -> AsyncGenerator[ChatCompletionChunk, None]:
        async with self.client.stream("POST", "/v1/chat/completions", json=request.model_dump()) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data.strip() == "[DONE]":
                        break
                    yield ChatCompletionChunk.model_validate_json(data)

    async def generate_image(self, request: ImageGenerationRequest) -> ImageGenerationResponse:
        # Cloudflare Workers AI supports text-to-image models (e.g. @cf/stable-diffusion-xl-...)
        payload = {"prompt": request.prompt, "n": request.n}
        resp = await self.client.post("/models/stable-diffusion-xl", json=payload)
        resp.raise_for_status()
        return ImageGenerationResponse(data=resp.json().get("data", []))

    async def generate_video(self, request: VideoGenerationRequest) -> VideoGenerationResponse:
        raise NotImplementedError("Cloudflare Workers AI does not provide video generation; delegate to fal/Replicate.")

    async def create_embedding(self, request: EmbeddingRequest) -> EmbeddingResponse:
        payload = {"text": request.input, "model": request.model}
        resp = await self.client.post("/models/embeddings", json=payload)
        resp.raise_for_status()
        return EmbeddingResponse(data=resp.json().get("data", []), model=request.model)

    async def list_models(self) -> List[Model]:
        resp = await self.client.get("/models")
        resp.raise_for_status()
        data = resp.json()
        return [Model(**m) for m in data.get("data", [])]

    async def health_check(self) -> ProviderHealth:
        try:
            await self.client.get("/models")
            return ProviderHealth(status=ProviderStatus.HEALTHY)
        except Exception as exc:
            return ProviderHealth(status=ProviderStatus.UNHEALTHY, error=str(exc))

    def get_provider_name(self) -> str:
        return "cloudflare"
