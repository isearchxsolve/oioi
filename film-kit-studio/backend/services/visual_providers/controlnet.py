"""
ControlNet preprocessing & unified interface for visual providers.

Provides a consistent API across Veo, Kling, Cosmos for:
- Canny edge detection
- Depth estimation (MiDaS/ZoeDepth)
- OpenPose human pose
- Normal maps (surface orientation)
- LineArt extraction
- Tile/QRCode (future)

Each provider maps these to their native ControlNet format.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# CONTROLNET TYPES
# ═══════════════════════════════════════════════════════════════════════════

class ControlNetType(str):
    CANNY = "canny"
    DEPTH = "depth"
    OPENPOSE = "openpose"
    NORMAL = "normal"
    LINEART = "lineart"
    TILE = "tile"
    QRCODE = "qrcode"


@dataclass
class ControlNetInput:
    """Single ControlNet conditioning input."""
    type: ControlNetType
    image_path: Path
    scale: float = 1.0          # Conditioning strength (0-2)
    guidance_start: float = 0.0 # When to start applying (0-1)
    guidance_end: float = 1.0   # When to stop applying (0-1)

    def to_provider_format(self, provider: str) -> dict[str, Any]:
        """Convert to provider-specific format."""
        if provider == "veo":
            return self._to_veo()
        elif provider == "kling":
            return self._to_kling()
        elif provider == "cosmos":
            return self._to_cosmos()
        else:
            return {"type": self.type, "image": str(self.image_path), "scale": self.scale}

    def _to_veo(self) -> dict:
        """Veo 3.1 native ControlNet format."""
        # Veo uses control_video_reference + control_type
        type_map = {
            ControlNetType.CANNY: "CANNY",
            ControlNetType.DEPTH: "DEPTH",
            ControlNetType.OPENPOSE: "POSE",
            ControlNetType.NORMAL: "NORMAL",
            ControlNetType.LINEART: "LINEART",
        }
        return {
            "control_video_reference": str(self.image_path),
            "control_type": type_map.get(self.type, "CANNY"),
            "control_strength": self.scale,
        }

    def _to_kling(self) -> dict:
        """Kling 3.0 ControlNet format."""
        # Kling uses controlnet_conditioning array
        return {
            "type": self.type,
            "image": str(self.image_path),
            "scale": self.scale,
            "guidance_start": self.guidance_start,
            "guidance_end": self.guidance_end,
        }

    def _to_cosmos(self) -> dict:
        """Cosmos IMAGE2WORLD ControlNet format."""
        # Cosmos uses controlnet_images[] with type + scale
        return {
            "type": self.type,
            "image": str(self.image_path),
            "scale": self.scale,
        }


# ═══════════════════════════════════════════════════════════════════════════
# PREPROCESSORS
# ═══════════════════════════════════════════════════════════════════════════

class ControlNetPreprocessor:
    """
    Extract ControlNet conditioning images from source frames.
    Uses OpenCV + MediaPipe + MiDaS (via torch hub).
    """

    def __init__(self, device: str = "cpu"):
        self.device = device
        self._midas = None
        self._pose = None
        self._lineart = None

    # ─────────────────────────────────────────────────────────────────────
    # CANNY EDGES
    # ─────────────────────────────────────────────────────────────────────

    def canny(self, image: np.ndarray, low_thresh: int = 100, high_thresh: int = 200) -> np.ndarray:
        """Standard Canny edge detection."""
        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        edges = cv2.Canny(gray, low_thresh, high_thresh)
        # Invert for white edges on black (typical ControlNet format)
        edges = 255 - edges
        return cv2.cvtColor(edges, cv2.COLOR_GRAY2RGB)

    # ─────────────────────────────────────────────────────────────────────
    # DEPTH (MiDaS via torch.hub)
    # ─────────────────────────────────────────────────────────────────────

    def _load_midas(self):
        if self._midas is None:
            import torch
            self._midas = torch.hub.load("intel-isl/MiDaS", "MiDaS_small", trust_repo=True)
            self._midas.to(self.device).eval()
            self._midas_transform = torch.hub.load("intel-isl/MiDaS", "transforms", trust_repo=True).small_transform

    def depth(self, image: np.ndarray) -> np.ndarray:
        """MiDaS depth estimation → normalized depth map."""
        import torch

        self._load_midas()

        # Transform
        input_tensor = self._midas_transform(image).to(self.device)

        with torch.no_grad():
            prediction = self._midas(input_tensor)
            prediction = torch.nn.functional.interpolate(
                prediction.unsqueeze(1),
                size=image.shape[:2],
                mode="bicubic",
                align_corners=False,
            ).squeeze()

        depth = prediction.cpu().numpy()
        # Normalize to 0-255
        depth = (depth - depth.min()) / (depth.max() - depth.min() + 1e-8)
        depth = (depth * 255).astype(np.uint8)
        return cv2.cvtColor(depth, cv2.COLOR_GRAY2RGB)

    # ─────────────────────────────────────────────────────────────────────
    # OPENPOSE (MediaPipe)
    # ─────────────────────────────────────────────────────────────────────

    def _load_pose(self):
        if self._pose is None:
            import mediapipe as mp
            self._pose = mp.solutions.pose.Pose(
                static_image_mode=True,
                model_complexity=2,
                enable_segmentation=False,
                min_detection_confidence=0.5,
            )
            self._mp_drawing = mp.solutions.drawing_utils
            self._mp_pose = mp.solutions.pose

    def openpose(self, image: np.ndarray, draw_bg: bool = False) -> np.ndarray:
        """MediaPipe Pose → OpenPose-format skeleton."""
        import mediapipe as mp

        self._load_pose()

        h, w = image.shape[:2]
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        results = self._pose.process(rgb)

        # Black background
        output = np.zeros((h, w, 3), dtype=np.uint8) if not draw_bg else image.copy()

        if results.pose_landmarks:
            # Draw connections
            self._mp_drawing.draw_landmarks(
                output,
                results.pose_landmarks,
                self._mp_pose.POSE_CONNECTIONS,
                self._mp_drawing.DrawingSpec(color=(255, 255, 255), thickness=2, circle_radius=2),
                self._mp_drawing.DrawingSpec(color=(255, 255, 255), thickness=2),
            )

        return output

    # ─────────────────────────────────────────────────────────────────────
    # NORMAL MAPS (via depth gradients)
    # ─────────────────────────────────────────────────────────────────────

    def normal(self, image: np.ndarray) -> np.ndarray:
        """Estimate normal map from depth gradients."""
        depth = self.depth(image).astype(np.float32) / 255.0
        gray = cv2.cvtColor(depth, cv2.COLOR_RGB2GRAY)

        # Sobel gradients
        dx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        dy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)

        # Normal = (-dx, -dy, 1) normalized
        normal = np.dstack([-dx, -dy, np.ones_like(gray)])
        norm = np.linalg.norm(normal, axis=2, keepdims=True) + 1e-8
        normal = normal / norm

        # Map to 0-255
        normal_vis = ((normal + 1) * 127.5).astype(np.uint8)
        return normal_vis

    # ─────────────────────────────────────────────────────────────────────
    # LINEART (Anime/clean lines)
    # ─────────────────────────────────────────────────────────────────────

    def _load_lineart(self):
        if self._lineart is None:
            # Use a simple edge-preserving filter as fallback
            # For production, load AnimeGAN/LineArt model
            pass

    def lineart(self, image: np.ndarray) -> np.ndarray:
        """Anime-style line art extraction."""
        # Simple but effective: bilateral filter + adaptive threshold
        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        smooth = cv2.bilateralFilter(gray, 9, 75, 75)
        edges = cv2.adaptiveThreshold(
            smooth, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            blockSize=9, C=2
        )
        return cv2.cvtColor(edges, cv2.COLOR_GRAY2RGB)

    # ─────────────────────────────────────────────────────────────────────
    # TILE / QR CODE (placeholder)
    # ─────────────────────────────────────────────────────────────────────

    def tile(self, image: np.ndarray) -> np.ndarray:
        """Tile/upscale conditioning - returns original."""
        return image

    def qrcode(self, image: np.ndarray) -> np.ndarray:
        """QR code detection - placeholder."""
        return image


# ═══════════════════════════════════════════════════════════════════════════
# HIGH-LEVEL API
# ═══════════════════════════════════════════════════════════════════════════

def extract_controlnet_images(
    source_image: Path,
    types: list[ControlNetType],
    output_dir: Path,
    device: str = "cpu",
) -> dict[ControlNetType, Path]:
    """
    Extract all requested ControlNet conditioning images from a source frame.

    Args:
        source_image: Path to reference frame
        types: List of ControlNet types to extract
        output_dir: Where to save conditioning images
        device: "cpu" or "cuda"

    Returns:
        Dict mapping ControlNetType -> saved image path
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load source
    img = cv2.imread(str(source_image))
    if img is None:
        raise ValueError(f"Could not load image: {source_image}")
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    preprocessor = ControlNetPreprocessor(device=device)
    results = {}

    for ctype in types:
        logger.info(f"Extracting {ctype} from {source_image.name}")

        if ctype == ControlNetType.CANNY:
            processed = preprocessor.canny(img)
        elif ctype == ControlNetType.DEPTH:
            processed = preprocessor.depth(img)
        elif ctype == ControlNetType.OPENPOSE:
            processed = preprocessor.openpose(img)
        elif ctype == ControlNetType.NORMAL:
            processed = preprocessor.normal(img)
        elif ctype == ControlNetType.LINEART:
            processed = preprocessor.lineart(img)
        elif ctype == ControlNetType.TILE:
            processed = preprocessor.tile(img)
        elif ctype == ControlNetType.QRCODE:
            processed = preprocessor.qrcode(img)
        else:
            logger.warning(f"Unknown ControlNet type: {ctype}")
            continue

        # Save
        out_path = output_dir / f"{source_image.stem}_{ctype}.png"
        cv2.imwrite(str(out_path), cv2.cvtColor(processed, cv2.COLOR_RGB2BGR))
        results[ctype] = out_path

    return results


def build_controlnet_inputs(
    conditioning_images: dict[ControlNetType, Path],
    scales: Optional[dict[ControlNetType, float]] = None,
) -> list[ControlNetInput]:
    """Build ControlNetInput list from extracted images."""
    scales = scales or {}
    return [
        ControlNetInput(
            type=ctype,
            image_path=path,
            scale=scales.get(ctype, 1.0),
        )
        for ctype, path in conditioning_images.items()
    ]


# ═══════════════════════════════════════════════════════════════════════════
# PROVIDER MAPPING HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def controlnet_to_veo(inputs: list[ControlNetInput]) -> list[dict]:
    """Convert to Veo 3.1 control_video_reference format."""
    return [inp.to_provider_format("veo") for inp in inputs]


def controlnet_to_kling(inputs: list[ControlNetInput]) -> list[dict]:
    """Convert to Kling 3.0 controlnet_conditioning format."""
    return [inp.to_provider_format("kling") for inp in inputs]


def controlnet_to_cosmos(inputs: list[ControlNetInput]) -> list[dict]:
    """Convert to Cosmos IMAGE2WORLD controlnet_images format."""
    return [inp.to_provider_format("cosmos") for inp in inputs]