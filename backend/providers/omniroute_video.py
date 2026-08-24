"""OmniRoute video adapter — real clips from Google Flow and rtst.ai.

This is the only adapter in this package that produces a video file that actually exists.
Before it, `capability="video"` resolved to GeminiAdapter.generate_video, which is a bare
`raise NotImplementedError`, and app/api/v1/endpoints/videos.py swallowed that in a blanket
`except Exception: pass` and returned

    https://cdn.pollinations.ai/video/clip_<prompt>.mp4   with "status": "completed"

MEASURED 2026-08-24: that host does not resolve at all (getaddrinfo failed). So the endpoint has
been reporting success while handing back a URL that has never once been a video.

It talks to the OmniRoute video router, a local process that drives real signed-in browser
sessions rather than an API key -- which is the point: no key exists for Flow, and the credits
are already bought. The router runs on this machine, loopback only, and answers the same
POST /v1/videos/generations shape OpenRouterAdapter already speaks.

CREDITS ARE REAL MONEY. Every successful generate_video() call spends from a finite balance
(measured 2026-08-24: flow 930, rtst 18). Three consequences are deliberate here:

  * quote first, always. /v1/videos/quote is free and, on rtst, exact. The router refuses to
    exceed its own per-request ceiling, but this adapter checks too, because a 402 after the
    money is gone is not a useful error.
  * no retry on a submitted job. The registry's fallback machinery retries failed adapters;
    a retried video submit would spend twice for one clip. Everything that can fail is made to
    fail BEFORE the submit.
  * is_configured() is a live probe, not a key check. The router is either up with a signed-in
    account or it is not, and only /healthz knows.

One provider constraint worth knowing when building the UI: MEASURED 2026-08-24, rtst.ai rejects
a prompt shorter than 10 words. The router reports that as a free `error` on the quote, so this
adapter raises before spending rather than after -- but a one-word prompt from the app will fail,
and it should fail loudly there rather than be padded silently here.
"""
from __future__ import annotations

import logging
import time
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx

