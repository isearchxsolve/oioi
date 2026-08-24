"""Groq adapter — free-tier LLM provider (OpenAI-compatible API).

Base URL: https://api.groq.com/openai/v1
Reuses the contracts defined in openrouter_adapter. NVIDIA NIM is NOT used.
"""
from __future__ import annotations

from typing import AsyncGenerator, List

import httpx

from .openrouter_adapter import (
    AIProviderAdapter,
    ChatCompletionChunk,
    ChatCompletionRequest,
    ChatCompletionResponse,
    EmbeddingRequest,
    EmbeddingResponse,
    ImageGenerationRequest,
    ImageGenerationResponse,
    Model,
    VideoGenerationRequest,
    VideoGenerationResponse,
)


class GroqAdapter(AIProviderAdapter):
    def __init__(self, api_key: str, base_url: str = "https://api.groq.com/openai/v1") -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )

    async def chat_completion(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        resp = await self.client.post("/chat/completions", json=request.model_dump())
        resp.raise_for_status()
        return ChatCompletionResponse(**resp.json())

    async def chat_completion_stream(
        self, request: ChatCompletionRequest
    ) -> AsyncGenerator[ChatCompletionChunk, None]:
        async with self.client.stream("POST", "/chat/completions", json=request.model_dump()) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data.strip() == "[DONE]":
                        break
                    yield ChatCompletionChunk.model_validate_json(data)

    async def generate_image(self, request: ImageGenerationRequest) -> ImageGenerationResponse:
        # Groq is LLM-only; image generation is delegated to other providers.
        raise NotImplementedError("Groq does not provide image generation; use Gemini/fal/Replicate.")

    async def generate_video(self, request: VideoGenerationRequest) -> VideoGenerationResponse:
        raise NotImplementedError("Groq does not provide video generation; use Gemini/fal/Replicate.")

    async def create_embedding(self, request: EmbeddingRequest) -> EmbeddingResponse:
        resp = await self.client.post("/embeddings", json=request.model_dump())
        resp.raise_for_status()
        return EmbeddingResponse(**resp.json())

    async def list_models(self) -> List[Model]:
        resp = await self.client.get("/models")
        resp.raise_for_status()
        data = resp.json()
        return [Model(**m) for m in data.get("data", [])]

    def get_provider_name(self) -> str:
        return "groq"
