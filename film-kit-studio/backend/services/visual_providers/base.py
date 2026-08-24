"""
VisualProvider protocol — the contract every visual backend implements.

Kept deliberately minimal so providers can be swapped via config without
services/pipeline.py caring which one is active.
"""

from pathlib import Path
from typing import Any, Callable, Coroutine, Optional, Protocol, runtime_checkable

# Type alias for the async progress callback: (fraction_0_to_1, message)
ProgressCallback = Optional[Callable[[float, str], Coroutine[Any, Any, None]]]


@runtime_checkable
class VisualProvider(Protocol):
    """A pluggable visual/video generation backend."""

    @property
    def name(self) -> str:
        """Human-readable provider name (e.g. 'cosmos', 'veo')."""
        ...

    def is_configured(self) -> bool:
        """True if this provider has the credentials it needs to run."""
        ...

    async def generate(
        self,
        visual_prompt: str,
        out_path: Path,
        aspect: str = "16:9",
        seed: Optional[int] = None,
        duration_seconds: float = 4.0,
        max_retries: int = 3,
        progress_callback: ProgressCallback = None,
        reference_image: Optional[Path] = None,
        controlnet_images: Optional[dict[str, Path]] = None,
        lora_path: Optional[str] = None,
        lora_scale: float = 1.0,
    ) -> str:
        """
        Generate a short clip (or image fallback) and write it to out_path.

        Args:
            visual_prompt: The text prompt describing the visual
            out_path: Output file path
            aspect: Aspect ratio (e.g., "16:9", "9:16", "1:1")
            seed: Random seed for reproducibility
            duration_seconds: Desired duration of generated clip
            max_retries: Maximum retry attempts
            progress_callback: Optional async callback for progress updates
            reference_image: Optional reference image path for character consistency (image-to-video)
            controlnet_images: Optional dict of ControlNet conditionings:
                {"canny": Path, "depth": Path, "pose": Path, "normal": Path, "lineart": Path}
            lora_path: Optional path to LoRA weights for character/style consistency
            lora_scale: LoRA strength scale (0.0-2.0)

        Returns:
            The path to the generated file (str).
        Raises:
            Provider-specific exception on failure.
        """
        ...