from providers.base import (
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

logger = logging.getLogger(__name__)

# The router's direct face. 8189 is the honest one: it reports real job state and real costs.
# 8188 wears a ComfyUI costume for tools that only speak ComfyUI, and is not what we want here.
#
# Configured via OMNIROUTE_VIDEO_BASE_URL, never OMNIROUTE_BASE_URL. That second name belongs to
# studio_pipeline/omniroute.py's LLM gateway on :20128, whose probe_video() looks for a video route
# by POSTing a real generation request -- so pointing that name here would make a capability probe
# spend 20 credits and then abandon the job on an 8s timeout.
DEFAULT_BASE_URL = "http://127.0.0.1:8189"

# Generation is slow by nature -- a Flow clip took 71s and an rtst clip 66s in testing, and both
# providers queue. This is the ceiling for one waited request, not an expectation.
GENERATE_TIMEOUT = 900.0


class OmniRouteVideoAdapter(AIProviderAdapter):
    """Video-only adapter. Every non-video capability raises, on purpose."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        api_key: str = "",
        max_credits: int = 25,
        timeout: float = GENERATE_TIMEOUT,
    ) -> None:
        self.provider_name = "omniroute_video"
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        # A ceiling this adapter enforces itself, above and beyond the router's own. Nothing in the
        # app's request shape names a price, so an operator's only defence against a model that
        # quietly costs 10x is a number they can set in one place.
        self.max_credits = max_credits
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self.client = httpx.AsyncClient(base_url=self.base_url, headers=headers, timeout=timeout)

    def get_provider_name(self) -> str:
        return self.provider_name

    # ---------------------------------------------------------------- health / config
    def is_configured(self) -> bool:
        """True when the router answers and at least one account is signed in and ready.

        Synchronous on purpose: provider_service._has_key() is a sync gate, so this has to answer
        there too. It uses a short-lived blocking client rather than the async one -- calling this
        from inside a running loop must not deadlock.
        """
        try:
            with httpx.Client(timeout=5.0) as c:
                r = c.get(f"{self.base_url}/healthz", headers=self._auth_headers())
                r.raise_for_status()
                accounts = r.json().get("accounts") or []
            return any(a.get("ready") for a in accounts)
        except Exception:
            return False

    def _auth_headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    async def health_check(self) -> ProviderHealth:
        t0 = time.monotonic()
        try:
            r = await self.client.get("/healthz", timeout=10.0)
            r.raise_for_status()
            body = r.json()
            latency = (time.monotonic() - t0) * 1000.0
            ready = [a for a in (body.get("accounts") or []) if a.get("ready")]
            if not ready:
                return ProviderHealth(
                    status=ProviderStatus.DEGRADED,
                    latency_ms=latency,
                    last_check=time.time(),
                    error="router is up but no account is signed in "
                          "(run: python video_router.py doctor)",
                )
            return ProviderHealth(
                status=ProviderStatus.HEALTHY, latency_ms=latency, last_check=time.time()
            )
        except Exception as exc:  # noqa: BLE001
            return ProviderHealth(
                status=ProviderStatus.UNHEALTHY,
                latency_ms=(time.monotonic() - t0) * 1000.0,
                last_check=time.time(),
                error=f"{type(exc).__name__}: {exc}",
            )

    async def list_models(self) -> List[Model]:
        """Ask the router which models its signed-in accounts can actually reach.

        MEASURED: the router names the field "model", not "id" -- its /v1/models is not an
        OpenAI-shaped models list, it is a catalogue carrying est_cost, proven, aspects and
        length_seconds per entry. Only the id is kept here because that is all Model holds.

        It also carries one row per (model, quality, audio) combination, so the raw list repeats
        veo_3_1_t2v_fast five times and vidu four times. Those rows differ only in fields Model
        cannot express, so they are collapsed -- a model picker should not offer the same name five
        times. First occurrence wins, which keeps the router's own ordering.

        Falls back to the two proven names if the router is down, so a model picker still renders
        something truthful rather than an empty list.
        """
        try:
            r = await self.client.get("/v1/models", timeout=15.0)
            r.raise_for_status()
            data = r.json().get("data") or []
            seen: set[str] = set()
            models: List[Model] = []
            for m in data:
                mid = m.get("model")
                if not mid or mid in seen:
                    continue
                seen.add(mid)
                models.append(Model(id=mid, owned_by=m.get("provider") or "omniroute"))
            if models:
                return models
        except Exception as exc:  # noqa: BLE001
            logger.warning("omniroute_video: /v1/models unavailable (%s); using proven defaults", exc)
        return [
            Model(id="veo_3_1_t2v_fast", owned_by="flow"),
            Model(id="vidu", owned_by="rtst"),
        ]

    # ---------------------------------------------------------------- the money path
    async def quote(self, request: VideoGenerationRequest) -> Dict[str, Any]:
        """Free. Returns the router's cost estimate without committing anything."""
        r = await self.client.post("/v1/videos/quote", json=self._payload(request), timeout=60.0)
        r.raise_for_status()
        return r.json()

    def _payload(self, request: VideoGenerationRequest) -> Dict[str, Any]:
        """Map the app's request onto the router's wire shape.

        VideoGenerationRequest carries prompt/model/first_frame/last_frame and nothing else, so
        duration and resolution are the router's own defaults. first_frame/last_frame are passed
        through under the names the router expects; it ignores what a given provider cannot use
        rather than failing, so an image-to-video request degrades to text-to-video instead of
        erroring.
        """
        payload: Dict[str, Any] = {"prompt": request.prompt}
        if request.model:
            payload["model"] = request.model
        if getattr(request, "first_frame", None):
            payload["first_frame"] = request.first_frame
        if getattr(request, "last_frame", None):
            payload["last_frame"] = request.last_frame
        return payload

    async def generate_video(self, request: VideoGenerationRequest) -> VideoGenerationResponse:
        """Quote, check the price, then submit exactly once and wait for the file.

        Raises before spending if anything looks wrong. After the submit there is no retry and no
        second attempt: at that point the credits are gone whatever this function returns, so the
        only honest thing left to do is report what happened.
        """
        payload = self._payload(request)

        # --- free checks first ------------------------------------------------------------
        try:
            q = await self.quote(request)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                f"omniroute_video: cannot reach the video router at {self.base_url} "
                f"({type(exc).__name__}: {exc}). Is `python video_router.py serve` running?"
            ) from exc

        if q.get("error"):
            raise RuntimeError(f"omniroute_video: router refused the request: {q['error']}")

        cost = q.get("quote", q.get("estimate"))
        if cost is None:
            raise RuntimeError(f"omniroute_video: router returned no price for this request: {q}")
        if cost > self.max_credits:
            raise RuntimeError(
                f"omniroute_video: refusing to spend {cost} credits on one clip "
                f"(ceiling is {self.max_credits}). Raise OMNIROUTE_MAX_CREDITS to allow it."
            )

        logger.info(
            "omniroute_video: submitting model=%s cost=%s credits exact=%s",
            payload.get("model"), cost, q.get("exact"),
        )

        # --- the irreversible part --------------------------------------------------------
        r = await self.client.post(
            "/v1/videos/generations",
            json={**payload, "wait": True, "wait_timeout": int(self.client.timeout.read or 900)},
        )
        r.raise_for_status()
        job = r.json()

        if job.get("status") != "succeeded":
            raise RuntimeError(
                f"omniroute_video: job {job.get('id')} ended {job.get('status')}: "
                f"{job.get('error')} (charged {job.get('credits_charged')} credits)"
            )

        url = job.get("content_url")
        return VideoGenerationResponse(
            created=int(job.get("finished") or time.time()),
            data=[{
                "url": f"{self.base_url}{url}" if url and url.startswith("/") else url,
                # The local path matters here: the pipeline stitches clips with ffmpeg, and reading
                # the file beats round-tripping it through HTTP for no reason.
                "path": job.get("file"),
                "provider": job.get("provider"),
                "job_id": job.get("id"),
                "credits_charged": job.get("credits_charged"),
                "bytes": job.get("bytes_total"),
                "duration": job.get("duration"),
                "revised_prompt": request.prompt,
            }],
        )

    # ---------------------------------------------------------------- not this adapter's job
    def _unsupported(self, what: str):
        return NotImplementedError(
            f"omniroute_video is a video-only provider; {what} is served by the chat/image "
            f"providers in PROVIDER_PRIORITY."
        )

    async def chat_completion(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        raise self._unsupported("chat_completion")

    async def chat_completion_stream(
        self, request: ChatCompletionRequest
    ) -> AsyncGenerator[ChatCompletionChunk, None]:
        raise self._unsupported("chat_completion_stream")
        yield  # pragma: no cover -- makes this an async generator, as the ABC declares

    async def generate_image(self, request: ImageGenerationRequest) -> ImageGenerationResponse:
        raise self._unsupported("generate_image")

    async def create_embedding(self, request: EmbeddingRequest) -> EmbeddingResponse:
        raise self._unsupported("create_embedding")

    async def aclose(self) -> None:
        await self.client.aclose()
