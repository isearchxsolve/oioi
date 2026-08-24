"""DEPRECATED: NVIDIA NIM model registry removed (AC-10 — NVIDIA is a TOTAL NO-GO).

The model registry now lives in the unified provider adapter layer. See
backend/openrouter_adapter.py and backend/groq_adapter.py.
"""
raise ImportError(
    "backend.nim_models has been removed: NVIDIA NIM is a TOTAL NO-GO (AC-10). "
    "Use the unified provider adapter layer instead."
)