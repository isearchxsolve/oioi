"""
MusicProvider protocol — the contract every score backend implements.
"""

from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class MusicProvider(Protocol):
    """A pluggable background-score generation backend."""

    @property
    def name(self) -> str:
        """Human-readable provider name (e.g. 'ffmpeg', 'suno')."""
        ...

    def is_configured(self) -> bool:
        """True if this provider has the credentials it needs to run."""
        ...

    async def generate(
        self,
        duration: float,
        out_path: Path,
        mood: str = "ambient",
    ) -> Path:
        """
        Generate a background score of approximately `duration` seconds
        and write it to out_path. Returns the output path.
        """
        ...
