"""
Dataset Curator for LoRA Training.

Automatically extracts and prepares training images from:
- Generated video frames (keyframe extraction)
- User-uploaded reference images
- Existing project assets
"""

import logging
import shutil
from pathlib import Path
from typing import Any, Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class DatasetCuratorError(Exception):
    pass


class DatasetCurator:
    """
    Curates and prepares training datasets for LoRA/DreamBooth training.
    
    Pipeline:
    1. Collect source images (generated clips, uploads, project assets)
    2. Extract keyframes from videos (scene changes, high quality frames)
    3. Detect and crop faces/characters
    4. Apply augmentations (flip, color jitter, crop)
    5. Generate captions (BLIP or manual)
    6. Organize into kohya-ss compatible structure
    """

    def __init__(self, project_dir: Path):
        self.project_dir = Path(project_dir)
        self.dataset_dir = self.project_dir / "training" / "dataset"
        self.dataset_dir.mkdir(parents=True, exist_ok=True)

        # Subdirectories for kohya-ss format
        self.images_dir = self.dataset_dir / "images"
        self.captions_dir = self.dataset_dir / "captions"
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.captions_dir.mkdir(parents=True, exist_ok=True)

    # ═══════════════════════════════════════════════════════════════════════════
    # MAIN CURATION PIPELINE
    # ═══════════════════════════════════════════════════════════════════════════

    def curate_from_project(
        self,
        character_name: str,
        video_paths: list[Path],
        reference_images: list[Path],
        target_count: int = 50,
        caption_template: str = "{character}, {description}",
    ) -> dict[str, Any]:
        """
        Full curation pipeline from project assets.
        
        Returns stats dict with counts and paths.
        """
        logger.info(f"Curating dataset for character '{character_name}' from {len(video_paths)} videos + {len(reference_images)} refs")

        all_frames = []

        # 1. Extract frames from videos
        for video_path in video_paths:
            frames = self._extract_keyframes(video_path, max_frames=target_count // len(video_paths) + 5)
            all_frames.extend(frames)
            logger.info(f"  Extracted {len(frames)} frames from {video_path.name}")

        # 2. Add reference images
        for ref_path in reference_images:
            if ref_path.exists():
                all_frames.append({
                    "image": ref_path,
                    "source": "reference",
                    "quality": 1.0,
                })

        # 3. Score and select best frames
        selected = self._score_and_select(all_frames, target_count, character_name)

        # 4. Process selected frames (crop, resize, augment)
        processed = self._process_frames(selected, character_name)

        # 5. Generate captions
        self._generate_captions(processed, caption_template, character_name)

        # 6. Create dataset metadata
        metadata = self._create_metadata(character_name, len(processed))

        return {
            "dataset_dir": str(self.dataset_dir),
            "images_dir": str(self.images_dir),
            "captions_dir": str(self.captions_dir),
            "image_count": len(processed),
            "metadata": metadata,
            "frames": processed,
        }

    # ═══════════════════════════════════════════════════════════════════════════
    # KEYFRAME EXTRACTION
    # ═══════════════════════════════════════════════════════════════════════════

    def _extract_keyframes(self, video_path: Path, max_frames: int = 10) -> list[dict]:
        """Extract high-quality keyframes from a video using scene detection."""
        frames = []

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            logger.warning(f"Could not open video: {video_path}")
            return frames

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)

        if total_frames == 0:
            cap.release()
            return frames

        # Sample frames at intervals, prioritizing:
        # - First frame
        # - Middle frames
        # - Scene changes (high frame difference)
        # - Last frame

        frame_indices = set()

        # Always include first and last
        frame_indices.add(0)
        frame_indices.add(total_frames - 1)

        # Evenly spaced
        for i in range(max_frames):
            frame_indices.add(int(i * total_frames / max_frames))

        # Scene change detection (sample every 15 frames)
        prev_frame = None
        for i in range(0, total_frames, max(1, total_frames // 100)):
            cap.set(cv2.CAP_PROP_POS_FRAMES, i)
            ret, frame = cap.read()
            if not ret:
                continue

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (21, 21), 0)

            if prev_frame is not None:
                diff = cv2.absdiff(prev_frame, gray)
                score = np.sum(diff) / (diff.shape[0] * diff.shape[1])
                if score > 30:  # Scene change threshold
                    frame_indices.add(i)

            prev_frame = gray

            if len(frame_indices) >= max_frames * 2:
                break

        # Extract selected frames
        for idx in sorted(frame_indices):
            if idx >= total_frames:
                continue
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            if not ret:
                continue

            # Save frame
            frame_path = self.images_dir / f"{video_path.stem}_frame_{idx:06d}.jpg"
            cv2.imwrite(str(frame_path), frame)

            # Quality assessment
            quality = self._assess_frame_quality(frame)

            frames.append({
                "image": frame_path,
                "source": "video",
                "video": video_path,
                "frame_index": idx,
                "timestamp": idx / fps if fps > 0 else 0,
                "quality": quality,
            })

            if len(frames) >= max_frames:
                break

        cap.release()
        return frames

    def _assess_frame_quality(self, frame: np.ndarray) -> float:
        """Assess frame quality (sharpness, brightness, contrast)."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Laplacian variance for sharpness
        sharpness = cv2.Laplacian(gray, cv2.CV_64F).var()

        # Brightness (avoid too dark/bright)
        brightness = np.mean(gray) / 255.0
        brightness_score = 1.0 - abs(brightness - 0.5) * 2

        # Contrast
        contrast = np.std(gray) / 255.0

        # Combined score (normalized)
        score = min(1.0, (sharpness / 1000.0) * 0.5 + brightness_score * 0.3 + contrast * 0.2)
        return max(0.0, min(1.0, score))

    # ═══════════════════════════════════════════════════════════════════════════
    # SELECTION & PROCESSING
    # ═══════════════════════════════════════════════════════════════════════════

    def _score_and_select(self, frames: list[dict], target_count: int, character_name: str) -> list[dict]:
        """Score frames and select best ones for training."""
        # Prioritize: reference images > high quality frames > diverse timestamps
        scored = []

        for frame in frames:
            score = frame.get("quality", 0.5)

            # Boost reference images
            if frame.get("source") == "reference":
                score += 0.5

            # Diversity bonus (spread across video)
            if frame.get("source") == "video":
                timestamp = frame.get("timestamp", 0)
                # Prefer frames spread across the video
                score += 0.1

            scored.append((score, frame))

        # Sort by score descending
        scored.sort(key=lambda x: x[0], reverse=True)

        # Select top frames, ensuring some diversity
        selected = []
        used_timestamps = set()

        for score, frame in scored:
            if len(selected) >= target_count:
                break

            # For video frames, ensure temporal diversity
            if frame.get("source") == "video":
                ts_bucket = int(frame.get("timestamp", 0) / 5)  # 5-second buckets
                if ts_bucket in used_timestamps and len(selected) > target_count * 0.7:
                    continue
                used_timestamps.add(ts_bucket)

            selected.append(frame)

        logger.info(f"Selected {len(selected)} frames from {len(frames)} candidates")
        return selected

    def _process_frames(self, frames: list[dict], character_name: str) -> list[dict]:
        """Process frames: crop faces, resize, augment."""
        processed = []

        for i, frame in enumerate(frames):
            src_path = frame["image"]
            if not src_path.exists():
                continue

            # Load image
            img = cv2.imread(str(src_path))
            if img is None:
                continue

            # Detect and crop face/character region
            cropped = self._crop_character_region(img, character_name)

            # Resize to training resolution (512x512 for SD)
            resized = cv2.resize(cropped, (512, 512), interpolation=cv2.INTER_LANCZOS4)

            # Save processed image
            out_name = f"{character_name}_{i:04d}.jpg"
            out_path = self.images_dir / out_name
            cv2.imwrite(str(out_path), resized, [cv2.IMWRITE_JPEG_QUALITY, 95])

            processed.append({
                "image": out_path,
                "original": src_path,
                "index": i,
                "source": frame.get("source", "unknown"),
            })

            # TODO: Add augmentations (flip, color jitter, etc.) for more training data

        return processed

    def _crop_character_region(self, img: np.ndarray, character_name: str) -> np.ndarray:
        """Detect and crop character region (face/upper body)."""
        # Try face detection first
        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, 1.1, 4)

        if len(faces) > 0:
            # Use largest face
            x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
            # Expand to include upper body
            expand = int(h * 1.5)
            x1 = max(0, x - expand)
            y1 = max(0, y - expand)
            x2 = min(img.shape[1], x + w + expand)
            y2 = min(img.shape[0], y + h + expand * 2)  # More body
            return img[y1:y2, x1:x2]

        # Fallback: center crop
        h, w = img.shape[:2]
        size = min(h, w)
        x1 = (w - size) // 2
        y1 = (h - size) // 2
        return img[y1:y1+size, x1:x1+size]

    # ═══════════════════════════════════════════════════════════════════════════
    # CAPTIONS & METADATA
    # ═══════════════════════════════════════════════════════════════════════════

    def _generate_captions(
        self,
        frames: list[dict],
        template: str,
        character_name: str,
    ) -> None:
        """Generate caption text files for each image."""
        for frame in frames:
            img_path = frame["image"]
            caption_path = self.captions_dir / (img_path.stem + ".txt")

            # Simple template - in production, use BLIP for auto-captioning
            caption = template.format(
                character=character_name,
                description="portrait, detailed face, high quality, cinematic lighting",
            )

            caption_path.write_text(caption)

    def _create_metadata(self, character_name: str, image_count: int) -> dict[str, Any]:
        """Create dataset metadata for tracking."""
        import json

        metadata = {
            "character": character_name,
            "image_count": image_count,
            "resolution": "512x512",
            "format": "jpg",
            "caption_format": "text",
            "created_at": datetime.utcnow().isoformat(),
            "source": "film_kit_studio",
        }

        meta_path = self.dataset_dir / "metadata.json"
        meta_path.write_text(json.dumps(metadata, indent=2))

        return metadata


# ════════════════════════════════════════════════════════════════════════════
# AUTO-CAPTIONING (BLIP)
# ════════════════════════════════════════════════════════════════════════════

class AutoCaptioner:
    """Auto-caption images using BLIP or similar models."""

    def __init__(self):
        self._processor = None
        self._model = None

    def _load_blip(self):
        if self._model is None:
            try:
                from transformers import BlipProcessor, BlipForConditionalGeneration
                import torch
                self._processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base")
                self._model = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-base")
                if torch.cuda.is_available():
                    self._model = self._model.cuda()
            except ImportError:
                logger.warning("transformers not installed, skipping auto-captioning")

    def caption_image(self, image_path: Path, character_name: str = "") -> str:
        """Generate caption for an image."""
        self._load_blip()
        if self._model is None:
            return f"{character_name}, portrait, detailed face, cinematic lighting"

        from PIL import Image
        import torch

        image = Image.open(image_path).convert("RGB")
        inputs = self._processor(image, return_tensors="pt")
        if torch.cuda.is_available():
            inputs = {k: v.cuda() for k, v in inputs.items()}

        with torch.no_grad():
            out = self._model.generate(**inputs, max_length=50)

        caption = self._processor.decode(out[0], skip_special_tokens=True)
        return f"{character_name}, {caption}" if character_name else caption