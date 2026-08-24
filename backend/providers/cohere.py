from __future__ import annotations
import asyncio
from typing import Any, AsyncGenerator, List, Dict
from pydantic import BaseModel, Field
import time
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

try:
    import cohere  # type: ignore
except ImportError:
    cohere = None  # type: ignore


class CohereAdapter(AIProviderAdapter):
    def __init__(self, api_key: str):
        global cohere
        if cohere is None:  # type: ignore
            try:
                import cohere as _cohere  # type: ignore
                cohere = _cohere  # type: ignore
            except ImportError:
                raise ImportError(
                    "cohere package is required for CohereAdapter; install with `pip install cohere`"
                )
        self.client = cohere.AsyncClient(api_key=api_key)  # type: ignore
        self.provider_name = 'cohere'

    async def chat_completion(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        # Cohere uses generate endpoint, not chat/completions exactly. We'll adapt.
        # For simplicity, we assume the last user message is the prompt.
        # In a real implementation, we would properly format chat history.
        prompt = ''
        for msg in request.messages:
            if msg['role'] == 'user':
                prompt += msg['content'] + ' '
            elif msg['role'] == 'assistant':
                prompt += msg['content'] + ' '
            elif msg['role'] == 'system':
                prompt = msg['content'] + ' ' + prompt
        # Cohere's generate method
        response = await self.client.generate(
            prompt=prompt.strip(),
            model=request.model or 'command',
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            k=0,
            p=0.75,
            stop_sequences=[],
            return_likelihoods=None)
        # Convert to OpenAI-like response
        text = response.generations[0].text if response.generations else ''
        response_obj = ChatCompletionResponse(
            id=f'cohere-{response.generation_id}',
            object='chat.completion',
            created=int(time.time()),
            model=request.model or 'command',
            choices=[{'index': 0, 'message': {'role': 'assistant', 'content': text}, 'finish_reason': 'stop'}],
            usage={'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0})
        return response_obj

    async def chat_completion_stream(self, request: ChatCompletionRequest) -> AsyncGenerator[ChatCompletionChunk, None]:
        # Cohere streaming not implemented for simplicity; fallback to non-stream
        resp = await self.chat_completion(request)
        for choice in resp.choices:
            yield ChatCompletionChunk(
                id=resp.id,
                object='chat.completion.chunk',
                created=resp.created,
                model=resp.model,
                choices=[{'index': 0, 'delta': {'role': 'assistant', 'content': choice.message['content']}, 'finish_reason': choice.finish_reason}])

    async def generate_image(self, request: ImageGenerationRequest) -> ImageGenerationResponse:
        raise NotImplementedError('Image generation not supported by Cohere adapter')

    async def generate_video(self, request: VideoGenerationRequest) -> VideoGenerationResponse:
        raise NotImplementedError('Video generation not supported by Cohere adapter')

    async def create_embedding(self, request: EmbeddingRequest) -> EmbeddingResponse:
        # Cohere embed endpoint
        response = await self.client.embed(
            texts=[request.input] if isinstance(request.input, str) else request.input,
            model=request.model or 'embed-english-v3.0',
            input_type='search_document')
        embeddings = response.embeddings
        response_obj = EmbeddingResponse(
            object='list',
            data=[{'embedding': emb, 'index': i} for i, emb in enumerate(embeddings)],
            model=request.model or 'embed-english-v3.0',
            usage={'prompt_tokens': 0, 'total_tokens': 0})
        return response_obj

    async def list_models(self) -> List[Model]:
        # Cohere does not have a models list endpoint; we return a static list
        return [
            Model(id='command', object='model', created=0, owned_by='Cohere'),
            Model(id='command-light', object='model', created=0, owned_by='Cohere'),
            Model(id='embed-english-v3.0', object='model', created=0, owned_by='Cohere'),
            Model(id='embed-multilingual-v3.0', object='model', created=0, owned_by='Cohere')]

    async def health_check(self) -> ProviderHealth:
        try:
            start = time.time()
            # Use a minimal embed call to check connectivity
            await self.client.embed(['test'], model='embed-english-v3.0', input_type='search_document')
            latency = (time.time() - start) * 1000
            return ProviderHealth(status=ProviderStatus.HEALTHY, latency_ms=latency, last_check=time.time(), error='')
        except Exception as e:
            return ProviderHealth(status=ProviderStatus.UNHEALTHY, latency_ms=0.0, last_check=time.time(), error=str(e))

    def get_provider_name(self) -> str:
        return self.provider_name