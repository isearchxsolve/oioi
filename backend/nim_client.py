"""DEPRECATED: NVIDIA NIM client removed (AC-10 — NVIDIA is a TOTAL NO-GO).

This module intentionally raises ImportError on import so that any lingering
references to `backend.nim_client` fail loudly. The platform now uses the
multi-provider free-tier adapter layer (see backend/openrouter_adapter.py and
backend/groq_adapter.py) instead of NVIDIA NIM.
"""
raise ImportError(
    "backend.nim_client has been removed: NVIDIA NIM is a TOTAL NO-GO (AC-10). "
    "Use backend.openrouter_adapter.OpenRouterAdapter or backend.groq_adapter.GroqAdapter instead."
)