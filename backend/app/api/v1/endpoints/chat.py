from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import json
import time
import uuid

from app.core.config import settings
from app.services.provider_service import get_provider_registry
from providers.base import ChatCompletionRequest as AdapterChatRequest

router = APIRouter()


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    messages: List[ChatMessage]
    # Was hardcoded "gemini-2.5-flash" here and at two more places below. MEASURED 2026-08-24: the
    # gateway cannot resolve that name -- unnamespaced it maps to a cookie-auth provider and every
    # call dies on `[401]: No cookie auth credentials found`. Follow the configured default instead,
    # so one env var repoints chat and the agents together.
    model: Optional[str] = None
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = None
    stream: Optional[bool] = False


async def _complete(messages: List[Dict[str, str]], model: Optional[str] = None,
                    temperature: float = 0.7, max_tokens: Optional[int] = None) -> Dict[str, Any]:
    """Run one chat completion through the registry and return the raw envelope.

    Centralised because all three call sites below previously invoked the adapter with the WRONG
    SIGNATURE: `adapter.chat_completion(messages=..., model=..., stream=...)` as keyword arguments,
    when every adapter takes a single ChatCompletionRequest object. Nothing here ever worked --
    /chat/completions answered
    `'OpenRouterAdapter' object has no attribute 'provider_name'` (the attribute is the method
    get_provider_name()) and would have raised TypeError immediately after that was fixed.
    """
    registry = await get_provider_registry()
    try:
        adapter = await registry.get_adapter("chat")
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"No available chat provider: {e}")

    name = adapter.get_provider_name()
    req = AdapterChatRequest(
        model=model or settings.DEFAULT_CHAT_MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens or settings.AGENT_MAX_TOKENS,
    )
    started = time.time()
    try:
        resp = await adapter.chat_completion(req)
    except Exception as e:
        # report_failure takes `reason`, not `error`. Passing error= raised TypeError from inside
        # the exception handler, replacing the real provider error with a confusing one.
        registry.report_failure(name, reason=f"{type(e).__name__}: {e}")
        raise HTTPException(
            status_code=502,
            detail=f"Provider {name} error: {type(e).__name__}: {e}" if str(e)
            else f"Provider {name} error: {type(e).__name__}",
        )
    registry.report_success(name, latency_ms=(time.time() - started) * 1000)
    return resp if isinstance(resp, dict) else resp.model_dump()


def _content_of(envelope: Dict[str, Any]) -> str:
    choices = envelope.get("choices") or [{}]
    return (choices[0].get("message") or {}).get("content") or ""


@router.post("/completions")
async def create_chat_completion(request: ChatCompletionRequest):
    """Chat completion routed through free-tier ProviderRegistry."""
    return await _complete(
        [{"role": m.role, "content": m.content} for m in request.messages],
        model=request.model,
        temperature=request.temperature or 0.7,
        max_tokens=request.max_tokens,
    )


@router.get("/stream")
async def stream_chat(prompt: str, model: Optional[str] = None):
    """SSE streaming chat response for real-time frontend canvas interaction."""

    async def event_generator():
        try:
            envelope = await _complete([{"role": "user", "content": prompt}], model=model)
        except HTTPException as e:
            yield f"data: {json.dumps({'error': e.detail})}\n\n"
            return
        for word in _content_of(envelope).split(" "):
            yield f"data: {json.dumps({'delta': {'content': word + ' '}})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Session-backed chat, which is what the Chat Mode tab in the UI actually calls.
#
# src/app/components/ChatMode.tsx has always issued GET /api/v1/chat/sessions and
# POST /api/v1/chat/send {message, sessionId, mode}. Neither route existed, so every message in
# that tab 404'd -- the component swallows the session 404 with `catch { return [] }` and shows
# "Sorry, I encountered an error" for the send. Same in-process store as the pipeline routes use.
# ---------------------------------------------------------------------------
CREATIVE_DIRECTOR_PROMPT = (
    "You are the Director of a 7-agent animation studio: Scriptwriter, Art Director, "
    "Character Designer, Scene Designer, Storyboard Artist, Animator and Sound Director. "
    "Help the user shape a story idea into something the crew can film. Be concrete and brief."
)

chat_sessions: Dict[str, Dict[str, Any]] = {}


class ChatSendRequest(BaseModel):
    message: str
    sessionId: Optional[str] = None
    mode: Optional[str] = "chat"
    model: Optional[str] = None


@router.get("/sessions")
async def list_chat_sessions():
    """Sessions, newest first. Shape matches the ChatSession interface in ChatMode.tsx."""
    return sorted(
        (
            {
                "id": sid,
                "title": s["title"],
                "messages": s["messages"],
                "createdAt": s["createdAt"],
                "updatedAt": s["updatedAt"],
                "mode": s["mode"],
            }
            for sid, s in chat_sessions.items()
        ),
        key=lambda s: s["updatedAt"],
        reverse=True,
    )


@router.post("/send")
async def send_chat_message(request: ChatSendRequest):
    """Append a turn to a session and answer it with a real provider call.

    Returns {"content": ...} because that is the field ChatMode.tsx reads. "agentUpdates" is
    deliberately absent rather than faked: the component drives its progress bars from it, and
    this route does not run the 7 agents -- /projects/{id}/pipeline/run does.
    """
    sid = request.sessionId or uuid.uuid4().hex[:12]
    now = time.time()
    session = chat_sessions.setdefault(
        sid,
        {
            "title": request.message[:60] or "New chat",
            "messages": [],
            "createdAt": now,
            "updatedAt": now,
            "mode": request.mode or "chat",
        },
    )
    session["messages"].append({"role": "user", "content": request.message})
    session["updatedAt"] = now

    envelope = await _complete(
        [{"role": "system", "content": CREATIVE_DIRECTOR_PROMPT}]
        + [{"role": m["role"], "content": m["content"]} for m in session["messages"]],
        model=request.model,
    )
    content = _content_of(envelope)
    session["messages"].append({"role": "assistant", "content": content})
    session["updatedAt"] = time.time()

    return {
        "sessionId": sid,
        "content": content,
        "model": envelope.get("model", ""),
        "usage": envelope.get("usage", {}),
    }
