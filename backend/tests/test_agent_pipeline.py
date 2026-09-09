"""Tests for the 7-agent animation pipeline (AC-3).

Tests the full idea -> short film pipeline using only free-tier providers.
"""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from providers.base import (
    AIProviderAdapter,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ImageGenerationRequest,
    ImageGenerationResponse,
    VideoGenerationRequest,
    VideoGenerationResponse,
    ProviderHealth,
    ProviderStatus,
)
from providers.registry import ProviderRegistry, get_registry, reset_registry


class MockChatAdapter(AIProviderAdapter):
    """Mock adapter for chat-only testing."""
    
    def __init__(self, name: str = "mock-chat"):
        self.provider_name = name
        self.health_status = ProviderStatus.HEALTHY
    
    async def chat_completion(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        import json
        system_prompt = request.messages[0].get("content", "") if request.messages else ""
        
        chars_for_scriptwriter = ["char1", "char2"]
        chars_for_designer = [{"name": "char1", "description": "desc", "prompt": "prompt"}]
        
        mock_response = {
            "title": "Mock Title",
            "description": "A test story",
            "scenes": [{"description": "scene1", "duration": 5, "prompt": "prompt1", "style": "style1"}],
            "characters": chars_for_scriptwriter if "Scriptwriter" in system_prompt else chars_for_designer,
            "visual_style": "anime",
            "color_palette": ["#000000"],
            "character_sheet_prompt": "sheet",
            "scene_style_prompt": "scene style",
            "animations": [{"scene": 1, "prompt": "anim1", "duration": 5}],
            "music_prompt": "music",
            "sound_effects": [],
            "final_notes": "looks good",
            "approved": True,
            "revisions": []
        }
        return ChatCompletionResponse(
            id="mock-id",
            model=request.model,
            choices=[{"index": 0, "message": {"role": "assistant", "content": json.dumps(mock_response)}, "finish_reason": "stop"}],
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
        )
    
    async def chat_completion_stream(self, request: ChatCompletionRequest):
        yield ChatCompletionResponse(
            id="mock-id",
            model=request.model,
            choices=[{"index": 0, "message": {"role": "assistant", "content": "streamed"}, "finish_reason": "stop"}],
            usage={}
        )
    
    async def generate_image(self, request: ImageGenerationRequest) -> ImageGenerationResponse:
        return ImageGenerationResponse(data=[{"url": "https://mock.example.com/image.png"}])
    
    async def generate_video(self, request: VideoGenerationRequest) -> VideoGenerationResponse:
        return VideoGenerationResponse(data=[{"url": "https://mock.example.com/video.mp4"}])
    
    async def create_embedding(self, request):
        from providers.base import EmbeddingResponse
        return EmbeddingResponse(object="list", data=[], model=request.model, usage={})
    
    async def list_models(self):
        from providers.base import Model
        return [Model(id="mock-model", object="model")]
    
    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(status=self.health_status)
    
    def get_provider_name(self) -> str:
        return self.provider_name


class TestAgentPipeline:
    """Tests for the 7-agent animation pipeline."""
    
    def setup_method(self):
        """Reset registry before each test."""
        reset_registry()
        registry = get_registry()
        registry.register("mock", MockChatAdapter(), priority=0, capabilities=("chat", "image", "video"))
    
    def test_pipeline_exists(self):
        """Agent pipeline module exists and has required functions."""
        from agent_pipeline import AGENT_ROLES, run_scriptwriter, run_pipeline
        
        assert 'Scriptwriter' in AGENT_ROLES
        assert 'Art Director' in AGENT_ROLES
        assert 'Character Designer' in AGENT_ROLES
        assert 'Scene Designer' in AGENT_ROLES
        assert 'Animator' in AGENT_ROLES
        assert 'Sound Director' in AGENT_ROLES
        assert 'Director' in AGENT_ROLES
        
        # Test scriptwriter
        result = run_scriptwriter("A test story")
        assert isinstance(result, str)
        assert "test story" in result.lower()
    
    def test_pipeline_returns_all_agents(self):
        """Pipeline returns outputs from all 7 agents."""
        from agent_pipeline import run_pipeline
        
        result = run_pipeline("A hero's journey")
        
        assert 'script' in result
        assert 'storyboard' in result
        assert 'characters' in result
        assert 'scenes' in result
        assert 'animation' in result
        assert 'sound_plan' in result
        assert 'director_notes' in result
        assert 'roles' in result
        
        # Verify all 8 roles are present
        assert len(result['roles']) == 8
    
    def test_pipeline_with_registry(self):
        """Pipeline can use registry for provider calls."""
        from agent_pipeline import run_pipeline
        result = run_pipeline("A test adventure")
        
        # Pipeline should complete without error
        assert result is not None
        assert 'script' in result
    
    def test_agent_contracts_exist(self):
        """Agent contracts define all required interfaces."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("agent_contracts", os.path.join(os.path.dirname(__file__), '..', 'agent_contracts.py'))
        agent_contracts = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(agent_contracts)
        
        # Verify all agent types exist
        assert agent_contracts.AgentType.SCRIPTWRITER.value == 'scriptwriter'
        assert agent_contracts.AgentType.ART_DIRECTOR.value == 'art_director'
        assert agent_contracts.AgentType.CHARACTER_DESIGNER.value == 'character_designer'
        assert agent_contracts.AgentType.SCENE_DESIGNER.value == 'scene_designer'
        assert agent_contracts.AgentType.STORYBOARD_ARTIST.value == 'storyboard_artist'
        assert agent_contracts.AgentType.ANIMATOR.value == 'animator'
        assert agent_contracts.AgentType.SOUND_DIRECTOR.value == 'sound_director'
        assert agent_contracts.AgentType.DIRECTOR.value == 'director'
        
        # Verify input/output classes exist
        assert agent_contracts.ScriptwriterInput is not None
        assert agent_contracts.ScriptwriterOutput is not None
    
    def test_agent_orchestrator_interface(self):
        """AgentOrchestrator defines the pipeline interface."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("agent_contracts", os.path.join(os.path.dirname(__file__), '..', 'agent_contracts.py'))
        agent_contracts = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(agent_contracts)
        
        # Verify abstract methods exist
        import inspect
        methods = [m[0] for m in inspect.getmembers(agent_contracts.AgentOrchestrator, predicate=inspect.ismethod)]
        
        assert 'run_scriptwriter' in methods or hasattr(agent_contracts.AgentOrchestrator, 'run_scriptwriter')
        assert 'run_pipeline' in methods or hasattr(agent_contracts.AgentOrchestrator, 'run_pipeline')


class TestPipelineIntegration:
    """Integration tests for pipeline with providers."""
    
    def setup_method(self):
        """Reset registry before each test."""
        reset_registry()
        registry = get_registry()
        registry.register("mock", MockChatAdapter(), priority=0, capabilities=("chat", "image", "video"))
    
    def test_full_pipeline_with_mock_providers(self):
        """Full pipeline execution with mocked providers."""
        from agent_pipeline import run_pipeline
        
        result = run_pipeline("A sci-fi adventure")
        
        assert result is not None
        assert 'script' in result
        assert 'storyboard' in result
        assert 'characters' in result
        assert 'scenes' in result
        assert 'animation' in result
        assert 'sound_plan' in result
        assert 'director_notes' in result
    
    def test_pipeline_handles_missing_providers_gracefully(self):
        """Pipeline handles missing providers by raising an appropriate error."""
        # Don't register any providers
        reset_registry()
        
        from agent_pipeline import run_pipeline
        
        # Pipeline should fail since providers are required
        import pytest
        with pytest.raises(RuntimeError, match="No provider available"):
            run_pipeline("A test story")


def test_direct_registry_orchestrator_path_is_rejected_in_production(monkeypatch):
    """The retired compatibility pipeline cannot become a billable prod escape hatch."""
    from app.services.orchestrator import AnimationAgentOrchestrator

    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(RuntimeError, match="canonical ChatPoolClient"):
        AnimationAgentOrchestrator(registry=object())
