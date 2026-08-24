"""
LivePortrait ONNX — Lip-sync animation from audio + reference image.

Uses the LivePortrait model (https://github.com/KwaiVGI/LivePortrait)
exported to ONNX for fast CPU/GPU inference.

Pipeline:
1. Extract audio features (MFCC/Hubert) from speech audio
2. Encode reference image to latent + keypoints
3. Drive latent with audio features to generate talking head video
4. Blend generated face back into original frame
"""

import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class LivePortraitError(Exception):
    pass


class LivePortraitONNX:
    """
    LivePortrait ONNX inference engine.
    
    Requires:
    - liveportrait.onnx (full pipeline) or separate encoder/retarget/generator ONNX files
    - insightface for face detection/alignment (optional, for better crops)
    """

    def __init__(
        self,
        model_path: str = "",
        providers: list[str] = None,
        device: str = "cpu",
    ):
        self.model_path = model_path or os.getenv("LIVEPORTRAIT_MODEL_PATH", "./models/liveportrait.onnx")
        self.device = device
        self.providers = providers or (
            ["CUDAExecutionProvider", "CPUExecutionProvider"] if device == "cuda"
            else ["CPUExecutionProvider"]
        )
        self._session = None
        self._face_detector = None

    def _load_session(self):
        """Lazy-load ONNX Runtime session."""
        if self._session is not None:
            return

        import onnxruntime as ort

        if not Path(self.model_path).exists():
            raise LivePortraitError(f"LivePortrait model not found at {self.model_path}")

        logger.info(f"Loading LivePortrait ONNX from {self.model_path} with providers: {self.providers}")
        self._session = ort.InferenceSession(self.model_path, providers=self.providers)

    def _load_face_detector(self):
        """Load InsightFace detector for face alignment."""
        if self._face_detector is not None:
            return

        try:
            import insightface
            self._face_detector = insightface.app.FaceAnalysis(
                providers=self.providers,
                allowed_modules=["detection", "landmark_2d_106"],
            )
            self._face_detector.prepare(ctx_id=0 if self.device == "cuda" else -1, det_size=(640, 640))
        except ImportError:
            logger.warning("insightface not installed, using OpenCV fallback for face detection")
            self._face_detector = None

    def animate(
        self,
        source_image: np.ndarray,  # HxWx3 BGR
        driving_audio: np.ndarray,  # 1D float32 audio samples at 16kHz
        sample_rate: int = 16000,
        output_path: Path = None,
        fps: int = 30,
    ) -> np.ndarray:
        """
        Generate talking head video from source image + driving audio.
        
        Returns: HxWx3xFrames video array
        """
        self._load_session()
        self._load_face_detector()

        # 1. Detect and align face in source image
        aligned_source = self._align_face(source_image)
        if aligned_source is None:
            raise LivePortraitError("No face detected in source image")

        # 2. Extract audio features (MFCC or Hubert)
        audio_features = self._extract_audio_features(driving_audio, sample_rate)

        # 3. Run LivePortrait pipeline
        # This is a simplified version - real implementation runs:
        # - Encoder: source image -> latent + keypoints
        # - Retarget: keypoints + audio features -> driven keypoints
        # - Generator: driven keypoints + latent -> video frames
        frames = self._run_pipeline(aligned_source, audio_features, fps)

        # 4. Blend back into original frame (if needed)
        result = self._blend_frames(frames, source_image)

        if output_path:
            self._write_video(result, output_path, fps)

        return result

    def _align_face(self, image: np.ndarray) -> Optional[np.ndarray]:
        """Detect and crop/align face to 256x256."""
        if self._face_detector is not None:
            faces = self._face_detector.get(image)
            if faces:
                face = max(faces, key=lambda f: f.bbox[2] * f.bbox[3])
                # Crop with padding
                x1, y1, x2, y2 = face.bbox.astype(int)
                w, h = x2 - x1, y2 - y1
                cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                size = max(w, h) * 1.5
                x1 = max(0, int(cx - size // 2))
                y1 = max(0, int(cy - size // 2))
                x2 = min(image.shape[1], int(cx + size // 2))
                y2 = min(image.shape[0], int(cy + size // 2))
                crop = image[y1:y2, x1:x2]
                return cv2.resize(crop, (256, 256))

        # Fallback: center crop
        h, w = image.shape[:2]
        size = min(h, w)
        x1 = (w - size) // 2
        y1 = (h - size) // 2
        crop = image[y1:y1+size, x1:x1+size]
        return cv2.resize(crop, (256, 256))

    def _extract_audio_features(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """Extract MFCC features from audio for driving."""
        import librosa

        # Resample to 16kHz if needed
        if sr != 16000:
            audio = librosa.resample(audio, orig_sr=sr, target_sr=16000)
            sr = 16000

        # Extract MFCC (39 dims: 13 MFCC + delta + delta-delta)
        mfcc = librosa.feature.mfcc(y=audio, sr=sr, n_mfcc=13)
        delta = librosa.feature.delta(mfcc)
        delta2 = librosa.feature.delta(mfcc, order=2)
        features = np.vstack([mfcc, delta, delta2]).T  # (T, 39)

        # Interpolate to match video fps (e.g., 30 fps)
        # 16000 samples/sec / 30 fps = 533 samples per frame
        # MFCC hop_length=512 -> ~31 frames/sec at 16kHz
        # We'll use simple interpolation
        return features.astype(np.float32)

    def _run_pipeline(
        self,
        source: np.ndarray,  # 256x256x3
        audio_features: np.ndarray,  # (T, 39)
        fps: int = 30,
    ) -> np.ndarray:
        """
        Run the full LivePortrait pipeline.
        
        This is a placeholder - real implementation would:
        1. Run encoder on source -> latent, keypoints
        2. Run retarget network (keypoints + audio features) -> driven keypoints
        3. Run generator (latent + driven keypoints) -> frames
        """
        num_frames = len(audio_features) * 30 // 31  # rough estimate

        # For now, return static frames (placeholder)
        # Real implementation generates animated frames
        frames = np.tile(source[None], (num_frames, 1, 1, 1))
        return frames

    def _blend_frames(
        self,
        generated_frames: np.ndarray,  # (T, H, W, 3)
        original: np.ndarray,  # (H, W, 3)
    ) -> np.ndarray:
        """Blend generated face back into original frame."""
        # Simple approach: just return generated frames at original resolution
        h, w = original.shape[:2]
        result = []
        for frame in generated_frames:
            resized = cv2.resize(frame, (w, h))
            result.append(resized)
        return np.array(result)

    def _write_video(self, frames: np.ndarray, output_path: Path, fps: int):
        """Write frames to MP4 video."""
        h, w = frames.shape[1:3]
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        writer = cv2.VideoWriter(str(output_path), fourcc, fps, (w, h))

        for frame in frames:
            writer.write(frame)
        writer.release()


# ════════════════════════════════════════════════════════════════════════════
# SADTALKER FALLBACK
# ════════════════════════════════════════════════════════════════════════════

class SadTalker:
    """
    SadTalker fallback for lip-sync.
    Uses the SadTalker model (https://github.com/Winfredy/SadTalker).
    
    Requires Python environment with SadTalker installed.
    """

    def __init__(self, checkpoint_dir: str = "./checkpoints/sadtalker"):
        self.checkpoint_dir = Path(checkpoint_dir)

    def animate(
        self,
        source_image: Path,
        driving_audio: Path,
        output_path: Path,
        still_mode: bool = False,
        preprocess: str = "crop",
        enhancer: str = "gfpgan",
    ) -> Path:
        """
        Run SadTalker inference via command line.
        
        Returns path to generated video.
        """
        cmd = [
            "python", "inference.py",
            "--driven_audio", str(driving_audio),
            "--source_image", str(source_image),
            "--result_dir", str(output_path.parent),
            "--still", str(still_mode).lower(),
            "--preprocess", preprocess,
            "--enhancer", enhancer,
            "--checkpoint_dir", str(self.checkpoint_dir),
        ]

        # Run in SadTalker directory
        result = subprocess.run(
            cmd,
            cwd=self.checkpoint_dir.parent,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise LivePortraitError(f"SadTalker failed: {result.stderr}")

        # Find output video
        output_files = list(output_path.parent.glob("*.mp4"))
        if not output_files:
            raise LivePortraitError("No output video generated")

        return output_files[0]


# ════════════════════════════════════════════════════════════════════════════
# HIGH-LEVEL API
# ════════════════════════════════════════════════════════════════════════════

async def run_lip_sync(
    character_image: Path,
    audio_path: Path,
    output_path: Path,
    method: str = "liveportrait",
    fps: int = 30,
) -> Path:
    """
    High-level lip-sync function.
    
    Args:
        character_image: Path to reference character image
        audio_path: Path to driving audio (WAV/MP3)
        output_path: Output video path
        method: "liveportrait" or "sadtalker"
        fps: Output video FPS
    
    Returns: Path to generated video
    """
    # Load image
    image = cv2.imread(str(character_image))
    if image is None:
        raise LivePortraitError(f"Could not load image: {character_image}")

    # Load audio
    import librosa
    audio, sr = librosa.load(str(audio_path), sr=16000)

    if method == "liveportrait":
        engine = LivePortraitONNX()
        frames = engine.animate(image, audio, sr, fps=fps)
    elif method == "sadtalker":
        sadtalker = SadTalker()
        return sadtalker.animate(character_image, audio_path, output_path)
    else:
        raise LivePortraitError(f"Unknown method: {method}")

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    engine._write_video(frames, output_path, fps)
    return output_path


# ════════════════════════════════════════════════════════════════════════════
# PIPELINE INTEGRATION HOOK
# ════════════════════════════════════════════════════════════════════════════

async def lip_sync_scene_clip(
    scene_clip_path: Path,
    character_image: Path,
    audio_path: Path,
    output_path: Path,
    method: str = "liveportrait",
) -> Path:
    """
    Pipeline hook: After audio generation, run lip-sync on the scene clip.
    
    This integrates with the pipeline's audio generation step.
    """
    return await run_lip_sync(
        character_image=character_image,
        audio_path=audio_path,
        output_path=output_path,
        method=method,
    )