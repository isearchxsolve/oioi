"""
Music / score providers.

Pluggable background-score backends, selected by MUSIC_PROVIDER + API key:

    ffmpeg — enriched synthesised ambient bed (free default)
    suno   — real instrumental score via a Suno gateway provider

All providers implement MusicProvider (base.py) and expose
generate_score() with a uniform signature.
"""

from services.music_providers.registry import generate_score, get_music_provider  # noqa: F401
