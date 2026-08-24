"""DEPRECATED: NVIDIA NIM integration removed (AC-10 — NVIDIA is a TOTAL NO-GO).

This module previously contained an async NVIDIA NIM client. It has been
removed because NVIDIA NIM endpoints are forbidden anywhere in the codebase.
The platform now uses the multi-provider free-tier adapter layer.
"""
raise ImportError(
    "backend.nim_integration has been removed: NVIDIA NIM is a TOTAL NO-GO (AC-10). "
    "Use backend.openrouter_adapter.OpenRouterAdapter or backend.groq_adapter.GroqAdapter instead."
)