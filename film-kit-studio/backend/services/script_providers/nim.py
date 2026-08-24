"""
NVIDIA NIM Script LLM Provider.

Wraps the existing NIM HTTP call logic (previously in nim_llm.py).
NIM is OpenAI-compatible, so this is the reference implementation.
"""

import json
import os
import httpx
from typing import Optional

from config import settings
from .base import ScriptLLMProvider


class NIMProvider:
    """NVIDIA NIM LLM provider (OpenAI-compatible API)."""

    name = "nim"

    def __init__(self) -> None:
        self.api_key = settings.nim_api_key
        self.base_url = settings.nim_base_url
        self.model = settings.nim_llm_model
        self.rpm = settings.nim_rpm

    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        if not self.is_configured():
            raise RuntimeError("NIM API key not configured")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        return data["choices"][0]["message"]["content"]


# Singleton instance
nim_provider = NIMProvider()