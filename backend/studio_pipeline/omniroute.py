"""OmniRoute gateway client: frontier-model JSON generation + video clip generation.

Measured behaviour of the local OmniRoute gateway (see MASTER_WORKLOG STAGE 0) that
this client is built around:

* ``POST /v1/chat/completions`` works and takes ~10s for a trivial prompt, so every
  default timeout here is generous and every call is retried with backoff.
* Responses carry both ``content`` and ``reasoning_content``. Only ``content`` is the
  answer; reading the wrong one yields the model's scratchpad.
* ``stream`` must be sent explicitly as ``false``.
* There is currently **no working video route**: ``/v1/videos`` returns
  ``404 unknown_route`` and ``/v1/videos/generations`` accepts the TCP connection then
  never answers. :meth:`OmniRouteClient.probe_video` detects this with a short timeout
  and caches the verdict, so the Animator degrades cleanly instead of hanging for hours.
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

DEFAULT_BASE_URL = "http://127.0.0.1:20128/v1"
DEFAULT_MODEL = "frontier"

#: Routes tried by :meth:`OmniRouteClient.probe_video`, best-guess first.
VIDEO_ROUTE_CANDIDATES = (
    "/videos/generations",
    "/video/generations",
    "/videos",
    "/images/generations",
)


class OmniRouteError(RuntimeError):
    """Raised when the gateway cannot satisfy a request after all retries."""


class OmniRouteJSONError(OmniRouteError):
    """The gateway answered, but the payload was not recoverable JSON."""


@dataclass
class VideoCapability:
    available: bool
    route: Optional[str]
    model: Optional[str]
    detail: str
    checked_at: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "available": self.available,
            "route": self.route,
            "model": self.model,
            "detail": self.detail,
            "checked_at": self.checked_at,
        }


_FENCE_RE = re.compile(r"^\s*```(?:json|JSON)?\s*|\s*```\s*$")
_TRAILING_COMMA_RE = re.compile(r",(\s*[}\]])")


def extract_json(text: str) -> Any:
    """Best-effort recovery of a JSON value from a chatty LLM response.

    Frontier models wrap JSON in prose or fences even under instruction. In order:
    parse as-is, strip code fences, slice the outermost brace/bracket pair, then drop
    trailing commas. Raises :class:`OmniRouteJSONError` if nothing parses.
    """
    if not text or not text.strip():
        raise OmniRouteJSONError("empty response body")

    candidates: List[str] = []
    raw = text.strip()
    candidates.append(raw)

    unfenced = _FENCE_RE.sub("", raw).strip()
    if unfenced != raw:
        candidates.append(unfenced)

    for opener, closer in (("{", "}"), ("[", "]")):
        start = unfenced.find(opener)
        end = unfenced.rfind(closer)
        if start != -1 and end > start:
            candidates.append(unfenced[start : end + 1])

    for cand in list(candidates):
        candidates.append(_TRAILING_COMMA_RE.sub(r"\1", cand))

    for cand in candidates:
        try:
            return json.loads(cand)
        except json.JSONDecodeError:
            continue

    preview = raw[:400].replace("\n", " ")
    raise OmniRouteJSONError(f"no parseable JSON in response; got: {preview!r}")


class OmniRouteClient:
    """Async client for the OmniRoute OpenAI-compatible gateway.

    One instance is shared by every agent in a run. It owns a single
    :class:`httpx.AsyncClient` with a connection pool, because a 3-hour render makes
    hundreds of calls and per-call clients would exhaust ephemeral ports on Windows.
    """

    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        video_model: Optional[str] = None,
        video_route: Optional[str] = None,
        request_timeout: float = 300.0,
        max_retries: int = 4,
    ) -> None:
        self.base_url = (
            base_url
            or os.getenv("OMNIROUTE_BASE_URL")
            or os.getenv("OPENROUTER_API_BASE_URL")
            or os.getenv("OPENAI_API_BASE")
            or DEFAULT_BASE_URL
        ).rstrip("/")
        self.api_key = api_key or os.getenv("OMNIROUTE_API_KEY") or os.getenv("OPENROUTER_API_KEY") or "sk-omniroute"
        self.model = model or os.getenv("OMNIROUTE_MODEL") or DEFAULT_MODEL
        self.video_model = video_model or os.getenv("OMNIROUTE_VIDEO_MODEL") or "pollinations/p-video"
        self.configured_video_route = video_route or os.getenv("OMNIROUTE_VIDEO_PATH") or None
        self.request_timeout = float(os.getenv("OMNIROUTE_TIMEOUT", request_timeout))
        self.max_retries = max_retries

        self._client: Optional[httpx.AsyncClient] = None
        self._client_lock = asyncio.Lock()
        self._video_cap: Optional[VideoCapability] = None
        self._video_lock = asyncio.Lock()
        #: Cumulative token usage across the run — surfaced in progress events.
        self.usage: Dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0}

    # --------------------------------------------------------------- plumbing
    async def _http(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            async with self._client_lock:
                if self._client is None or self._client.is_closed:
                    self._client = httpx.AsyncClient(
                        timeout=httpx.Timeout(
                            connect=10.0,
                            read=self.request_timeout,
                            write=60.0,
                            pool=30.0,
                        ),
                        limits=httpx.Limits(max_connections=16, max_keepalive_connections=8),
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                        },
                    )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    async def __aenter__(self) -> "OmniRouteClient":
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        await self.aclose()

    @staticmethod
    def _backoff(attempt: int) -> float:
        """Exponential backoff with full jitter, capped at 30s."""
        return min(30.0, (2.0**attempt)) * (0.5 + random.random() / 2.0)

    # ------------------------------------------------------------------- chat
    async def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        model: Optional[str] = None,
        temperature: float = 0.8,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
        timeout: Optional[float] = None,
    ) -> str:
        """One completion, retried on transport errors and 5xx/429. Returns ``content``."""
        payload: Dict[str, Any] = {
            "model": model or self.model,
            "stream": False,  # OmniRoute requires this explicitly
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        client = await self._http()
        url = f"{self.base_url}/chat/completions"
        last_error: Optional[str] = None

        for attempt in range(self.max_retries):
            try:
                resp = await client.post(
                    url,
                    json=payload,
                    timeout=timeout or self.request_timeout,
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
            else:
                if resp.status_code in (429, 500, 502, 503, 504):
                    last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                elif resp.status_code >= 400:
                    # 4xx other than 429 are deterministic — retrying wastes minutes.
                    raise OmniRouteError(f"HTTP {resp.status_code} from {url}: {resp.text[:400]}")
                else:
                    try:
                        data = resp.json()
                    except json.JSONDecodeError as exc:
                        last_error = f"non-JSON envelope: {exc}"
                    else:
                        usage = data.get("usage") or {}
                        self.usage["prompt_tokens"] += int(usage.get("prompt_tokens", 0) or 0)
                        self.usage["completion_tokens"] += int(usage.get("completion_tokens", 0) or 0)
                        self.usage["calls"] += 1
                        choices = data.get("choices") or []
                        if not choices:
                            last_error = f"no choices in envelope: {str(data)[:200]}"
                        else:
                            msg = choices[0].get("message") or {}
                            # Deliberately ignore `reasoning_content`: it is the model's
                            # scratchpad, not the answer.
                            content = msg.get("content")
                            if content:
                                return str(content)
                            last_error = "empty content (only reasoning_content returned)"

            if attempt < self.max_retries - 1:
                await asyncio.sleep(self._backoff(attempt))

        raise OmniRouteError(f"chat failed after {self.max_retries} attempts: {last_error}")

    async def chat_json(
        self,
        messages: List[Dict[str, str]],
        *,
        model: Optional[str] = None,
        temperature: float = 0.8,
        max_tokens: Optional[int] = None,
        repair_attempts: int = 2,
        timeout: Optional[float] = None,
    ) -> Any:
        """Completion whose result must be JSON, with an explicit repair round-trip.

        If the model returns unparseable output the failure is fed back to it verbatim
        with an instruction to emit JSON only — far cheaper than regenerating from the
        original prompt, and it usually succeeds on the first repair.
        """
        convo = list(messages)
        last_exc: Optional[Exception] = None

        for attempt in range(repair_attempts + 1):
            raw = await self.chat(
                convo,
                model=model,
                temperature=temperature if attempt == 0 else min(temperature, 0.3),
                max_tokens=max_tokens,
                json_mode=True,
                timeout=timeout,
            )
            try:
                return extract_json(raw)
            except OmniRouteJSONError as exc:
                last_exc = exc
                if attempt >= repair_attempts:
                    break
                convo = list(messages) + [
                    {"role": "assistant", "content": raw[:4000]},
                    {
                        "role": "user",
                        "content": (
                            "That was not valid JSON and could not be parsed. "
                            "Reply again with the SAME content as a single valid JSON object. "
                            "Output JSON only: no prose, no markdown fences, no trailing commas."
                        ),
                    },
                ]

        raise OmniRouteJSONError(f"could not obtain JSON after {repair_attempts + 1} attempts: {last_exc}")

    # ------------------------------------------------------------------ health
    async def probe_chat(self, *, timeout: float = 45.0) -> Dict[str, Any]:
        """Cheap liveness check for the text path."""
        started = time.time()
        try:
            content = await self.chat(
                [{"role": "user", "content": "Reply with the single word: ok"}],
                temperature=0.0,
                max_tokens=16,
                timeout=timeout,
            )
        except Exception as exc:  # noqa: BLE001 — a probe reports, it does not raise
            return {
                "available": False,
                "latency_ms": round((time.time() - started) * 1000, 1),
                "detail": f"{type(exc).__name__}: {exc}",
            }
        return {
            "available": True,
            "latency_ms": round((time.time() - started) * 1000, 1),
            "detail": content.strip()[:80],
        }

    async def probe_video(self, *, force: bool = False, timeout: float = 8.0) -> VideoCapability:
        """Find a working video route, cached for the life of the client.

        The timeout is deliberately short: one candidate route accepts the TCP
        connection and then never responds, and a 3-hour render cannot afford to
        rediscover that per scene.
        """
        async with self._video_lock:
            if self._video_cap is not None and not force:
                return self._video_cap

            routes = (
                [self.configured_video_route]
                if self.configured_video_route
                else list(VIDEO_ROUTE_CANDIDATES)
            )
            client = await self._http()
            findings: List[str] = []

            for route in routes:
                if not route:
                    continue
                url = f"{self.base_url}{route if route.startswith('/') else '/' + route}"
                payload = {
                    "model": self.video_model,
                    "prompt": "a single still frame of a grey test card",
                    "n": 1,
                }
                try:
                    resp = await client.post(url, json=payload, timeout=timeout)
                except httpx.TimeoutException:
                    findings.append(f"{route}: no HTTP response within {timeout:g}s (route hangs)")
                    continue
                except httpx.TransportError as exc:
                    findings.append(f"{route}: {type(exc).__name__}")
                    continue

                if resp.status_code < 300:
                    self._video_cap = VideoCapability(
                        available=True,
                        route=route,
                        model=self.video_model,
                        detail=f"HTTP {resp.status_code}",
                        checked_at=time.time(),
                    )
                    return self._video_cap
                if resp.status_code in (401, 403):
                    findings.append(
                        f"{route}: HTTP {resp.status_code} — gateway reached but upstream "
                        f"credential missing ({resp.text[:120]})"
                    )
                else:
                    findings.append(f"{route}: HTTP {resp.status_code} ({resp.text[:120]})")

            self._video_cap = VideoCapability(
                available=False,
                route=None,
                model=self.video_model,
                detail="; ".join(findings) or "no candidate routes configured",
                checked_at=time.time(),
            )
            return self._video_cap

    # ------------------------------------------------------------------- video
    async def generate_video(
        self,
        prompt: str,
        *,
        duration_seconds: int = 10,
        aspect_ratio: str = "16:9",
        first_frame_url: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> str:
        """Ask OmniRoute for one clip and return a fetchable URL.

        Raises :class:`OmniRouteError` when no video route is available, which is the
        signal for the Animator to fall back to local synthesis.
        """
        cap = await self.probe_video()
        if not cap.available or not cap.route:
            raise OmniRouteError(f"no OmniRoute video route available: {cap.detail}")

        payload: Dict[str, Any] = {
            "model": self.video_model,
            "prompt": prompt,
            "n": 1,
            "duration": duration_seconds,
            "aspect_ratio": aspect_ratio,
        }
        if first_frame_url:
            payload["image"] = first_frame_url

        client = await self._http()
        url = f"{self.base_url}{cap.route}"
        last_error: Optional[str] = None

        for attempt in range(self.max_retries):
            try:
                resp = await client.post(url, json=payload, timeout=timeout or self.request_timeout)
                if resp.status_code in (429, 500, 502, 503, 504):
                    last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                elif resp.status_code >= 400:
                    raise OmniRouteError(f"HTTP {resp.status_code} from {url}: {resp.text[:300]}")
                else:
                    found = self._find_media_url(resp.json())
                    if found:
                        return found
                    last_error = f"no url/b64 in response: {resp.text[:200]}"
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
            except json.JSONDecodeError as exc:
                last_error = f"non-JSON response: {exc}"

            if attempt < self.max_retries - 1:
                await asyncio.sleep(self._backoff(attempt))

        raise OmniRouteError(f"video generation failed after {self.max_retries} attempts: {last_error}")

    @staticmethod
    def _find_media_url(payload: Any) -> Optional[str]:
        """Pull the first http(s) media URL out of an arbitrarily shaped envelope.

        Providers disagree on schema (``data[0].url``, ``output[0]``, ``video_url``,
        ``assets.video``…), so search rather than assume.
        """
        keys = ("url", "video_url", "videoUrl", "uri", "output_url", "download_url", "signed_url")

        def walk(node: Any, depth: int = 0) -> Optional[str]:
            if depth > 8:
                return None
            if isinstance(node, str):
                return node if node.startswith(("http://", "https://")) else None
            if isinstance(node, dict):
                for k in keys:
                    v = node.get(k)
                    if isinstance(v, str) and v.startswith(("http://", "https://")):
                        return v
                for v in node.values():
                    found = walk(v, depth + 1)
                    if found:
                        return found
                return None
            if isinstance(node, (list, tuple)):
                for v in node:
                    found = walk(v, depth + 1)
                    if found:
                        return found
            return None

        return walk(payload)


__all__ = [
    "OmniRouteClient",
    "OmniRouteError",
    "OmniRouteJSONError",
    "VideoCapability",
    "VIDEO_ROUTE_CANDIDATES",
    "extract_json",
]
