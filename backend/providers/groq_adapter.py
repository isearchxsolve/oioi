from __future__ import annotations
import asyncio
from typing import Any, AsyncGenerator, List, Dict
from groq import AsyncGroq
from pydantic import BaseModel, Field
import time
from providers.base import AIProviderAdapter, ProviderHealth, ProviderStatus
from models import ChatCompletionRequest, ChatCompletionResponse, ChatCompletionChunk, ImageGenerationRequest, ImageGenerationResponse, VideoGenerationRequest, VideoGenerationResponse, EmbeddingRequest, EmbeddingResponse, Model


class GroqAdapter(AIProviderAdapter):
    def __init__(self, api_key: str, base_url: str = 'https://api.groq.com/openai/v1'):
        self.client = AsyncGroq(api_key=api_key)  # Groq uses OpenAI-compatible API, base_url is default in AsyncGroq
        self.provider_name = 'groq'

    async def chat_completion(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        response = await self.client.chat.completions.create(**request.dict())
        return ChatCompletionResponse(**response.dict())

    async def chat_completion_stream(self, request: ChatCompletionRequest) -> AsyncGenerator[ChatCompletionChunk, None]:
        async for chunk in await self.client.chat.completions.create(stream=True, **request.dict()):
            yield ChatCompletionChunk(**chunk.dict())

    async def generate_image(self, request: ImageGenerationRequest) -> ImageGenerationResponse:
        # Groq does not have image generation; raise NotImplementedError
        raise NotImplementedError('Image generation not supported by Groq adapter')

    async def generate_video(self, request: VideoGenerationRequest) -> VideoGenerationResponse:
        raise NotImplementedError('Video generation not supported by Groq adapter')

    async def create_embedding(self, request: EmbeddingRequest) -> EmbeddingResponse:
        # Groq does not have embeddings endpoint; using OpenAI compatible embeddings if available
        try:
            response = await self.client.embeddings.create(**request.dict())
            return EmbeddingResponse(**response.dict())
        except Exception:
            raise NotImplementedError('Embedding not supported by Groq adapter')

    async def list_models(self) -> List[Model]:
        models = await self.client.models.list()
        return [Model(**m.dict()) for m in models.data]

    async def health_check(self) -> ProviderHealth:
        try:
            start = time.time()
            await self.client.models.list()
            latency = (time.time() - start) * 1000
            return ProviderHealth(status=ProviderStatus.HEALTHY, latency_ms=latency, last_check=time.time(), error='')
        except Exception as e:
            return ProviderHealth(status=ProviderStatus.UNHEALTHY, latency_ms=0.0, last_check=time.time(), error=str(e))

    def get_provider_name(self) -> str:
        return self.provider_name