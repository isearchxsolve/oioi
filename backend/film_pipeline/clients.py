"""Typed async HTTP clients for the two frozen supply-layer contracts."""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Dict, Literal, Optional

import httpx

from .models import (
    CapacitySeat,
    ChatReply,
    VideoAuthError,
    VideoCapacity,
    VideoJob,
    VideoNoCapacity,
    VideoSubmissionUnknown,
    VideoSubmission,
    VideoTransientError,
    VideoWallError,
    classify_video_failure,
)


class ChatPoolClient:
    """Consumer client for the :8190 OpenAI-shaped session-pool contract."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8190",
        *,
        client: Optional[httpx.AsyncClient] = None,
        retries: int = 3,
    ) -> None:
        self._owned = client is None
        # Structured multi-shot JSON batches are much larger than a simple chat
        # probe. The consumer pool can legitimately take longer than 45 seconds to
        # route one, so keep strict parsing but grant the contract a 180s read budget.
        self.client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"), timeout=httpx.Timeout(180.0, connect=10.0)
        )
        self.retries = max(0, retries)

    async def aclose(self) -> None:
        if self._owned:
            await self.client.aclose()

    async def message(self, content: str, *, max_tokens: int = 1024, model: str = "session-pool/auto") -> ChatReply:
        """Make one OpenAI-shaped completion and retain router provenance."""
        payload = {
            "model": model or "session-pool/auto",
            "max_tokens": max(1, int(max_tokens)),
            "messages": [{"role": "user", "content": content}],
        }
        last: Optional[BaseException] = None
        for attempt in range(self.retries + 1):
            try:
                response = await self.client.post("/v1/chat/completions", json=payload)
                if response.status_code == 503:
                    last = VideoTransientError("chat pool is busy (503)")
                    if attempt < self.retries:
                        await asyncio.sleep(min(12.0, 1.5 * (2**attempt)))
                        continue
                    raise last
                response.raise_for_status()
                body = response.json()
                choices = body.get("choices") or []
                message = choices[0].get("message") if choices and isinstance(choices[0], dict) else {}
                text = str((message or {}).get("content") or "")
                if not text:
                    raise VideoTransientError("chat pool returned no text content")
                return ChatReply(
                    text=text, provider=body.get("provider"), session=body.get("session"), tenant=body.get("tenant"),
                )
            except httpx.HTTPError as exc:
                last = VideoTransientError(f"chat transport: {type(exc).__name__}")
                if attempt < self.retries:
                    await asyncio.sleep(min(12.0, 1.5 * (2**attempt)))
                    continue
                raise last from exc
        raise VideoTransientError("chat pool request exhausted retries") from last

    async def models(self) -> Dict[str, Any]:
        """Return the session-pool model catalogue from ``GET /v1/models``."""
        response = await self.client.get("/v1/models")
        response.raise_for_status()
        body = response.json()
        return body if isinstance(body, dict) else {"data": body}

    async def health(self) -> Dict[str, Any]:
        """Return the live pool health document without making a generation request."""
        # The new consumer endpoint exposes model discovery rather than a separate
        # health resource. A successful catalogue response is the non-spending probe.
        models = await self.models()
        return {"status": "healthy", "models": len(models.get("data") or [])}


class VideoRouterClient:
    """Video adapter for the :8190 OpenAI-shaped consumer contract.

    The router advertises video seats in ``/v1/models`` and dispatches video through
    ``/v1/chat/completions`` with ``video/auto`` (or a deliberately pinned video
    host model). It returns provider/session/tenant provenance with every response.
    Unlike the former /v1/video/jobs service, a completed URL may be returned inline;
    the adapter treats that as a completed durable job without inventing a polling
    endpoint that the new contract does not provide.
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8190",
        *,
        client: Optional[httpx.AsyncClient] = None,
        mode: Literal["mock", "live"] = "mock",
        live: bool = False,
        max_clips: int = 0,
        video_model: str = "video/auto",
    ) -> None:
        self._owned = client is None
        # A video route can acknowledge an asynchronous render slower than a plain
        # text completion. This is a transport budget only; it does not relax any
        # response parsing or create an imaginary job API.
        self.client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"), timeout=httpx.Timeout(180.0, connect=10.0)
        )
        self.mode = mode
        self.max_clips = int(max_clips)
        self.video_model = video_model.strip() or "video/auto"
        if self.mode == "live" and not self.video_model.startswith("video/"):
            raise ValueError("live video model must be video/auto or video/<host>/auto")
        self._live_submissions = 0
        self._inline_jobs: Dict[str, VideoJob] = {}
        self._catalogue: Optional[list[Dict[str, Any]]] = None
        if mode == "live" and (not live or self.max_clips <= 0):
            raise ValueError("live video client requires explicit live=True and positive max_clips")

    async def aclose(self) -> None:
        if self._owned:
            await self.client.aclose()

    @staticmethod
    def _error(response: httpx.Response) -> VideoTransientError:
        try:
            message = str((response.json() or {}).get("error") or response.text)
        except ValueError:
            message = response.text
        return VideoTransientError(f"video HTTP {response.status_code}: {message[:240]}")

    async def submit(
        self,
        *,
        job_key: str,
        prompt: str,
        duration_seconds: int,
        image_refs: list[str],
        aspect_ratio: str,
        seed: Optional[int],
    ) -> VideoSubmission:
        if self.mode == "mock":
            return await self._mock_submit(
                job_key=job_key, prompt=prompt, duration_seconds=duration_seconds, image_refs=image_refs,
                aspect_ratio=aspect_ratio, seed=seed,
            )
        if self.mode == "live" and self._live_submissions >= self.max_clips:
            raise VideoTransientError("live video safety cap reached; no further submit is permitted")
        try:
            response = await self.client.post(
                "/v1/chat/completions",
                json={
                    "model": self.video_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 1024,
                    # The bridge receives render context in addition to the normal
                    # OpenAI-shaped message. `job_key` is retained for operator
                    # reconciliation, but OiiOii never assumes it makes a timed-out
                    # consumer POST idempotent unless the contract says so.
                    "video": {
                        "job_key": job_key, "duration_seconds": int(duration_seconds),
                        "image_refs": image_refs, "aspect_ratio": aspect_ratio, "seed": seed,
                    },
                },
            )
        except httpx.HTTPError as exc:
            raise VideoSubmissionUnknown(
                f"video submission receipt missing after {type(exc).__name__}; remote spend state is unknown"
            ) from exc
        if response.status_code == 503:
            try:
                body = response.json()
            except ValueError:
                body = {}
            if body.get("error") == "no_capacity":
                raise VideoNoCapacity(body.get("retryAfterSeconds", 120))
        if response.status_code not in (200, 202):
            raise self._error(response)
        body = response.json()
        if self.mode == "live":
            self._live_submissions += 1
        payload = self._video_payload(body)
        job_id = str(payload.get("jobId") or payload.get("job_id") or payload.get("id") or body.get("id") or job_key)
        url = self._url_from_payload(payload) or self._url_from_payload(body)
        status = str(payload.get("status") or ("succeeded" if url else "queued")).lower()
        if status not in {"queued", "running", "succeeded", "failed"}:
            status = "succeeded" if url else "queued"
        self._inline_jobs[job_id] = VideoJob(
            job_id=job_id, status=status, provider=str(body.get("provider") or payload.get("provider") or "video/auto"),
            progress=float(payload.get("progress") or (1.0 if url else 0.0)), url=url,
            error=payload.get("error"), credits_spent=float(payload.get("creditsSpent") or payload.get("credits_spent") or 0),
        )
        return VideoSubmission(
            job_id=job_id,
            provider=str(body.get("provider") or payload.get("provider") or "video/auto"),
            estimated_seconds=int(payload.get("estimatedSeconds") or payload.get("estimated_seconds") or duration_seconds),
            credits_reserved=float(payload.get("creditsReserved") or payload.get("credits_reserved") or 0),
            idempotent_replay=response.status_code == 200,
            session=body.get("session"), tenant=body.get("tenant"),
            status=status, url=url, error=payload.get("error"),
            credits_spent=float(payload.get("creditsSpent") or payload.get("credits_spent") or 0),
        )

    async def get_job(self, job_id: str) -> VideoJob:
        if self.mode == "mock":
            return await self._mock_get_job(job_id)
        known = self._inline_jobs.get(job_id)
        if known is None:
            raise VideoTransientError("video response was not retained in this worker")
        return known

    async def capacity(self) -> VideoCapacity:
        if self.mode == "mock":
            return await self._mock_capacity()
        if self._catalogue is None:
            response = await self.client.get("/v1/models")
            if response.status_code < 200 or response.status_code >= 300:
                raise self._error(response)
            body = response.json()
            self._catalogue = [row for row in (body.get("data") or []) if isinstance(row, dict)]
        # ``video/auto`` is the balancing alias, not a paid-seat record. The
        # remaining catalogue rows are individual dispatchable seats (24 on the
        # supplied consumer service). A deliberately pinned model narrows that
        # inventory to its own seats so the scheduler cannot claim capacity from a
        # host that the actual submit call will not use.
        video_routes = [
            row for row in self._catalogue
            if str(row.get("id") or "").startswith("video/")
            and str(row.get("id") or "") != "video/auto"
            and (self.video_model == "video/auto" or str(row.get("id") or "") == self.video_model)
        ]
        seats = [
            CapacitySeat(
                seat=f"video-seat-{index:02d}",
                provider=str(row.get("id") or "video/auto"),
                credits_remaining=0.0,
                clips_remaining=1,
                cooldown_until=None,
            )
            for index, row in enumerate(video_routes, start=1)
        ]
        return VideoCapacity(seats=seats, total_clips_available=len(seats))

    async def cancel(self, job_id: str) -> None:
        if self.mode == "mock":
            response = await self.client.delete(f"/v1/video/jobs/{job_id}")
            response.raise_for_status()
            return
        # The consumer contract intentionally has no cancellation endpoint. Forgetting
        # a local inline handle never claims that a remote, spend-gated render stopped.
        self._inline_jobs.pop(job_id, None)

    @staticmethod
    def _video_payload(body: Dict[str, Any]) -> Dict[str, Any]:
        if isinstance(body.get("video"), dict):
            return dict(body["video"])
        choices = body.get("choices") or []
        message = choices[0].get("message") if choices and isinstance(choices[0], dict) else {}
        content = (message or {}).get("content")
        if isinstance(content, dict):
            return dict(content)
        if isinstance(content, str):
            try:
                decoded = json.loads(content)
                if isinstance(decoded, dict):
                    return decoded
            except json.JSONDecodeError:
                return {"content": content}
        return {}

    @staticmethod
    def _url_from_payload(value: Dict[str, Any]) -> Optional[str]:
        for key in ("url", "videoUrl", "video_url", "downloadUrl", "download_url"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.startswith(("https://", "http://")):
                return candidate
        content = value.get("content")
        if isinstance(content, str):
            match = re.search(r"https?://[^\s\"']+", content)
            if match:
                return match.group(0).rstrip(".,)")
        return None

    async def _mock_submit(
        self, *, job_key: str, prompt: str, duration_seconds: int, image_refs: list[str], aspect_ratio: str,
        seed: Optional[int],
    ) -> VideoSubmission:
        response = await self.client.post(
            "/v1/video/jobs",
            json={
                "jobKey": job_key, "prompt": prompt, "durationSeconds": int(duration_seconds),
                "imageRefs": image_refs, "aspectRatio": aspect_ratio, "seed": seed,
            },
        )
        if response.status_code == 503:
            try:
                body = response.json()
            except ValueError:
                body = {}
            if body.get("error") == "no_capacity":
                raise VideoNoCapacity(body.get("retryAfterSeconds", 120))
        if response.status_code not in (200, 202):
            raise self._error(response)
        body = response.json()
        return VideoSubmission(
            job_id=str(body["jobId"]), provider=str(body["provider"]),
            estimated_seconds=int(body.get("estimatedSeconds") or 0),
            credits_reserved=float(body.get("creditsReserved") or 0), idempotent_replay=response.status_code == 200,
        )

    async def _mock_get_job(self, job_id: str) -> VideoJob:
        response = await self.client.get(f"/v1/video/jobs/{job_id}")
        if response.status_code < 200 or response.status_code >= 300:
            raise self._error(response)
        body = response.json()
        return VideoJob(
            job_id=str(body["jobId"]), status=body["status"], provider=str(body.get("provider") or "unknown"),
            progress=float(body.get("progress") or 0.0), url=body.get("url"), error=body.get("error"),
            credits_spent=float(body.get("creditsSpent") or 0),
        )

    async def _mock_capacity(self) -> VideoCapacity:
        response = await self.client.get("/v1/video/capacity")
        if response.status_code < 200 or response.status_code >= 300:
            raise self._error(response)
        body = response.json()
        seats = [
            CapacitySeat(
                seat=str(row["seat"]), provider=str(row["provider"]),
                credits_remaining=float(row.get("creditsRemaining") or 0),
                clips_remaining=int(row.get("clipsRemaining") or 0), cooldown_until=row.get("cooldownUntil"),
            )
            for row in body.get("seats") or []
        ]
        return VideoCapacity(seats=seats, total_clips_available=int(body.get("totalClipsAvailable") or 0))

    @staticmethod
    def terminal_exception(error: Optional[str]) -> VideoTransientError | VideoWallError | VideoAuthError:
        return classify_video_failure(error)((error or "video job failed").strip())
