"""
Director Planner — Uses Anthropic Claude 3.5 Sonnet to transform a logline
into a structured beat sheet and scene specifications.
"""

import json
import logging
from typing import Any, Optional

import anthropic

from config import settings
from services.director.prompts import (
    PLANNER_SYSTEM_PROMPT,
    build_planner_user_prompt,
)

logger = logging.getLogger(__name__)


class PlannerError(Exception):
    pass


class DirectorPlanner:
    """
    Planner agent that converts a logline/idea into:
    - Beat sheet (narrative structure)
    - Scene specs (per-shot visual + audio instructions)
    - Continuity setup (characters, locations, palette)
    """

    def __init__(self):
        self.api_key = settings.anthropic_api_key
        self.model = settings.anthropic_model or "claude-3-5-sonnet-20241022"
        self._client: Optional[anthropic.AsyncAnthropic] = None

    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def _get_client(self) -> anthropic.AsyncAnthropic:
        if self._client is None:
            if not self.is_configured():
                raise PlannerError("ANTHROPIC_API_KEY not set")
            self._client = anthropic.AsyncAnthropic(api_key=self.api_key)
        return self._client

    async def generate_plan(
        self,
        idea: str,
        genre: str = "drama",
        target_duration: float = 60.0,
        beats_per_minute: float = 1.5,
        existing_continuity: Optional[dict] = None,
        max_retries: int = 3,
    ) -> dict[str, Any]:
        """
        Generate a complete director plan from a logline.

        Returns dict with keys: beats, scene_specs, continuity_setup
        """
        if not self.is_configured():
            raise PlannerError("ANTHROPIC_API_KEY not configured")

        client = await self._get_client()

        user_prompt = build_planner_user_prompt(
            idea=idea,
            genre=genre,
            target_duration=target_duration,
            beats_per_minute=beats_per_minute,
            existing_continuity=existing_continuity,
        )

        last_error: Exception | None = None

        for attempt in range(max_retries):
            try:
                logger.info(f"Planner attempt {attempt + 1}/{max_retries} for: {idea[:80]}...")

                response = await client.messages.create(
                    model=self.model,
                    max_tokens=8192,
                    temperature=0.3,  # Low temp for structured output consistency
                    system=PLANNER_SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": user_prompt}],
                )

                # Extract JSON from response
                content = response.content[0].text if response.content else ""
                plan = self._parse_json_response(content)

                # Validate structure
                self._validate_plan(plan)
                logger.info(f"Planner success: {len(plan['beats'])} beats, {len(plan['scene_specs'])} scenes")
                return plan

            except (json.JSONDecodeError, ValueError, PlannerError) as e:
                last_error = e
                logger.warning(f"Planner attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    import asyncio
                    await asyncio.sleep(2 ** attempt)

        raise PlannerError(f"Planner failed after {max_retries} attempts: {last_error}")

    def _parse_json_response(self, content: str) -> dict[str, Any]:
        """Extract and parse JSON from Claude response."""
        # Claude sometimes wraps in markdown code blocks
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            # Try to find JSON object in the response
            start = content.find("{")
            end = content.rfind("}")
            if start >= 0 and end > start:
                try:
                    return json.loads(content[start:end + 1])
                except json.JSONDecodeError:
                    pass
            raise PlannerError(f"Failed to parse JSON from planner response: {e}")

    def _validate_plan(self, plan: dict[str, Any]) -> None:
        """Validate the plan has required structure."""
        required_keys = {"beats", "scene_specs", "continuity_setup"}
        missing = required_keys - set(plan.keys())
        if missing:
            raise PlannerError(f"Plan missing required keys: {missing}")

        if not isinstance(plan["beats"], list) or not plan["beats"]:
            raise PlannerError("Plan must have at least one beat")

        if not isinstance(plan["scene_specs"], list):
            raise PlannerError("scene_specs must be a list")

        # Validate each beat has required fields
        for i, beat in enumerate(plan["beats"]):
            beat_required = {"slug", "type", "title", "description", "duration_seconds", "mood", "characters", "location"}
            missing = beat_required - set(beat.keys())
            if missing:
                raise PlannerError(f"Beat {i} missing fields: {missing}")

        # Validate each scene spec
        for i, scene in enumerate(plan["scene_specs"]):
            scene_required = {"beat_id", "index_in_beat", "visual_prompt", "shot_type", "duration_seconds"}
            missing = scene_required - set(scene.keys())
            if missing:
                raise PlannerError(f"Scene spec {i} missing fields: {missing}")

        # Validate continuity
        cont = plan["continuity_setup"]
        if not isinstance(cont.get("characters"), list):
            raise PlannerError("continuity_setup.characters must be a list")
        if not isinstance(cont.get("locations"), list):
            raise PlannerError("continuity_setup.locations must be a list")


# ═══════════════════════════════════════════════════════════════════════════
# SYNCHRONOUS WRAPPER (for non-async contexts)
# ═══════════════════════════════════════════════════════════════════════════

def generate_plan_sync(
    idea: str,
    genre: str = "drama",
    target_duration: float = 60.0,
    beats_per_minute: float = 1.5,
    existing_continuity: Optional[dict] = None,
) -> dict[str, Any]:
    """Sync wrapper for planner — runs in thread pool."""
    import asyncio
    planner = DirectorPlanner()
    return asyncio.run(planner.generate_plan(
        idea=idea,
        genre=genre,
        target_duration=target_duration,
        beats_per_minute=beats_per_minute,
        existing_continuity=existing_continuity,
    ))