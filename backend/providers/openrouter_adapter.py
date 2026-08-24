"""OpenRouter adapter — free-tier AI provider (OpenAI-compatible API).

Base URL: https://openrouter.ai/api/v1
Implements the AIProviderAdapter interface. NVIDIA NIM is NOT used.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Shared request/response contracts (also used by other adapters)
# ---------------------------------------------------------------------------
class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[Dict[str, Any]]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = None
    stream: bool = False
    # MEASURED 2026-08-24: all 8 orchestrator call sites already pass
    # response_format={"type": "json_object"}, but this field did not exist -- pydantic's default
    # `extra="ignore"` DROPPED it silently, so model_dump() never put it on the wire and no agent
    # ever actually ran in JSON mode. The Scriptwriter then emitted a `scenes` array whose first
    # element was missing its opening brace and _parse_json died on
    # `Expecting ',' delimiter: line 9 column 18`. With json_object genuinely sent, the same model
    # returned valid 3-scene JSON first try. Silently ignoring a caller's argument is the worst
    # failure mode available: the code reads as if the feature is on.
    response_format: Optional[Dict[str, Any]] = None


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[Dict[str, Any]]
    usage: Dict[str, Any]


class ChatCompletionChunk(BaseModel):
    id: str
    object: str = "chat.completion.chunk"
    created: int
    model: str
    choices: List[Dict[str, Any]]


class ImageGenerationRequest(BaseModel):
    prompt: str
    model: str
    n: int = 1
    size: str = "1024x1024"
    response_format: str = "url"


class ImageGenerationResponse(BaseModel):
    created: int
    data: List[Dict[str, Any]]


class VideoGenerationRequest(BaseModel):
    prompt: str
    model: str
    first_frame: Optional[str] = None
    last_frame: Optional[str] = None


class VideoGenerationResponse(BaseModel):
    created: int
    data: List[Dict[str, Any]]


class EmbeddingRequest(BaseModel):
    input: Any
    model: str


class EmbeddingResponse(BaseModel):
    object: str = "list"
    data: List[Dict[str, Any]]
    model: str
    usage: Dict[str, int]


class Model(BaseModel):
    id: str
    object: str = "model"
    created: int = 0
    owned_by: str = ""


# ---------------------------------------------------------------------------
# Unified adapter interface
# ---------------------------------------------------------------------------
RETRY_STATUS = {429, 500, 502, 503, 504}
MAX_RETRIES = 5


def backoff(attempt: int) -> float:
    """Exponential backoff with jitter, capped at 30s."""
    return min(30.0, 0.5 * (2 ** attempt))


def _error_message(resp: "httpx.Response") -> str:
    """The upstream's own explanation for a failure, or the body, or the status line.

    The gateway answers `{"error": {"message": "..."}}` and that message is the only place the
    real cause appears -- e.g. "All antigravity accounts have exhausted their quota (reset after
    2h 34m 38s)" or "No active credentials for provider: openai". httpx's raise_for_status()
    discards the body entirely, which is how a hard quota wall came back looking like a transient
    "429 Too Many Requests".
    """
    try:
        payload = resp.json()
    except ValueError:
        return (resp.text or "").strip()[:400] or f"HTTP {resp.status_code}"
    err = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(err, dict):
        return str(err.get("message") or err)[:400]
    if err:
        return str(err)[:400]
    return str(payload)[:400]


# Phrases the gateway uses when waiting cannot help: the quota is spent for hours, or there is no
# credential to spend at all. Retrying these wastes the caller's time and hides the real message.
_UNRECOVERABLE = (
    "exhausted their quota",
    "exhausted quota",
    "no active credentials",
    "insufficient_quota",
    "quota exceeded",
)


def _quota_exhausted(detail: str) -> bool:
    low = (detail or "").lower()
    return any(p in low for p in _UNRECOVERABLE)


def _retry_delay(resp: "httpx.Response", attempt: int) -> float:
    """Honour Retry-After when the upstream sends one, else exponential backoff."""
    ra = resp.headers.get("Retry-After")
    if ra:
        try:
            return max(0.0, min(60.0, float(ra)))
        except ValueError:
            pass
    return backoff(attempt)


def sse_to_completion(raw: str) -> Optional[Dict[str, Any]]:
    """Collapse an SSE chat-completion stream into the non-streaming envelope shape.

    MEASURED 2026-08-24 against the local OmniRoute gateway: it replies with server-sent events
    even when the request does NOT set "stream": true. `httpx.Response.json()` on that body raises
    `Expecting value: line 1 column 1 (char 0)`, which is indistinguishable at a glance from a dead
    provider -- a whole model benchmark scored three WORKING models as failures because of it. Real
    models affected: gemini-3.6-flash-high, auto/best-reasoning, auto/best-coding, morph-v3-fast.

    Returns None when the body is not SSE, so the caller can report the original parse failure
    rather than a misleading one.
    """
    if "data:" not in raw:
        return None
    content: List[str] = []
    reasoning: List[str] = []
    finish: Optional[str] = None
    usage: Optional[Dict[str, Any]] = None
    model_id: Optional[str] = None
    cid: Optional[str] = None
    created = 0
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            chunk = json.loads(payload)
        except ValueError:
            continue  # a partial frame; the next one carries the rest
        model_id = chunk.get("model") or model_id
        cid = chunk.get("id") or cid
        created = chunk.get("created") or created
        # usage and finish_reason arrive on TRAILING chunks, so keep overwriting rather than
        # breaking out on the first one that appears.
        usage = chunk.get("usage") or usage
        for ch in chunk.get("choices") or []:
            delta = ch.get("delta") or {}
            if delta.get("content"):
                content.append(delta["content"])
            if delta.get("reasoning_content"):
                reasoning.append(delta["reasoning_content"])
            if ch.get("finish_reason"):
                finish = ch["finish_reason"]
    message: Dict[str, Any] = {"role": "assistant", "content": "".join(content)}
    if reasoning:
        # Kept separate on purpose. Concatenating a thinking model's scratchpad into `content`
        # would hand the agents' json.loads() a wall of prose wrapped around the JSON.
        message["reasoning_content"] = "".join(reasoning)
    return {
        "id": cid or "sse-reassembled",
        "object": "chat.completion",
        "created": created,
        "model": model_id or "",
        "choices": [{"index": 0, "finish_reason": finish, "message": message}],
        "usage": usage or {},
    }


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
    def get_provider_name(self) -> str:
        ...


# ---------------------------------------------------------------------------
# OpenRouter implementation
# ---------------------------------------------------------------------------
class OpenRouterAdapter(AIProviderAdapter):
    def __init__(self, api_key: str, base_url: str = "https://openrouter.ai/api/v1") -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "HTTP-Referer": "https://oioii.ai",
                "X-Title": "OiiOii.ai Clone",
            },
            # MEASURED 2026-08-24: 60s is not enough for this workload and the failure is silent.
            # The film crew asks for up to AGENT_MAX_TOKENS (4096) of strict JSON from a *thinking*
            # model, which routinely runs past a minute. httpx then raises ReadTimeout, whose str()
            # is EMPTY -- so the pipeline reported literally "Animator execution error:" with no
            # cause, after 497 seconds. Configurable, and generous by default: a slow answer is
            # still an answer, whereas a timeout throws away everything the model already generated.
            timeout=float(os.getenv("CHAT_TIMEOUT_SECONDS", "300")),
        )

    async def _request_with_retry(self, method: str, path: str, json: Optional[dict] = None) -> httpx.Response:
        last_exc: Optional[Exception] = None
        for attempt in range(MAX_RETRIES):
            try:
                resp = await self.client.request(method, path, json=json)
                if resp.status_code in RETRY_STATUS and attempt < MAX_RETRIES - 1:
                    # MEASURED 2026-08-24: a 7-agent run died on agent 2 with
                    # "Client error '429 Too Many Requests'" after burning 34s on retries. The
                    # gateway had actually answered
                    #   [antigravity/gemini-3.6-flash-high] All antigravity accounts have exhausted
                    #   their quota (reset after 2h 34m 38s)
                    # -- so the retries could never succeed (total backoff here is ~7.5s against a
                    # 2.5 HOUR window) and the one piece of actionable information was thrown away,
                    # because raise_for_status() renders only the status line. Give up immediately
                    # when the gateway says the quota is gone, and carry its wording into the error.
                    detail = _error_message(resp)
                    if _quota_exhausted(detail):
                        raise httpx.HTTPStatusError(
                            f"{resp.status_code} from {path}: {detail}",
                            request=resp.request, response=resp,
                        )
                    await asyncio.sleep(_retry_delay(resp, attempt))
                    continue
                if resp.status_code >= 400:
                    # Same reason: keep the upstream's own explanation rather than "Client error 429".
                    raise httpx.HTTPStatusError(
                        f"{resp.status_code} from {path}: {_error_message(resp)}",
                        request=resp.request, response=resp,
                    )
                return resp
            except httpx.HTTPStatusError:
                raise  # already carries the gateway's message; retrying is decided above
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(backoff(attempt))
                    continue
                raise
        raise last_exc  # type: ignore[misc]

    async def chat_completion(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        # exclude_none so a request that never set response_format does not transmit
        # "response_format": null, which some upstreams reject outright.
        resp = await self._request_with_retry(
            "POST", "/chat/completions", request.model_dump(exclude_none=True)
        )
        try:
            payload = resp.json()
        except ValueError:
            # The gateway force-streams some models regardless of `stream`. See sse_to_completion:
            # without this, every one of those models looks like a hard failure to all 7 agents.
            payload = sse_to_completion(resp.text)
            if payload is None:
                raise
        return ChatCompletionResponse(**payload)

    async def chat_completion_stream(
        self, request: ChatCompletionRequest
    ) -> AsyncGenerator[ChatCompletionChunk, None]:
        async with self.client.stream(
            "POST", "/chat/completions", json=request.model_dump()
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data.strip() == "[DONE]":
                        break
                    yield ChatCompletionChunk.model_validate_json(data)

    async def generate_image(self, request: ImageGenerationRequest) -> ImageGenerationResponse:
        resp = await self._request_with_retry("POST", "/images/generations", request.model_dump())
        return ImageGenerationResponse(**resp.json())

    async def generate_video(self, request: VideoGenerationRequest) -> VideoGenerationResponse:
        resp = await self._request_with_retry("POST", "/videos/generations", request.model_dump())
        return VideoGenerationResponse(**resp.json())

    async def create_embedding(self, request: EmbeddingRequest) -> EmbeddingResponse:
        resp = await self._request_with_retry("POST", "/embeddings", request.model_dump())
        return EmbeddingResponse(**resp.json())

    async def list_models(self) -> List[Model]:
        resp = await self._request_with_retry("GET", "/models")
        data = resp.json()
        return [Model(**m) for m in data.get("data", [])]

    def get_provider_name(self) -> str:
        return "openrouter"
