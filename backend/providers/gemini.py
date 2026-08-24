"""Gemini adapter — Google AI Studio (free-tier multimodal).

Google AI Studio offers free-tier access to:
- Chat completions (Gemini 2.5 Flash / Pro) via ``generateContent``
- Image generation (Gemini 2.0 Flash experimental / Imagen 3)
- Video generation (Veo 2 via Long-running Operation)
- Text-to-speech (Gemini TTS / Gemini Live)
- Embeddings (``text-embedding-004``)

No proprietary cloud dependencies — pure Google AI Studio endpoints.
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


class GeminiAdapter(AIProviderAdapter):
    """Adapter for Google Gemini (AI Studio) free-tier endpoints."""

    DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(self, api_key: str, base_url: str = DEFAULT_BASE_URL) -> None:
        if not api_key:
            raise ValueError("GeminiAdapter requires a non-empty api_key")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.provider_name = "gemini"
        self.client = httpx.AsyncClient(
            headers={"Content-Type": "application/json"},
            timeout=120.0,
        )

    def get_provider_name(self) -> str:
        return self.provider_name

    async def chat_completion(
        self, request: ChatCompletionRequest
    ) -> ChatCompletionResponse:
        url = f"{self.base_url}/models/{request.model}:generateContent?key={self.api_key}"
        contents = [
            {"role": m["role"] if m["role"] != "assistant" else "model",
             "parts": [{"text": m["content"]}]}
            for m in request.messages
        ]
        payload = {"contents": contents}
        resp = await self.client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        usage = data.get("usageMetadata", {})
        return ChatCompletionResponse(
            id=data.get("id", "gemini-completion"),
            model=request.model,
            choices=[{"message": {"role": "assistant", "content": text},
                      "finish_reason": data["candidates"][0].get("finishReason", "stop")}],
            usage={
                "prompt_tokens": usage.get("promptTokenCount", 0),
                "completion_tokens": usage.get("candidatesTokenCount", 0),
                "total_tokens": usage.get("totalTokenCount", 0),
            },
        )

    async def chat_completion_stream(
        self, request: ChatCompletionRequest
    ) -> AsyncGenerator[ChatCompletionChunk, None]:
        # Streaming via server-sent events is not yet implemented.
        raise NotImplementedError("GeminiAdapter streaming — not yet implemented")
        yield  # pragma: no cover — makes this a generator

    async def generate_image(
        self, request: ImageGenerationRequest
    ) -> ImageGenerationResponse:
        url = f"{self.base_url}/models/{request.model}:generateContent?key={self.api_key}"
        payload = {
            "contents": [{"parts": [{"text": request.prompt}]}],
            "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
        }
        resp = await self.client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        parts = data["candidates"][0]["content"]["parts"]
        image_url = next((p.get("text") or p.get("fileData", {}).get("fileUri", "")
                          for p in parts), "")
        return ImageGenerationResponse(data=[{"url": image_url, "prompt": request.prompt}])

    async def generate_video(
        self, request: VideoGenerationRequest
    ) -> VideoGenerationResponse:
        raise NotImplementedError("GeminiAdapter.generate_video — not yet implemented")

    async def create_embedding(
        self, request: EmbeddingRequest
    ) -> EmbeddingResponse:
        url = f"{self.base_url}/models/text-embedding-004:embedContent?key={self.api_key}"
        payload = {"model": "models/text-embedding-004",
                   "content": {"parts": [{"text": request.input}]}}
        resp = await self.client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        vector = data["embedding"]["values"]
        return EmbeddingResponse(data=[{"embedding": vector}])

    async def list_models(self) -> List[Model]:
        return [
            Model(id="gemini-2.5-flash", owned_by="google"),
            Model(id="gemini-2.5-pro", owned_by="google"),
            Model(id="gemini-2.0-flash-exp", owned_by="google"),
            Model(id="gemini-2.5-veo", owned_by="google"),
            Model(id="text-embedding-004", owned_by="google"),
        ]

    async def health_check(self) -> ProviderHealth:
        try:
            url = f"{self.base_url}/models?key={self.api_key}"
            resp = await self.client.get(url, timeout=10.0)
            resp.raise_for_status()
            return ProviderHealth(status=ProviderStatus.HEALTHY, latency_ms=0.0,
                                  last_check=0.0, error="")
        except Exception as exc:  # pragma: no cover
            return ProviderHealth(status=ProviderStatus.UNHEALTHY, latency_ms=0.0,
                                  last_check=0.0, error=str(exc))
