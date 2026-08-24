"""
Continuity Tracker — Enforces cross-scene visual consistency.
"""

import logging
from typing import Any, Optional

from services.director.models import (
    SceneSpec,
    ContinuityState,
    CharacterAppearance,
    LocationProfile,
)

logger = logging.getLogger(__name__)


class ContinuityTracker:
    """
    Tracks and enforces visual continuity across scenes:
    - Character appearance (face, build, wardrobe, props)
    - Location consistency (lighting, time of day, features)
    - Global style (color palette, lighting mood)
    """

    def __init__(self):
        self.state = ContinuityState()

    def initialize_from_plan(self, continuity_setup: dict[str, Any]) -> None:
        """Initialize from planner's continuity_setup output."""
        # Characters
        for char_data in continuity_setup.get("characters", []):
            name = char_data.get("name", "")
            if not name:
                continue
            self.state.characters[name] = CharacterAppearance(
                name=name,
                description=char_data.get("description", ""),
                reference_image_path=char_data.get("reference_image_path"),
                lora_path=char_data.get("lora_path"),
                wardrobe=char_data.get("wardrobe", {}),
                props=char_data.get("props", {}),
            )

        # Locations
        for loc_data in continuity_setup.get("locations", []):
            name = loc_data.get("name", "")
            if not name:
                continue
            self.state.locations[name] = LocationProfile(
                name=name,
                description=loc_data.get("description", ""),
                reference_image_path=loc_data.get("reference_image_path"),
                time_of_day=loc_data.get("time_of_day", "day"),
                lighting_setup=loc_data.get("lighting_setup", "natural"),
                weather=loc_data.get("weather", "clear"),
                key_features=loc_data.get("key_features", []),
            )

        # Global
        self.state.global_lighting_mood = continuity_setup.get("global_lighting_mood", "cinematic")
        self.state.color_palette = continuity_setup.get("color_palette", [])

    def get_character_prompt_additions(self, scene: SceneSpec) -> dict[str, Any]:
        """Get continuity data for characters in this scene."""
        additions = {
            "character_descriptions": {},
            "lora_paths": {},
            "wardrobe": {},
            "props": {},
        }

        for char_name in scene.characters:
            char = self.state.get_character(char_name)
            additions["character_descriptions"][char_name] = char.description

            if char.lora_path:
                additions["lora_paths"][char_name] = char.lora_path

            # Wardrobe for this scene's beat
            scene_slug = scene.beat_id
            if scene_slug in char.wardrobe:
                additions["wardrobe"][char_name] = char.wardrobe[scene_slug]

            if scene_slug in char.props:
                additions["props"][char_name] = char.props[scene_slug]

        return additions

    def get_location_prompt_additions(self, scene: SceneSpec) -> dict[str, Any]:
        """Get continuity data for this scene's location."""
        loc = self.state.get_location(scene.location)

        return {
            "location_description": loc.description,
            "time_of_day": loc.time_of_day,
            "lighting_setup": loc.lighting_setup,
            "weather": loc.weather,
            "key_features": loc.key_features,
            "reference_image": loc.reference_image_path,
        }

    def get_global_style(self) -> dict[str, Any]:
        return {
            "global_lighting_mood": self.state.global_lighting_mood,
            "color_palette": self.state.color_palette,
        }

    def update_after_generation(self, scene: SceneSpec, scene_index: int, generated_clip_path: str) -> ContinuityState:
        """Update state after a scene is generated."""
        # Update character last-seen
        for char_name in scene.characters:
            char = self.state.get_character(char_name)
            char.last_seen_scene = scene_index

        # Update location last-used
        loc = self.state.get_location(scene.location)
        loc.last_used_scene = scene_index
        loc.time_of_day = scene.time_of_day

        return self.state

    def get_consistency_report(self) -> dict[str, Any]:
        """Generate a report on continuity health."""
        return {
            "characters": {
                name: {
                    "consistency_score": char.consistency_score,
                    "scenes_appeared": sum(1 for _ in char.wardrobe) + sum(1 for _ in char.props),
                    "last_seen_scene": char.last_seen_scene,
                }
                for name, char in self.state.characters.items()
            },
            "locations": {
                name: {
                    "scenes_used": sum(1 for _ in loc.key_features) if loc.key_features else 0,
                    "last_used_scene": loc.last_used_scene,
                }
                for name, loc in self.state.locations.items()
            },
            "global_palette": self.state.color_palette,
        }


def enforce_continuity_on_spec(scene: SceneSpec, continuity: ContinuityState) -> SceneSpec:
    """
    Modify a SceneSpec to include continuity-enforcing additions.
    Returns a NEW SceneSpec (doesn't mutate input).
    """
    # Create a copy
    updated = SceneSpec(**scene.dict())

    # Character additions
    char_additions = {}
    for char_name in scene.characters:
        char = continuity.get_character(char_name)
        if char.description:
            char_additions.setdefault("character_descriptions", {})[char_name] = char.description
        if char.lora_path:
            char_additions.setdefault("lora_paths", {})[char_name] = char.lora_path

        scene_slug = scene.beat_id
        if scene_slug in char.wardrobe:
            char_additions.setdefault("wardrobe", {})[char_name] = char.wardrobe[scene_slug]
        if scene_slug in char.props:
            char_additions.setdefault("props", {})[char_name] = char.props[scene_slug]

    if char_additions:
        updated.visual_prompt += "\n\nCONTINUITY ENFORCEMENT:\n"
        if "character_descriptions" in char_additions:
            for name, desc in char_additions["character_descriptions"].items():
                updated.visual_prompt += f"- Character {name}: {desc}\n"
        if "wardrobe" in char_additions:
            for name, outfit in char_additions["wardrobe"].items():
                updated.visual_prompt += f"- {name} wears: {outfit}\n"
        if "props" in char_additions:
            for name, props in char_additions["props"].items():
                updated.visual_prompt += f"- {name} holds: {', '.join(props)}\n"

    # Location additions
    loc = continuity.get_location(scene.location)
    loc_parts = []
    if loc.description:
        loc_parts.append(f"Location: {loc.description}")
    if loc.time_of_day:
        loc_parts.append(f"Time: {loc.time_of_day}")
    if loc.lighting_setup:
        loc_parts.append(f"Lighting: {loc.lighting_setup}")
    if loc.weather:
        loc_parts.append(f"Weather: {loc.weather}")
    if loc.key_features:
        loc_parts.append(f"Key features: {', '.join(loc.key_features)}")

    if loc_parts:
        updated.visual_prompt += "\nLOCATION CONTINUITY:\n" + "\n".join(loc_parts) + "\n"

    # Global style
    if continuity.global_lighting_mood:
        updated.visual_prompt += f"\nGLOBAL MOOD: {continuity.global_lighting_mood}\n"
    if continuity.color_palette:
        updated.visual_prompt += f"COLOR PALETTE: {', '.join(continuity.color_palette)}\n"

    return updated