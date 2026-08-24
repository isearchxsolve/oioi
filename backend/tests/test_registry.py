"""Tests for ProviderRegistry (T001, T002, T003, T004) — validates registry, adapters, and provider management.

Tests cover:
  * Registry singleton and reset
  * Provider registration with priority/capabilities
  * NVIDIA NIM blocking (AC-10)
  * Adapter lookup with failover
  * Health tracking and cooldown
  * All adapter implementations (Gemini, Pollinations, etc.)
"""
from __future__ import annotations

import asyncio
import pytest
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

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
from providers.registry import ProviderRegistry, get_registry, reset_registry


class MockAdapter(AIProviderAdapter):
    """Mock adapter for testing registry behavior."""
    
    def __init__(self, name: str = "mock"):
        self.provider_name = name
        self.health_status = ProviderStatus.HEALTHY
    
    async def chat_completion(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        return ChatCompletionResponse(
            id="mock-id", model=request.model, choices=[], usage={}
        )
    
    async def chat_completion_stream(self, request: ChatCompletionRequest) -> AsyncGenerator[ChatCompletionChunk, None]:
        """Async generator for streaming chat completions."""
        yield ChatCompletionChunk(
            id="mock-id",
            object="chat.completion.chunk",
            created=0,
            model=request.model,
            choices=[]
        )
    
    async def generate_image(self, request: ImageGenerationRequest) -> ImageGenerationResponse:
        return ImageGenerationResponse(data=[])
    
    async def generate_video(self, request: VideoGenerationRequest) -> VideoGenerationResponse:
        return VideoGenerationResponse(data=[])
    
    async def create_embedding(self, request: EmbeddingRequest) -> EmbeddingResponse:
        return EmbeddingResponse(object="list", data=[], model=request.model, usage={})
    
    async def list_models(self) -> list[Model]:
        return [Model(id="mock-model", object="model")]
    
    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(status=self.health_status)
    
    def get_provider_name(self) -> str:
        return self.provider_name


class TestProviderRegistry:
    """Tests for ProviderRegistry singleton and management."""
    
    def setup_method(self):
        """Reset registry before each test."""
        reset_registry()
    
    def test_registry_singleton(self):
        """Registry is a singleton."""
        r1 = get_registry()
        r2 = get_registry()
        assert r1 is r2
    
    def test_registry_reset(self):
        """Reset clears the singleton."""
        registry = get_registry()
        registry.register("test", MockAdapter("test"), priority=0, capabilities=("chat",))
        reset_registry()
        new_registry = get_registry()
        assert new_registry is not registry
        assert len(new_registry._providers) == 0
    
    def test_nvidia_blocked(self):
        """NVIDIA NIM providers are blocked (AC-10)."""
        registry = get_registry()
        with pytest.raises(ValueError, match="NVIDIA NIM is a TOTAL NO-GO"):
            registry.register("nvidia-nim", MockAdapter("nvidia"), priority=0)
        with pytest.raises(ValueError, match="NVIDIA NIM is a TOTAL NO-GO"):
            registry.register("nim", MockAdapter("nim"), priority=0)
    
    def test_register_factory(self):
        """Factory registration works correctly."""
        registry = get_registry()
        
        async def factory():
            return MockAdapter("factory-test")
        
        registry.register_factory("factory-test", factory, priority=0, capabilities=("chat", "image"))
        assert "factory-test" in registry._providers
        assert registry._providers["factory-test"].capabilities == ("chat", "image")
    
    def test_list_providers_by_priority(self):
        """Providers are listed in priority order."""
        registry = get_registry()
        registry.register("low", MockAdapter("low"), priority=10)
        registry.register("high", MockAdapter("high"), priority=0)
        registry.register("medium", MockAdapter("medium"), priority=5)
        
        providers = registry.list_providers()
        assert providers == ["high", "medium", "low"]
    
    def test_get_adapter_returns_best(self):
        """get_adapter returns highest priority available."""
        registry = get_registry()
        registry.register("high", MockAdapter("high"), priority=0, capabilities=("chat",))
        registry.register("low", MockAdapter("low"), priority=10, capabilities=("chat",))
        
        adapter = asyncio.get_event_loop().run_until_complete(
            registry.get_adapter("chat")
        )
        assert adapter.get_provider_name() == "high"
    
    def test_get_adapter_with_prefer(self):
        """get_adapter respects prefer parameter."""
        registry = get_registry()
        registry.register("high", MockAdapter("high"), priority=0, capabilities=("chat",))
        registry.register("low", MockAdapter("low"), priority=10, capabilities=("chat",))
        
        adapter = asyncio.get_event_loop().run_until_complete(
            registry.get_adapter("chat", prefer="low")
        )
        assert adapter.get_provider_name() == "low"
    
    def test_get_adapter_fails_when_unavailable(self):
        """get_adapter raises when no provider has capability."""
        registry = get_registry()
        registry.register("only-chat", MockAdapter("only-chat"), priority=0, capabilities=("chat",))
        
        with pytest.raises(RuntimeError, match="No provider available"):
            asyncio.get_event_loop().run_until_complete(
                registry.get_adapter("image")
            )
    
    def test_report_success(self):
        """report_success updates health status."""
        registry = get_registry()
        registry.register("test", MockAdapter("test"), priority=0)
        
        registry.report_success("test", latency_ms=100.0)
        record = registry.get("test")
        assert record.health.status == ProviderStatus.HEALTHY
        assert record.health.latency_ms == 100.0
    
    def test_report_failure(self):
        """report_failure triggers cooldown."""
        registry = get_registry()
        registry.register("test", MockAdapter("test"), priority=0)
        
        registry.report_failure("test", "test error")
        record = registry.get("test")
        assert record.consecutive_failures == 1
        assert record.cooldown_until > 0
    
    def test_snapshot(self):
        """snapshot returns provider states."""
        registry = get_registry()
        registry.register("test", MockAdapter("test"), priority=0, capabilities=("chat", "image"))
        
        snapshot = registry.snapshot()
        assert len(snapshot) == 1
        assert snapshot[0]["name"] == "test"
        assert snapshot[0]["priority"] == 0
        assert "chat" in snapshot[0]["capabilities"]


class TestGeminiAdapter:
    """Tests for GeminiAdapter implementation."""
    
    def test_is_ai_provider_adapter(self):
        """GeminiAdapter implements AIProviderAdapter."""
        from providers.gemini import GeminiAdapter
        adapter = GeminiAdapter(api_key="test-key")
        assert isinstance(adapter, AIProviderAdapter)
    
    def test_provider_name(self):
        """GeminiAdapter returns correct provider name."""
        from providers.gemini import GeminiAdapter
        adapter = GeminiAdapter(api_key="test-key")
        assert adapter.get_provider_name() == "gemini"
    
    def test_no_nvidia_reference(self):
        """GeminiAdapter contains no NVIDIA references (AC-10)."""
        import providers.gemini as mod
        src = open(mod.__file__, encoding="utf-8").read().lower()
        assert "nvidia" not in src
        assert "nim" not in src.replace("animate", "")
        assert "ac-10" not in src


class TestPollinationsAdapter:
    """Tests for PollinationsAdapter (keyless image generation)."""
    
    def test_pollinations_exists(self):
        """PollinationsAdapter file exists."""
        import importlib.util
        spec = importlib.util.find_spec("providers.pollinations")
        assert spec is not None, "providers.pollinations module must exist"
    
    def test_pollinations_is_adapter(self):
        """PollinationsAdapter implements AIProviderAdapter."""
        from providers.pollinations import PollinationsAdapter
        adapter = PollinationsAdapter()
        assert isinstance(adapter, AIProviderAdapter)
    
    def test_pollinations_keyless(self):
        """PollinationsAdapter works without API key."""
        from providers.pollinations import PollinationsAdapter
        adapter = PollinationsAdapter()
        assert adapter.api_key is None or adapter.api_key == ""


class TestCohereAdapter:
    """Tests for CohereAdapter streaming support."""

    def test_cohere_streaming(self):
        """CohereAdapter implements streaming."""
        cohere = pytest.importorskip("cohere", reason="cohere package not installed")
        from providers.cohere import CohereAdapter
        adapter = CohereAdapter(api_key="test-key")
        assert hasattr(adapter, "chat_completion_stream")


class TestCloudflareAdapter:
    """Tests for CloudflareAdapter video delegation."""
    
    def test_cloudflare_video_not_implemented(self):
        """CloudflareAdapter raises NotImplementedError for video."""
        from providers.cloudflare import CloudflareAdapter
        adapter = CloudflareAdapter(api_key="test", account_id="test")
        
        async def test():
            with pytest.raises(NotImplementedError):
                await adapter.generate_video(VideoGenerationRequest(prompt="test", model="test"))
        
        asyncio.get_event_loop().run_until_complete(test())


class TestCerebrasAdapter:
    """Tests for CerebrasAdapter embedding support."""
    
    def test_cerebras_embedding_not_implemented(self):
        """CerebrasAdapter raises NotImplementedError for embeddings."""
        from providers.cerebras import CerebrasAdapter
        adapter = CerebrasAdapter(api_key="test-key")
        
        async def test():
            with pytest.raises(NotImplementedError):
                await adapter.create_embedding(EmbeddingRequest(input="test", model="test"))
        
        asyncio.get_event_loop().run_until_complete(test())