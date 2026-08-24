"""DEPRECATED: NVIDIA NIM client removed (AC-10 — NVIDIA is a TOTAL NO-GO).

This module intentionally raises ImportError on import so that any lingering
references to `app.services.nim_client` fail loudly. The platform now uses the
multi-provider free-tier adapter layer (see app.services.provider_service).
"""
raise ImportError(
    "app.services.nim_client has been removed: NVIDIA NIM is a TOTAL NO-GO (AC-10). "
    "Use app.services.provider_service instead."
)