"""
Visual generation providers.

Pluggable backends for generating scene visuals, selected by the
VISUAL_PROVIDER setting + presence of the relevant API key.

    cosmos   — NVIDIA Cosmos3 NIM (free default; Physical-AI model)
    veo      — Google Veo 3.1 via the Gemini API (cinematic, native audio)
    kling    — Kling 3.0 first-party API (strong long-form + image-to-video)

All providers implement the VisualProvider protocol in base.py and expose
the same generate_visual() signature that services/pipeline.py expects.
"""

from services.visual_providers.registry import generate_visual, get_visual_provider  # noqa: F401
