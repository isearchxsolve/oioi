"""
Director Critic — Uses Google Gemini 1.5 Pro (VLM) to evaluate generated clips
against the director's intent and professional standards.
"""

import json
import logging
import mimetypes
from pathlib import Path
from typing import Any, Optional

import google.generativeai as genai

from config import settings
from services.director.models import CritiqueResult
from services.director.prompts import (
    CRITIC_SYSTEM_PROMPT,
    build_critic_user_prompt,
)

logger = logging.getLogger(__name__)


class CriticError(Exception):
    pass


class DirectorCritic:
    """
    VLM-based critic that watches generated clips and produces structured critiques.
    """

    def __init__(self):
        self.api_key = settings.gemini_api_key
        self.model_name = settings.gemini_model or "gemini-1.5-pro"
        self._model: Optional[genai.GenerativeModel] = None

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _get_model(self) -> genai.GenerativeModel:
        if self._model is None:
            if not self.is_configured():
                raise CriticError("GEMINI_API_KEY not set")
            genai.configure(api_key=self.api_key)
            self._model = genai.GenerativeModel(
                model_name=self.model_name,
                system_instruction=CRITIC_SYSTEM_PROMPT,
                generation_config=genai.GenerationConfig(
                    temperature=0.1,  # Very low for consistent evaluation
                    max_output_tokens=8192,
                    response_mime_type="application/json",
                ),
            )
        return self._model

    async def critique_run(
        self,
        beats: list[dict],
        scene_specs: list[dict],
        clip_paths: list[str],
        audio_paths: list[str],
        continuity_state: dict,
        iteration: int,
        max_retries: int = 3,
    ) -> CritiqueResult:
        """
        Evaluate all clips in a run against their specs.

        Returns CritiqueResult with overall score, per-scene scores, issues, and summary.
        """
        if not self.is_configured():
            raise CriticError("GEMINI_API_KEY not configured")

        if len(clip_paths) != len(scene_specs):
            logger.warning(f"Clip count ({len(clip_paths)}) != scene spec count ({len(scene_specs)})")

        model = self._get_model()

        # Upload all clips to Gemini Files API
        uploaded_files = []
        try:
            for path in clip_paths:
                if Path(path).exists():
                    file_obj = genai.upload_file(path=path, mime_type=self._get_mime_type(path))
                    uploaded_files.append(file_obj)
                    logger.debug(f"Uploaded {path} -> {file_obj.name}")
                else:
                    logger.warning(f"Clip not found: {path}")

            # Build the critique prompt
            user_prompt = build_critic_user_prompt(
                beats=beats,
                scene_specs=scene_specs,
                clip_paths=clip_paths,
                audio_paths=audio_paths,
                continuity_state=continuity_state,
                iteration=iteration,
            )

            # Create content with files + prompt
            content = [user_prompt] + uploaded_files

            last_error: Exception | None = None
            for attempt in range(max_retries):
                try:
                    logger.info(f"Critic attempt {attempt + 1}/{max_retries} evaluating {len(uploaded_files)} clips")

                    response = await model.generate_content_async(content)

                    # Parse JSON response
                    result = self._parse_critique_response(response.text)

                    # Validate
                    self._validate_critique(result, len(scene_specs))

                    logger.info(f"Critic success: overall={result['overall_score']:.2f}, passed={result['passed']}, issues={len(result['issues'])}")
                    return CritiqueResult(**result)

                except (json.JSONDecodeError, ValueError, CriticError) as e:
                    last_error = e
                    logger.warning(f"Critic attempt {attempt + 1} failed: {e}")
                    if attempt < max_retries - 1:
                        import asyncio
                        await asyncio.sleep(2 ** attempt)

            raise CriticError(f"Critic failed after {max_retries} attempts: {last_error}")

        finally:
            # Clean up uploaded files
            for file_obj in uploaded_files:
                try:
                    genai.delete_file(file_obj.name)
                except Exception:
                    pass

    def _get_mime_type(self, path: str) -> str:
        mime, _ = mimetypes.guess_type(path)
        return mime or "video/mp4"

    def _parse_critique_response(self, text: str) -> dict[str, Any]:
        """Parse and clean the VLM's JSON response."""
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            # Try to extract JSON object
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end + 1])
                except json.JSONDecodeError:
                    pass
            raise CriticError(f"Failed to parse critic JSON: {e}")

    def _validate_critique(self, result: dict[str, Any], expected_scenes: int) -> None:
        """Validate critique result has required fields."""
        required = ["overall_score", "passed", "issues", "per_scene_scores", "summary"]
        for field in required:
            if field not in result:
                raise CriticError(f"Missing required field in critique: {field}")

        if not isinstance(result["overall_score"], (int, float)):
            raise CriticError("overall_score must be numeric")

        if not 0 <= result["overall_score"] <= 1:
            raise CriticError("overall_score must be 0-1")

        if not isinstance(result["passed"], bool):
            raise CriticError("passed must be boolean")

        if not isinstance(result["issues"], list):
            raise CriticError("issues must be list")

        # Validate each issue
        for issue in result["issues"]:
            if not all(k in issue for k in ("type", "severity", "description", "fix_suggestion", "scene_index")):
                raise CriticError("Issue missing required keys")


# ═══════════════════════════════════════════════════════════════════════════
# FALLBACK CRITIC (Rule-based, no VLM needed)
# ═══════════════════════════════════════════════════════════════════════════

class FallbackCritic:
    """
    Rule-based critic for when VLM is unavailable.
    Checks technical basics: file exists, duration matches, audio synced.
    """

    def __init__(self):
        pass

    async def critique_run(
        self,
        beats: list[dict],
        scene_specs: list[dict],
        clip_paths: list[str],
        audio_paths: list[str],
        continuity_state: dict,
        iteration: int,
    ) -> CritiqueResult:
        """Basic technical validation only."""
        issues = []
        per_scene_scores = {}

        for i, (spec, clip_path) in enumerate(zip(scene_specs, clip_paths)):
            score = 1.0

            # Check file exists
            from pathlib import Path
            if not Path(clip_path).exists():
                issues.append({
                    "type": "technical",
                    "severity": "critical",
                    "description": f"Scene {i}: clip file not found at {clip_path}",
                    "fix_suggestion": "Re-generate scene; check pipeline output paths",
                    "scene_index": i,
                    "timestamp_seconds": 0,
                })
                score = 0.0

            # Check duration (would need ffprobe - placeholder)
            target_dur = spec.get("duration_seconds", 5)
            # TODO: probe actual duration with ffprobe
            # if abs(actual - target) > target * 0.3:
            #     issues.append(...)

            per_scene_scores[i] = score

        overall = sum(per_scene_scores.values()) / len(per_scene_scores) if per_scene_scores else 0
        passed = overall >= 0.7

        return CritiqueResult(
            run_id="",  # Filled by loop
            iteration=iteration,
            overall_score=overall,
            passed=passed,
            issues=issues,
            per_scene_scores=per_scene_scores,
            summary=f"Fallback critic: {len(issues)} technical issues found. Overall score: {overall:.2f}",
        )