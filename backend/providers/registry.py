"""Provider registry for multi-vendor free-tier LLM provider management.

Implements the ProviderRegistry class described in ARCHITECTURE.md and
MIGRATION_TODOS.md Phase 1.3. The registry:

  * lazily instantiates provider adapters from configuration
  * selects a provider by priority / capability / health
  * tracks per-provider health, latency and quota state
  * supports automatic failover when a provider errors or is rate-limited

NVIDIA NIM is a TOTAL NO-GO (AC-10) and is never registered.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from .base import AIProviderAdapter, ProviderHealth, ProviderStatus

logger = logging.getLogger(__name__)


@dataclass
class ProviderRecord:
    """Runtime state for a single registered provider."""

    name: str
    adapter: AIProviderAdapter
    priority: int = 0
    capabilities: Tuple[str, ...] = ("chat",)
    health: ProviderHealth = field(default_factory=ProviderHealth)
    consecutive_failures: int = 0
    cooldown_until: float = 0.0


class ProviderRegistry:
    """Registry that owns provider adapters and routes requests with fallback."""

    def __init__(self) -> None:
        self._providers: Dict[str, ProviderRecord] = {}
        self._lock = asyncio.Lock()
        self._factories: Dict[str, Callable[[], Awaitable[AIProviderAdapter]]] = {}

    # ------------------------------------------------------------------ registration
    def register_factory(
        self,
        name: str,
        factory: Callable[[], Awaitable[AIProviderAdapter]],
        priority: int = 0,
        capabilities: Tuple[str, ...] = ("chat",),
    ) -> None:
        """Register a lazy async factory for a provider."""
        if "nim" in name.lower() or "nvidia" in name.lower():
            raise ValueError("NVIDIA NIM is a TOTAL NO-GO (AC-10); cannot register.")
        self._factories[name] = factory
        # Pre-seed a record so priority ordering is stable before first use.
        if name not in self._providers:
            self._providers[name] = ProviderRecord(
                name=name, adapter=None, priority=priority, capabilities=capabilities  # type: ignore[arg-type]
            )
        else:
            self._providers[name].priority = priority
            self._providers[name].capabilities = capabilities

    def register(self, name: str, adapter: AIProviderAdapter, priority: int = 0,
                 capabilities: Tuple[str, ...] = ("chat",)) -> None:
        """Register an already-constructed adapter."""
        if "nim" in name.lower() or "nvidia" in name.lower():
            raise ValueError("NVIDIA NIM is a TOTAL NO-GO (AC-10); cannot register.")
        self._providers[name] = ProviderRecord(
            name=name, adapter=adapter, priority=priority, capabilities=capabilities
        )

    # ------------------------------------------------------------------ lookup
    def list_providers(self) -> List[str]:
        return sorted(self._providers.keys(), key=lambda n: self._providers[n].priority)

    def get(self, name: str) -> Optional[ProviderRecord]:
        return self._providers.get(name)

    def _candidates(self, capability: str) -> List[ProviderRecord]:
        now = time.monotonic()
        avail = [
            r for r in self._providers.values()
            if capability in r.capabilities and now >= r.cooldown_until
        ]
        avail.sort(key=lambda r: r.priority)
        return avail

    async def get_adapter(
        self, capability: str = "chat", prefer: Optional[str] = None
    ) -> AIProviderAdapter:
        """Return the best available adapter for a capability, with fallback."""
        async with self._lock:
            candidates = self._candidates(capability)
            if prefer and prefer in self._providers:
                candidates = [self._providers[prefer]] + [
                    c for c in candidates if c.name != prefer
                ]
            if not candidates:
                raise RuntimeError(f"No provider available for capability={capability!r}")
            for rec in candidates:
                await self._ensure_adapter(rec)
                if rec.adapter is not None:
                    return rec.adapter
            raise RuntimeError(f"Failed to materialise adapter for capability={capability!r}")

    async def _ensure_adapter(self, rec: ProviderRecord) -> None:
        if rec.adapter is not None:
            return
        factory = self._factories.get(rec.name)
        if factory is None:
            return
        try:
            rec.adapter = await factory()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Provider %s factory failed: %s", rec.name, exc)
            self._mark_failure(rec)

    # ------------------------------------------------------------------ health
    def report_success(self, name: str, latency_ms: float = 0.0) -> None:
        rec = self._providers.get(name)
        if rec is None:
            return
        rec.consecutive_failures = 0
        rec.cooldown_until = 0.0
        rec.health = ProviderHealth(
            status=ProviderStatus.HEALTHY,
            latency_ms=latency_ms,
            last_check=time.monotonic(),
        )

    def report_failure(self, name: str, reason: str = "") -> None:
        rec = self._providers.get(name)
        if rec is None:
            return
        self._mark_failure(rec, reason)

    def _mark_failure(self, rec: ProviderRecord, reason: str = "") -> None:
        rec.consecutive_failures += 1
        backoff = min(60.0, 2.0 ** rec.consecutive_failures)
        rec.cooldown_until = time.monotonic() + backoff
        status = ProviderStatus.DEGRADED if rec.consecutive_failures < 3 else ProviderStatus.UNHEALTHY
        rec.health = ProviderHealth(
            status=status, latency_ms=rec.health.latency_ms, last_check=time.monotonic(), error=reason
        )

    def snapshot(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for name in self.list_providers():
            rec = self._providers[name]
            out.append({
                "name": name,
                "priority": rec.priority,
                "capabilities": list(rec.capabilities),
                "status": rec.health.status.value,
                "latency_ms": rec.health.latency_ms,
                "consecutive_failures": rec.consecutive_failures,
                "in_cooldown": time.monotonic() < rec.cooldown_until,
            })
        return out


# Module-level singleton ------------------------------------------------------
_registry: Optional[ProviderRegistry] = None


def get_registry() -> ProviderRegistry:
    global _registry
    if _registry is None:
        _registry = ProviderRegistry()
    return _registry


def reset_registry() -> None:
    """Test helper: drop the singleton."""
    global _registry
    _registry = None

# Already exists, but ensure no NVIDIA references. We'll just read and ensure.