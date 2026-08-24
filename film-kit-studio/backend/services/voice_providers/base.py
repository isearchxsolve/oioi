"""
VoiceProvider protocol — the contract every TTS backend implements.
"""

from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class VoiceProvider(Protocol):
    """A pluggable text-to-speech narration backend."""

    @property
    def name(self) -> str:
        """Human-readable provider name (e.g. 'edge', 'elevenlabs')."""
        ...

    def is_configured(self) -> bool:
        """True if this provider has the credentials it needs to run."""
        ...

    async def synthesize(
        self,
        text: str,
        voice_key: str,
        out_path: Path,
    ) -> float:
        """
        Synthesize narration audio and write it to out_path.

        Returns the audio duration in seconds.
        """
        ...
