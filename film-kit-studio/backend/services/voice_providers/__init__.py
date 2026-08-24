"""
Voice / narration providers.

Pluggable TTS backends, selected by VOICE_PROVIDER + presence of API keys:

    edge        — Microsoft edge-tts (free default, keyless)
    elevenlabs  — ElevenLabs TTS (dramatically more natural + emotional)

All providers implement VoiceProvider (base.py) and expose the same
synthesize_narration() signature that services/tts.py used.
"""

from services.voice_providers.registry import synthesize_narration, get_voice_provider  # noqa: F401
