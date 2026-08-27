"""Durable hand-off from the seven-stage creative crew to a FilmJobStore graph.

The older animation workflow returned a useful collection of crew responses, but
left those responses beside a separate render workflow.  This module makes the
Director's approved package an explicit, validated input to :class:`FilmRequest`.
It makes no provider calls and does not generate character art; approved character
reference URLs remain caller-owned inputs relayed by the Film Pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional

from .orchestrator import FilmOrchestrator, FilmRequest


class CrewHandoffError(ValueError):
    """The crew package cannot responsibly be admitted to the render graph."""


def _mapping(value: Any, name: str) -> Dict[str, Any]:
    if hasattr(value, "dict"):
        value = value.dict()
    if not isinstance(value, Mapping):
        raise CrewHandoffError(f"{name} output must be an object")
    return dict(value)


def _items(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _text(*values: Any) -> str:
    return " ".join(str(value).strip() for value in values if str(value or "").strip())


def _scene_number(value: Any, default: int) -> int:
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return default


def _scene_durations(scenes: Iterable[Dict[str, Any]]) -> List[int]:
    durations: List[int] = []
    for scene in scenes:
        try:
            duration = int(scene.get("duration", 5))
        except (TypeError, ValueError):
            duration = 5
        durations.append(max(1, duration))
    return durations


def _sound_effects(
    raw_effects: Iterable[Dict[str, Any]], durations: List[int], target_seconds: int
) -> List[Dict[str, Any]]:
    """Convert scene-labelled Sound Director output to timeline-local Foley events."""
    starts = [0]
    for duration in durations:
        starts.append(starts[-1] + duration)
    result: List[Dict[str, Any]] = []
    for index, effect in enumerate(raw_effects):
        scene = _scene_number(effect.get("scene"), index + 1)
        scene_index = min(len(starts) - 1, scene - 1) if starts else 0
        try:
            length = float(effect.get("durationSeconds", effect.get("duration", 1.5)))
        except (TypeError, ValueError):
            length = 1.5
        description = _text(
            effect.get("description"), effect.get("sfx"), effect.get("effect"), effect.get("prompt")
        ) or "scene foley"
        result.append({
            "scene": scene,
            "startSeconds": min(max(0, starts[scene_index] if starts else 0), target_seconds),
            "durationSeconds": max(0.08, min(12.0, length)),
            "description": description,
        })
    return result


@dataclass(frozen=True)
class ApprovedCrewHandoff:
    """The replayable creative package and the request it deterministically creates."""

    request: FilmRequest
    title: str
    crew_snapshot: Dict[str, Any]


def build_approved_crew_handoff(
    crew_outputs: Mapping[str, Any],
    *,
    target_seconds: Optional[int] = None,
    aspect_ratio: str = "16:9",
    character_refs: Optional[Dict[str, Any]] = None,
    image_refs: Optional[List[str]] = None,
) -> ApprovedCrewHandoff:
    """Build a durable film request only after the Director explicitly approves it.

    The stored bible retains the approved screenplay, art direction, character and
    scene design, storyboard, animation plan, and sound plan.  That is intentional:
    recovery/replanning has the actual crew decisions rather than merely a flattened
    prompt.  Character *prompts* are retained as design notes, while only supplied
    approved URLs are passed as image references.
    """
    if not isinstance(crew_outputs, Mapping):
        raise CrewHandoffError("crew outputs must be a mapping keyed by crew role")
    required = (
        "scriptwriter", "art_director", "character_designer", "scene_designer",
        "storyboard_artist", "animator", "sound_director", "director",
    )
    missing = [name for name in required if name not in crew_outputs]
    if missing:
        raise CrewHandoffError(f"crew handoff is missing stage output: {', '.join(missing)}")

    scriptwriter = _mapping(crew_outputs["scriptwriter"], "scriptwriter")
    art = _mapping(crew_outputs["art_director"], "art director")
    characters = _mapping(crew_outputs["character_designer"], "character designer")
    scene_design = _mapping(crew_outputs["scene_designer"], "scene designer")
    storyboard = _mapping(crew_outputs["storyboard_artist"], "storyboard artist")
    animation = _mapping(crew_outputs["animator"], "animator")
    sound = _mapping(crew_outputs["sound_director"], "sound director")
    director = _mapping(crew_outputs["director"], "director")
    if director.get("approved") is not True:
        revisions = director.get("revisions") or []
        raise CrewHandoffError(
            "Director has not approved this package"
            + (f"; revisions: {', '.join(map(str, revisions))}" if revisions else "")
        )

    script_scenes = _items(scriptwriter.get("scenes"))
    scene_items = _items(scene_design.get("scenes"))
    panels = _items(storyboard.get("panels"))
    animations = _items(animation.get("animations"))
    if not script_scenes:
        raise CrewHandoffError("approved Scriptwriter output has no scenes")
    durations = _scene_durations(script_scenes)
    inferred_duration = sum(durations)
    target = max(5, int(target_seconds if target_seconds is not None else inferred_duration))

    screenplay_parts = [
        f"TITLE: {_text(scriptwriter.get('title')) or 'Untitled'}",
        _text(scriptwriter.get("description")),
        f"DIRECTOR NOTES: {_text(director.get('final_notes'))}",
    ]
    for number, scene in enumerate(script_scenes, start=1):
        design = scene_items[number - 1] if number <= len(scene_items) else {}
        panel = next((entry for entry in panels if _scene_number(entry.get("scene"), 0) == number), {})
        motion = next((entry for entry in animations if _scene_number(entry.get("scene"), 0) == number), {})
        screenplay_parts.append(
            f"SCENE {number} ({durations[number - 1]} seconds): "
            + _text(
                scene.get("description"), scene.get("prompt"), design.get("description"), design.get("prompt"),
                panel.get("composition"), panel.get("camera"), panel.get("action"),
                motion.get("prompt"), motion.get("action"),
            )
        )
    screenplay = "\n".join(part for part in screenplay_parts if part)

    designed_characters = _items(characters.get("characters"))
    character_bible = {
        _text(character.get("name")) or f"character-{index + 1}": {
            "description": _text(character.get("description")),
            "designPrompt": _text(character.get("prompt")),
        }
        for index, character in enumerate(designed_characters)
    }
    effects = _sound_effects(_items(sound.get("sound_effects")), durations, target)
    snapshot = {
        "scriptwriter": scriptwriter,
        "art_director": art,
        "character_designer": characters,
        "scene_designer": scene_design,
        "storyboard_artist": storyboard,
        "animator": animation,
        "sound_director": sound,
        "director": director,
    }
    bible = {
        "style": _text(art.get("visual_style")) or "cinematic",
        "palette": list(art.get("color_palette") or []),
        "characters": character_bible,
        "locations": [
            _text(scene.get("description"), scene.get("prompt")) for scene in scene_items if _text(scene.get("description"), scene.get("prompt"))
        ],
        "imageRefs": list(image_refs or []),
        "characterRefs": dict(character_refs or {}),
        "soundPlan": {
            "musicPrompt": _text(sound.get("music_prompt")),
            "voiceOver": _text(sound.get("voice_over")),
            "effects": effects,
        },
        "crew": snapshot,
    }
    request = FilmRequest(
        script=screenplay,
        target_seconds=target,
        aspect_ratio=aspect_ratio,
        style=str(bible["style"]),
        image_refs=list(image_refs or []),
        character_refs=dict(character_refs or {}),
        bible=bible,
    )
    return ApprovedCrewHandoff(request=request, title=str(scriptwriter.get("title") or "Untitled"), crew_snapshot=snapshot)


async def admit_approved_crew_film(
    orchestrator: FilmOrchestrator,
    crew_outputs: Mapping[str, Any],
    **kwargs: Any,
) -> Dict[str, Any]:
    """Persist the approved crew package and its planned shots in ``FilmJobStore``."""
    handoff = build_approved_crew_handoff(crew_outputs, **kwargs)
    admission = await orchestrator.request_film(handoff.request)
    # ``request_film`` intentionally returns a compact form on an idempotent replay.
    # The crew endpoint has one stable admission contract, so expose its acceptance
    # truth on both first admission and replay rather than forcing an API caller to
    # infer it from a nested status.
    admission.setdefault(
        "accepted",
        str((admission.get("film") or {}).get("status") or "")
        not in {"refused_capacity", "refused_safety_cap", "failed", "assembly_error"},
    )
    return {
        "title": handoff.title,
        "admission": admission,
        "directorApproved": True,
    }


__all__ = [
    "ApprovedCrewHandoff",
    "CrewHandoffError",
    "admit_approved_crew_film",
    "build_approved_crew_handoff",
]
