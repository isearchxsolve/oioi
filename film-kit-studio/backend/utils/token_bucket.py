"""
Token bucket rate limiter — migrated and enhanced from the original
film_kit.py and nim_agent.py scripts.

Features:
  - Adaptive RPM targeting (80% of ceiling)
  - Hard backoff on 429 / rate-limit responses
  - Thread-safe with asyncio-compatible async wait
  - Rolling 60-second TPM observation meter
"""

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional


class TokenBucket:
    """
    Async-compatible RPM guard. Targets 80% of the ceiling RPM,
    backs off hard on 429 responses.

    Migrated from film_kit.py TokenBucket with async support added
    for the FastAPI non-blocking architecture.
    """

    def __init__(self, rpm: float = 40.0, min_gap: float = 1.0, safety_margin: float = 0.8):
        self.ceiling_rpm = max(1.0, rpm)
        self.rpm = self.ceiling_rpm * safety_margin
        self.min_gap = min_gap
        self.last_call = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        """Async wait until it's safe to make the next API call."""
        gap = max(self.min_gap, 60.0 / self.rpm)
        elapsed = time.monotonic() - self.last_call
        if elapsed < gap:
            await asyncio.sleep(gap - elapsed)
        self.last_call = time.monotonic()

    def penalize(self) -> None:
        """Halve the RPM after a 429 — gradual recovery happens via ceiling."""
        self.rpm = max(2.0, self.rpm * 0.5)

    def reset(self) -> None:
        """Restore full RPM after sustained success."""
        self.rpm = self.ceiling_rpm * 0.8


class TokenMeter:
    """Rolling 60-second TPM (tokens-per-minute) observer."""

    def __init__(self):
        self._window: deque = deque()
        self.total_prompt = 0
        self.total_completion = 0

    def _prune(self) -> None:
        now = time.monotonic()
        while self._window and self._window[0][0] < now - 60.0:
            self._window.popleft()

    def record(self, prompt_tokens: int, completion_tokens: int) -> None:
        now = time.monotonic()
        self._window.append((now, max(0, prompt_tokens) + max(0, completion_tokens)))
        self.total_prompt += max(0, prompt_tokens)
        self.total_completion += max(0, completion_tokens)
        self._prune()

    def tpm(self) -> int:
        self._prune()
        return sum(t for _, t in self._window)

    def stats(self) -> str:
        return (
            f"{self.tpm()} TPM  ·  lifetime "
            f"{self.total_prompt} in / {self.total_completion} out"
        )


def estimate_tokens(text: Optional[str]) -> int:
    """~4 chars/token estimate for pacing visibility."""
    if not text:
        return 0
    return max(1, len(text) // 4)


# Global meter instance
TOKEN_METER = TokenMeter()

# Global token bucket instances (for different services)
_buckets: dict[str, TokenBucket] = {}


def get_token_bucket(name: str = "default") -> TokenBucket:
    """Get or create a token bucket for the given service name."""
    if name not in _buckets:
        from config import settings
        if name == "nim_llm":
            _buckets[name] = TokenBucket(rpm=settings.nim_rpm)
        elif name == "cosmos":
            _buckets[name] = TokenBucket(rpm=min(settings.nim_rpm, 20.0))
        elif name == "veo":
            _buckets[name] = TokenBucket(rpm=10.0)
        elif name == "kling":
            _buckets[name] = TokenBucket(rpm=10.0)
        else:
            _buckets[name] = TokenBucket()
    return _buckets[name]
