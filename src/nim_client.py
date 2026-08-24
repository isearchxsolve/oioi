# NVIDIA NIM API Client for OiiOii.ai Clone  (c) 2025 Neon Architect Team  This module provides a thin wrapper around the NVIDIA NIM Cloud API  for LLM, image, and video generation.  It follows the OpenAI-compatible API spec at https://integrate.api.nvidia.com/v1  ---------------------------------------------------------------------------  
import os
import json
import asyncio
from typing import Dict, List, Optional, AsyncGenerator, Any
import httpx
from dataclasses import dataclass

@dataclass
class NIMModel:
    id: str
    object: str = "model"
    owned_by: str = "nvidia"
    created: Optional[int] = None

class NIMClient:
    def __init__(self, api_key: Optional[str] = None, base_url: str = "https://integrate.api.nvidia.com/v1"):
        self.api_key = api_key or os.getenv("NVIDIA_API_KEY")
        self.base_url = base_url.rstrip("/")
        if not self.api_key:
            raise ValueError("NVIDIA API key is required. Set NVIDIA_API_KEY environment variable or pass api_key.")
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            },
            timeout=30.0
        )

    async def list_models(self) -> List[NIMModel]:
        """Fetch available models from NIM API."""
        response = await self.client.get("/models")
        response.raise_for_status()
        data = response.json()
        return [NIMModel(**model) for model in data.get("data", [])]

    async def chat_completion(
        self,
        model: str,
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        top_p: float = 0.9,
        stream: bool = False,
        stop: Optional[List[str]] = None,
        **kwargs
    ) -> Any:
        """Create a chat completion (OpenAI-compatible)."""
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
            "stream": stream
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if stop is not None:
            payload["stop"] = stop
        payload.update(kwargs)

        response = await self.client.post("/chat/completions", json=payload)
        response.raise_for_status()
        return response.json()

    async def completion(
        self,
        model: str,
        prompt: str,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        top_p: float = 0.9,
        stream: bool = False,
        stop: Optional[List[str]] = None,
        **kwargs
    ) -> Any:
        """Create a text completion (OpenAI-compatible)."""
        payload: Dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "temperature": temperature,
            "top_p": top_p,
            "stream": stream
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if stop is not None:
            payload["stop"] = stop
        payload.update(kwargs)

        response = await self.client.post("/completions", json=payload)
        response.raise_for_status()
        return response.json()

    async def embeddings(
        self,
        model: str,
        input: List[str],
        encoding_format: str = "float",
        **kwargs
    ) -> Any:
        """Create embeddings (OpenAI-compatible)."""
        payload: Dict[str, Any] = {
            "model": model,
            "input": input,
            "encoding_format": encoding_format
        }
        payload.update(kwargs)

        response = await self.client.post("/embeddings", json=payload)
        response.raise_for_status()
        return response.json()

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

# Synchronous wrapper for convenience
class NIMClientSync:
    def __init__(self, api_key: Optional[str] = None, base_url: str = "https://integrate.api.nvidia.com/v1"):
        self.api_key = api_key or os.getenv("NVIDIA_API_KEY")
        self.base_url = base_url.rstrip("/")
        if not self.api_key:
            raise ValueError("NVIDIA API key is required. Set NVIDIA_API_KEY environment variable or pass api_key.")
        self.client = httpx.Client(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            },
            timeout=30.0
        )

    def list_models(self) -> List[NIMModel]:
        response = self.client.get("/models")
        response.raise_for_status()
        data = response.json()
        return [NIMModel(**model) for model in data.get("data", [])]

    def chat_completion(
        self,
        model: str,
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        top_p: float = 0.9,
        stream: bool = False,
        stop: Optional[List[str]] = None,
        **kwargs
    ) -> Any:
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
            "stream": stream
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if stop is not None:
            payload["stop"] = stop
        payload.update(kwargs)

        response = self.client.post("/chat/completions", json=payload)
        response.raise_for_status()
        return response.json()

    def completion(
        self,
        model: str,
        prompt: str,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        top_p: float = 0.9,
        stream: bool = False,
        stop: Optional[List[str]] = None,
        **kwargs
    ) -> Any:
        payload: Dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "temperature": temperature,
            "top_p": top_p,
            "stream": stream
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if stop is not None:
            payload["stop"] = stop
        payload.update(kwargs)

        response = self.client.post("/completions", json=payload)
        response.raise_for_status()
        return response.json()

    def embeddings(
        self,
        model: str,
        input: List[str],
        encoding_format: str = "float",
        **kwargs
    ) -> Any:
        payload: Dict[str, Any] = {
            "model": model,
            "input": input,
            "encoding_format": encoding_format
        }
        payload.update(kwargs)

        response = self.client.post("/embeddings", json=payload)
        response.raise_for_status()
        return response.json()

    def close(self):
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

# Example usage
if __name__ == "__main__":
    import asyncio
    async def main():
        async with NIMClient() as nim:
            models = await nim.list_models()
            print(f"Available models: {len(models)}")
            for model in models[:5]:
                print(f"  - {model.id}")
    asyncio.run(main())