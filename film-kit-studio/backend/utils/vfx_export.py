"""
VFX Export — Alpha plates, depth, normal, motion vectors, UDIM layout.

Exports render passes for VFX integration (Nuke, Houdini, Blender, etc.).
Requires video generation with render passes (currently placeholder).
"""

import logging
import shutil
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class VFXExportError(Exception):
    pass


async def export_alpha_plates(
    src: Path,
    output_dir: Path,
    beauty_name: str = "beauty",
) -> dict[str, Path]:
    """
    Export VFX plates from rendered clip.
    
    Requires the source to have been rendered with render passes.
    For Film Kit Studio, this exports:
    - Beauty (RGB)
    - Alpha (from reference image if available)
    - Depth (from video model if available)
    - Normal (from video model if available)
    - Motion Vectors (from video model if available)
    
    Placeholder for production - requires render passes from video model.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Copy beauty as-is
    beauty_out = output_dir / f"{beauty_name}.mov"
    shutil.copy2(src, beauty_out)
    
    # Placeholder plates
    results = {"beauty": beauty_out}
    
    # Note: Actual alpha/depth/normal/motion would come from video generation
    # This is a placeholder structure
    
    return results


async def export_udim_layout(
    texture_dir: Path,
    output_dir: Path,
) -> Path:
    """Export UDIM texture layout for 3D integration."""
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "UDIM_LAYOUT.txt").write_text(
        "UDIM layout placeholder - requires 3D render passes"
    )
    return output_dir