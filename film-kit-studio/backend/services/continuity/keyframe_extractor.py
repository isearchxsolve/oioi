"""
Temporal Consistency — Keyframe extraction + motion trajectory tracking.

Ensures visual coherence across consecutive shots in a film.
"""

import logging
import tempfile
from pathlib import Path
from typing import Any, Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class ContinuityError(Exception):
    pass


# ════════════════════════════════════════════════════════════════════════════
# KEYFRAME EXTRACTOR
# ════════════════════════════════════════════════════════════════════════════

class KeyframeExtractor:
    """
    Extract representative keyframes from video clips for consistency checking
    and LoRA training dataset curation.
    """

    def __init__(
        self,
        max_keyframes: int = 10,
        scene_threshold: float = 30.0,
        quality_threshold: float = 0.5,
    ):
        self.max_keyframes = max_keyframes
        self.scene_threshold = scene_threshold
        self.quality_threshold = quality_threshold

    def extract(self, video_path: Path) -> list[dict[str, Any]]:
        """
        Extract keyframes from a video.
        
        Returns list of dicts with: frame_index, timestamp, image_path, quality_score, scene_id
        """
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise ContinuityError(f"Could not open video: {video_path}")

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30

        if total_frames == 0:
            cap.release()
            return []

        keyframes = []
        prev_gray = None
        scene_id = 0

        # Sample frames for scene detection
        sample_interval = max(1, total_frames // (self.max_keyframes * 5))

        for frame_idx in range(0, total_frames, sample_interval):
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret:
                break

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (21, 21), 0)

            quality = self._assess_quality(frame)

            if quality < self.quality_threshold:
                continue

            is_new_scene = False
            if prev_gray is not None:
                diff = cv2.absdiff(prev_gray, gray)
                score = np.sum(diff) / (diff.shape[0] * diff.shape[1])
                if score > self.scene_threshold:
                    is_new_scene = True
                    scene_id += 1

            # Save keyframe
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as f:
                cv2.imwrite(f.name, frame)
                keyframes.append({
                    'frame_index': frame_idx,
                    'timestamp': frame_idx / fps,
                    'image_path': f.name,
                    'quality_score': quality,
                    'scene_id': scene_id,
                    'is_scene_boundary': is_new_scene,
                })

            prev_gray = gray

            if len(keyframes) >= self.max_keyframes:
                break

        cap.release()
        return keyframes

    def _assess_quality(self, frame: np.ndarray) -> float:
        """Assess frame quality (sharpness, brightness, contrast)."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Laplacian variance for sharpness
        sharpness = cv2.Laplacian(gray, cv2.CV_64F).var()

        # Brightness (0-1, ideal ~0.5)
        brightness = np.mean(gray) / 255.0
        brightness_score = 1.0 - abs(brightness - 0.5) * 2

        # Contrast
        contrast = np.std(gray) / 255.0

        # Combined score
        score = (sharpness / 1000.0) * 0.5 + brightness_score * 0.3 + contrast * 0.2
        return min(1.0, max(0.0, score))


# ════════════════════════════════════════════════════════════════════════════
# MOTION TRAJECTORY TRACKER
# ════════════════════════════════════════════════════════════════════════════

class MotionTrajectoryTracker:
    """
    Track camera/object motion across consecutive shots to ensure
    consistent motion direction and speed.
    """

    def __init__(self):
        self.trajectories: dict[str, list[dict]] = {}  # object_id -> trajectory points

    def track_from_keyframes(
        self,
        keyframes: list[dict],
        reference_object: str = "camera",
    ) -> dict[str, Any]:
        """
        Analyze motion trajectory from extracted keyframes.
        
        Returns trajectory analysis with direction, speed, smoothness metrics.
        """
        if len(keyframes) < 2:
            return {'valid': False, 'reason': 'Need at least 2 keyframes'}

        # For camera motion, we'd use optical flow or feature matching
        # This is a simplified version using frame differences

        trajectories = []
        for i in range(1, len(keyframes)):
            prev_path = keyframes[i-1]['image_path']
            curr_path = keyframes[i]['image_path']

            prev_img = cv2.imread(prev_path)
            curr_img = cv2.imread(curr_path)

            if prev_img is None or curr_img is None:
                continue

            # Compute optical flow
            prev_gray = cv2.cvtColor(prev_img, cv2.COLOR_BGR2GRAY)
            curr_gray = cv2.cvtColor(curr_img, cv2.COLOR_BGR2GRAY)

            flow = cv2.calcOpticalFlowFarneback(
                prev_gray, curr_gray, None,
                pyr_scale=0.5, levels=3, winsize=15,
                iterations=3, poly_n=5, poly_sigma=1.2, flags=0
            )

            # Analyze flow
            magnitude, angle = cv2.cartToPolar(flow[..., 0], flow[..., 1])
            avg_magnitude = np.mean(magnitude)
            avg_angle = np.mean(angle)

            trajectories.append({
                'frame_pair': (keyframes[i-1]['frame_index'], keyframes[i]['frame_index']),
                'avg_magnitude': float(avg_magnitude),
                'avg_angle': float(avg_angle),
                'time_delta': keyframes[i]['timestamp'] - keyframes[i-1]['timestamp'],
            })

        # Aggregate trajectory
        if not trajectories:
            return {'valid': False, 'reason': 'No valid trajectories'}

        avg_speed = np.mean([t['avg_magnitude'] for t in trajectories])
        dominant_direction = np.mean([t['avg_angle'] for t in trajectories])
        smoothness = 1.0 - (np.std([t['avg_magnitude'] for t in trajectories]) / (avg_speed + 1e-6))

        return {
            'valid': True,
            'reference_object': reference_object,
            'avg_speed': float(avg_speed),
            'dominant_direction_rad': float(dominant_direction),
            'dominant_direction_deg': float(np.degrees(dominant_direction)),
            'smoothness': float(max(0, min(1, smoothness))),
            'trajectory_points': trajectories,
            'recommendations': self._generate_recommendations(avg_speed, dominant_direction, smoothness),
        }

    def _generate_recommendations(self, speed: float, direction: float, smoothness: float) -> list[str]:
        """Generate actionable recommendations for motion consistency."""
        recs = []
        if smoothness < 0.5:
            recs.append("Motion is jittery — consider stabilizing or re-generating with consistent camera move")
        if speed > 10:
            recs.append("Very fast motion — may cause temporal artifacts, consider slowing down")
        if speed < 0.5:
            recs.append("Very slow motion — ensure it's intentional, not frozen frames")
        return recs


# ════════════════════════════════════════════════════════════════════════════
# CHARACTER/APPEARANCE CONSISTENCY
# ════════════════════════════════════════════════════════════════════════════

class AppearanceConsistencyChecker:
    """
    Check character appearance consistency across frames/shots.
    Uses face/feature embedding comparison.
    """

    def __init__(self):
        self._face_analyzer = None

    def _load_analyzer(self):
        if self._face_analyzer is not None:
            return
        try:
            import insightface
            self._face_analyzer = insightface.app.FaceAnalysis(
                providers=['CPUExecutionProvider'],
                allowed_modules=['detection', 'recognition'],
            )
            self._face_analyzer.prepare(ctx_id=0, det_size=(640, 640))
        except ImportError:
            logger.warning("insightface not available for appearance checking")

    def check_character_consistency(
        self,
        keyframes: list[dict],
        character_name: str,
        reference_embedding: np.ndarray = None,
    ) -> dict[str, Any]:
        """
        Check if character appearance is consistent across keyframes.
        
        Returns consistency report with per-frame similarity scores.
        """
        self._load_analyzer()

        if self._face_analyzer is None:
            return {'valid': False, 'reason': 'Face analyzer not available'}

        similarities = []
        embeddings = []

        for kf in keyframes:
            img = cv2.imread(kf['image_path'])
            if img is None:
                continue

            faces = self._face_analyzer.get(img)
            if not faces:
                similarities.append({'frame': kf['frame_index'], 'similarity': 0.0, 'error': 'No face detected'})
                continue

            # Use largest face
            face = max(faces, key=lambda f: f.bbox[2] * f.bbox[3])
            embedding = face.embedding
            embeddings.append(embedding)

            if reference_embedding is not None:
                sim = np.dot(embedding, reference_embedding) / (
                    np.linalg.norm(embedding) * np.linalg.norm(reference_embedding)
                )
                similarities.append({
                    'frame': kf['frame_index'],
                    'similarity': float(sim),
                    'timestamp': kf['timestamp'],
                })

        # Compute statistics
        if similarities:
            sims = [s['similarity'] for s in similarities]
            avg_sim = np.mean(sims)
            min_sim = np.min(sims)
            consistency = 'high' if min_sim > 0.8 else 'medium' if min_sim > 0.6 else 'low'

            return {
                'valid': True,
                'character': character_name,
                'avg_similarity': float(avg_sim),
                'min_similarity': float(min_sim),
                'consistency_level': consistency,
                'per_frame': similarities,
                'recommendations': self._get_consistency_recommendations(consistency, min_sim),
            }

        return {'valid': False, 'reason': 'No valid comparisons'}

    def _get_consistency_recommendations(self, level: str, min_sim: float) -> list[str]:
        if level == 'low':
            return [
                f"Character appearance drifts significantly (min similarity: {min_sim:.2f})",
                "Re-generate problematic shots with character LoRA or reference image",
                "Ensure consistent lighting and camera angle across shots",
            ]
        elif level == 'medium':
            return [
                f"Some appearance variation detected (min similarity: {min_sim:.2f})",
                "Consider re-generating lowest-similarity shots",
            ]
        return ["Character appearance is consistent across shots"]


# ════════════════════════════════════════════════════════════════════════════
# LIGHTING/COLOR CONSISTENCY
# ════════════════════════════════════════════════════════════════════════════

class LightingColorConsistency:
    """Check lighting and color palette consistency across shots."""

    @staticmethod
    def analyze(keyframes: list[dict]) -> dict[str, Any]:
        """Analyze lighting and color consistency across keyframes."""
        if len(keyframes) < 2:
            return {'valid': False, 'reason': 'Need at least 2 keyframes'}

        color_stats = []
        lighting_stats = []

        for kf in keyframes:
            img = cv2.imread(kf['image_path'])
            if img is None:
                continue

            # Convert to LAB for lighting analysis
            lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
            l_mean = np.mean(lab[:, :, 0])  # Lightness
            a_mean = np.mean(lab[:, :, 1])  # Green-Red
            b_mean = np.mean(lab[:, :, 2])  # Blue-Yellow

            # Dominant colors (k-means on small sample)
            sample = img[::10, ::10].reshape(-1, 3)
            from sklearn.cluster import KMeans
            kmeans = KMeans(n_clusters=5, random_state=42, n_init=10)
            kmeans.fit(sample)
            dominant_colors = kmeans.cluster_centers_.astype(int)

            color_stats.append({
                'frame': kf['frame_index'],
                'dominant_colors': dominant_colors.tolist(),
                'lab_means': {'L': float(l_mean), 'a': float(a_mean), 'b': float(b_mean)},
            })

            lighting_stats.append({
                'lightness': float(l_mean / 255.0),
                'color_temp': float(a_mean / 255.0),  # Green-Red balance
                'tint': float(b_mean / 255.0),  # Blue-Yellow balance
            })

        # Compute consistency metrics
        if lighting_stats:
            lightness_vals = [s['lightness'] for s in lighting_stats]
            color_temp_vals = [s['color_temp'] for s in lighting_stats]

            lightness_std = np.std(lightness_vals)
            temp_std = np.std(color_temp_vals)

            consistency = 'high' if lightness_std < 0.1 and temp_std < 0.05 else \
                         'medium' if lightness_std < 0.2 and temp_std < 0.1 else 'low'

            return {
                'valid': True,
                'lightness_consistency': float(1.0 - min(1.0, lightness_std * 5)),
                'color_temp_consistency': float(1.0 - min(1.0, temp_std * 10)),
                'overall_consistency': consistency,
                'per_frame': color_stats,
                'recommendations': [
                    "Lighting shifts detected between shots" if lightness_std > 0.15 else "Lighting is consistent",
                    "Color temperature varies" if temp_std > 0.08 else "Color temperature stable",
                ],
            }

        return {'valid': False, 'reason': 'No valid frames for analysis'}


# ════════════════════════════════════════════════════════════════════════════
# CONTINUITY PIPELINE
# ════════════════════════════════════════════════════════════════════════════

async def run_continuity_check(
    clip_paths: list[Path],
    character_name: str = None,
    reference_image: Path = None,
) -> dict[str, Any]:
    """
    Run full continuity check on a sequence of clips.
    
    Returns comprehensive continuity report.
    """
    extractor = KeyframeExtractor(max_keyframes=20)
    tracker = MotionTrajectoryTracker()
    appearance_checker = AppearanceConsistencyChecker()
    lighting_checker = LightingColorConsistency()

    all_keyframes = []

    # Extract keyframes from each clip
    for clip_path in clip_paths:
        kfs = extractor.extract(clip_path)
        for kf in kfs:
            kf['clip'] = str(clip_path)
        all_keyframes.extend(kfs)

    # Sort by timestamp
    all_keyframes.sort(key=lambda x: x['timestamp'])

    # Run analyses
    motion = tracker.track_from_keyframes(all_keyframes)
    lighting = LightingColorConsistency.analyze(all_keyframes)

    result = {
        'total_keyframes': len(all_keyframes),
        'motion_analysis': motion,
        'lighting_color': lighting,
    }

    if character_name:
        # Get reference embedding if reference image provided
        ref_embedding = None
        if reference_image and reference_image.exists():
            import insightface
            analyzer = insightface.app.FaceAnalysis(providers=['CPUExecutionProvider'])
            analyzer.prepare(ctx_id=0, det_size=(640, 640))
            ref_img = cv2.imread(str(reference_image))
            faces = analyzer.get(ref_img)
            if faces:
                ref_embedding = max(faces, key=lambda f: f.bbox[2]*f.bbox[3]).embedding

        appearance = appearance_checker.check_character_consistency(
            all_keyframes,
            character_name,
            reference_embedding=ref_embedding,
        )
        result['character_appearance'] = appearance

    return result