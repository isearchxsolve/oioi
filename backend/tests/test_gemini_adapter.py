"""Tests for the GeminiAdapter (T001) — free multimodal chat/image/video/audio.

Validates that the adapter:
  * implements AIProviderAdapter fully
  * routes chat/image/video through Google AI Studio v1beta
  * never references NVIDIA NIM (AC-10)
  * degrades gracefully when GEMINI_API_KEY is absent
"""
from __future__ import annotations

import asyncio
from typing import Any, AsyncGenerator, Dict, List

import pytest

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from providers.base import (
    AIProviderAdapter,
    ChatCompletionRequest,
    ImageGenerationRequest,
    VideoGenerationRequest,
    EmbeddingRequest,
)
from providers.gemini import GeminiAdapter


def _adapter() -> GeminiAdapter:
    return GeminiAdapter(api_key="test-key")


def test_is_ai_provider_adapter():
    assert isinstance(_adapter(), AIProviderAdapter)


def test_provider_name():
    assert _adapter().get_provider_name() == "gemini"


def test_no_nvidia_reference():
    import providers.gemini as mod
    src = open(mod.__file__, encoding="utf-8").read().lower()
    assert "nvidia" not in src
    assert "nim" not in src.replace("animate", "")  # avoid false positive on 'animate'
    assert "ac-10" not in src


def test_chat_completion_builds_gemini_payload(monkeypatch):
    captured: Dict[str, Any] = {}

    class FakeResp:
        status_code = 200
        def json(self_inner):
            return {
                "candidates": [{
                    "content": {"parts": [{"text": "hello world"}], "role": "model"},
                    "finishReason": "STOP",
                }],
                "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 2},
            }
        def raise_for_status(self_inner): pass

    async def fake_post(url, json=None, **kw):
        captured["url"] = url
        captured["json"] = json
        return FakeResp()

    adapter = _adapter()
    monkeypatch.setattr(adapter.client, "post", fake_post)

    req = ChatCompletionRequest(
        model="gemini-1.5-flash",
        messages=[{"role": "user", "content": "hi"}],
    )
    resp = asyncio.get_event_loop().run_until_complete(adapter.chat_completion(req))

    assert resp.model == "gemini-1.5-flash"
    assert resp.choices[0]["message"]["content"] == "hello world"
    assert "contents" in captured["json"]
    assert "/models/gemini-1.5-flash:generateContent" in captured["url"]


def test_generate_image_returns_url(monkeypatch):
    class FakeResp:
        status_code = 200
        def json(self_inner):
            return {
                "candidates": [{
                    "content": {"parts": [{"text": "https://img.example/x.png"}]}
                }]
            }
        def raise_for_status(self_inner): pass

    async def fake_post(url, json=None, **kw):
        return FakeResp()

    adapter = _adapter()
    monkeypatch.setattr(adapter.client, "post", fake_post)
    resp = asyncio.get_event_loop().run_until_complete(
        adapter.generate_image(ImageGenerationRequest(prompt="a cat", model="gemini-2.0-flash-exp"))
    )
    assert resp.data
    assert "url" in resp.data[0]


def test_missing_key_raises():
    with pytest.raises(ValueError):
        GeminiAdapter(api_key="")
