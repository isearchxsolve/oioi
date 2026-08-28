"""Deterministic, cached screenplay-to-shot decomposition and shot deduplication."""
from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any, Dict, Iterable, List, Optional

from .clients import ChatPoolClient
from .models import ShotSpec


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def stable_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def merge_image_refs(*groups: Iterable[Any]) -> List[str]:
    """Return stable, de-duplicated visual reference URLs in editorial order."""
    result: List[str] = []
    seen: set[str] = set()
    for group in groups:
        for raw in group:
            value = str(raw or "").strip()
            if value and value not in seen:
                seen.add(value)
                result.append(value)
    return result


def normalize_character_refs(value: Optional[Dict[str, Any]]) -> Dict[str, List[str]]:
    """Normalise the durable character-reference manifest supplied by the crew/API.

    Supports the documented ``sheetUrl`` / ``portraitUrls`` shape as well as a simple
    list of URLs.  The Film Pipeline only relays approved URLs; it never invents a
    character image or calls an image provider while planning.
    """
    normalized: Dict[str, List[str]] = {}
    for name, raw in (value or {}).items():
        values: List[Any] = []
        if isinstance(raw, dict):
            values.append(raw.get("sheetUrl"))
            values.extend(raw.get("portraitUrls") or [])
            values.extend(raw.get("imageRefs") or [])
        elif isinstance(raw, (list, tuple, set)):
            values.extend(raw)
        else:
            values.append(raw)
        refs = merge_image_refs(values)
        if refs:
            normalized[str(name)] = refs
    return normalized


def enrich_bible_references(bible: Dict[str, Any], character_refs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Persist approved character art in the bible and attach it to every shot."""
    enriched = dict(bible or {})
    normalized = normalize_character_refs(character_refs if character_refs is not None else enriched.get("characterRefs"))
    if normalized:
        enriched["characterRefs"] = normalized
    elif "characterRefs" in enriched:
        enriched["characterRefs"] = {}
    enriched["imageRefs"] = merge_image_refs(
        enriched.get("imageRefs") or [], *(normalized.values()),
    )
    return enriched


def job_key_for_shot(shot: ShotSpec, *, canonical_index: int) -> str:
    """Caller-side stable idempotency key required by the frozen video contract.

    The index is the canonical/source shot index.  Repeated shots reference the same
    canonical index so one render is reusable, while a materially distinct shot at a
    later position cannot accidentally collide with it.
    """
    return stable_hash({
        "prompt": normalize_prompt(shot.prompt), "duration": int(shot.duration_seconds),
        "imageRefs": sorted(shot.image_refs), "seed": shot.seed, "shotIndex": int(canonical_index),
    })


def request_key_for_film(
    *, script: str, target_seconds: int, aspect_ratio: str, bible: Dict[str, Any], seed: Optional[int],
    tenant_scope: Optional[str] = None,
) -> str:
    return stable_hash({
        "script": script.strip(), "targetSeconds": int(target_seconds), "aspectRatio": aspect_ratio,
        "bible": bible, "seed": seed, "tenantScope": tenant_scope or "",
    })


_WORD = re.compile(r"[a-z0-9]+")


def normalize_prompt(prompt: str) -> str:
    """Stable prompt text for a *job key*, without using it for creative deduplication."""
    return " ".join(_WORD.findall((prompt or "").lower()))


def canonical_render_payload(shot: ShotSpec) -> Dict[str, Any]:
    """The only safe reuse boundary for a billable/fallback render.

    Earlier code used unordered word-overlap and equal position-derived seeds.  That made
    default dedup inert while also allowing ``A hits B`` and ``B hits A`` to collide when
    no seed was supplied.  A repeated cut may reuse only byte-identical creative render
    inputs.  The seed is intentionally excluded: the planner's position-derived seed is
    not creative intent and the canonical source shot owns the reused render seed.
    """
    return {
        "prompt": str(shot.prompt).strip(),
        "durationSeconds": int(shot.duration_seconds),
        # Reference order can change a multimodal provider result, so do not sort it.
        "imageRefs": [str(value) for value in shot.image_refs],
    }


def deduplicate_shots(shots: Iterable[ShotSpec]) -> List[ShotSpec]:
    """Reference only exact canonical render payloads; never fuzzy-match film actions."""
    result: List[ShotSpec] = []
    canonical: Dict[str, ShotSpec] = {}
    for shot in shots:
        payload_key = canonical_json(canonical_render_payload(shot))
        prior = canonical.get(payload_key)
        if prior is None:
            prior = shot
            canonical[payload_key] = prior
        # Identical prompts at different timeline positions deliberately inherit the
        # first render's seed/job.  A new seed remains a new render only when the caller
        # makes the visual payload distinct (for example a prompt variant/reference).
        result.append(ShotSpec(
            index=shot.index,
            prompt=shot.prompt,
            duration_seconds=shot.duration_seconds,
            image_refs=list(shot.image_refs),
            seed=prior.seed,
            continuity=dict(shot.continuity),
            hero_shot=bool(shot.hero_shot),
            canonical_index=prior.index,
        ))
    return result


def _extract_json(text: str) -> Any:
    try:
        # The pool/router guarantees JSON-intent requests are routed to clean seats.
        # Do not "find" a JSON fragment in prose: accepting it would conceal a router
        # regression and silently change the creative plan.
        return json.loads(text.strip())
    except json.JSONDecodeError as exc:
        raise ValueError(
            "planner router returned malformed JSON; this is a router contract failure"
        ) from exc


_CREW_CAMERA_MOVES = (
    "slow push in", "pan left", "pan right", "zoom out", "tilt up", "tilt down",
)


def _crew_mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _crew_items(value: Any) -> List[Dict[str, Any]]:
    return [dict(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _crew_scene_number(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _approved_crew_shots(
    *,
    script: str,
    target_seconds: int,
    bible: Dict[str, Any],
    seed: Optional[int],
) -> List[ShotSpec]:
    """Expand the Director-approved crew package into the durable shot graph locally.

    This is deliberately not a second LLM storyboard pass.  When a crew hand-off is
    present, the approved scene design, panels, animator plan and sound plan are the
    source of truth.  Five-second slots are only an editorial expansion needed by the
    render substrate; their text and continuity remain traceable to that package.
    """
    crew = _crew_mapping(bible.get("crew"))
    scriptwriter = _crew_mapping(crew.get("scriptwriter"))
    script_scenes = _crew_items(scriptwriter.get("scenes"))
    if not script_scenes:
        return []
    scene_designs = _crew_items(_crew_mapping(crew.get("scene_designer")).get("scenes"))
    panels = _crew_items(_crew_mapping(crew.get("storyboard_artist")).get("panels"))
    animations = _crew_items(_crew_mapping(crew.get("animator")).get("animations"))
    art = _crew_mapping(crew.get("art_director"))

    durations: List[int] = []
    for scene in script_scenes:
        try:
            durations.append(max(1, int(scene.get("duration", 5))))
        except (TypeError, ValueError):
            durations.append(5)
    nominal_total = max(1, sum(durations))
    total = max(1, int(math.ceil(int(target_seconds) / 5)))
    output: List[ShotSpec] = []
    refs = merge_image_refs(bible.get("imageRefs") or [])
    visual_scene_number = 0
    prior_approved_scene = -1
    for index in range(total):
        # Map the render grid back onto the approved script clock. This preserves the
        # relative scene length even when a caller asks for a longer/shorter delivery.
        timeline_second = (index * 5.0) * nominal_total / max(1.0, float(target_seconds))
        elapsed = 0.0
        scene_index = len(script_scenes) - 1
        for candidate, duration in enumerate(durations):
            if timeline_second < elapsed + duration:
                scene_index = candidate
                break
            elapsed += duration
        scene_number = scene_index + 1
        scene = script_scenes[scene_index]
        design = scene_designs[scene_index] if scene_index < len(scene_designs) else {}
        panel = next((item for item in panels if _crew_scene_number(item.get("scene")) == scene_number), {})
        animation = next((item for item in animations if _crew_scene_number(item.get("scene")) == scene_number), {})
        within_scene = sum(
            1 for shot in output
            if int(shot.continuity["shot"].get("approvedSceneNumber", shot.continuity["shot"]["sceneNumber"])) == scene_number
        )
        # The image fallback has a deliberate six-move scene grammar.  A long
        # approved screenplay scene is therefore split into consecutive visual
        # sequences of at most six slots, never allowed to repeat a camera move
        # inside one retained-still sequence.
        scene_shot_number = within_scene % len(_CREW_CAMERA_MOVES) + 1
        if scene_number != prior_approved_scene or scene_shot_number == 1:
            visual_scene_number += 1
            prior_approved_scene = scene_number
        preferred_move = str(panel.get("camera") or "").strip()
        moves = ([preferred_move] if preferred_move else []) + [
            move for move in _CREW_CAMERA_MOVES if move.casefold() != preferred_move.casefold()
        ]
        camera_move = moves[scene_shot_number - 1]
        style = str(art.get("visual_style") or bible.get("style") or "cinematic").strip()
        still_prompt = " | ".join(filter(None, [
            str(design.get("prompt") or design.get("description") or scene.get("description") or "").strip(),
            style,
            str(panel.get("composition") or "").strip(),
            f"editorial sequence {visual_scene_number}",
        ]))
        prompt = " | ".join(filter(None, [
            f"Approved scene {scene_number}, editorial beat {within_scene + 1}",
            str(scene.get("description") or scene.get("prompt") or "").strip(),
            str(panel.get("action") or panel.get("composition") or "").strip(),
            str(animation.get("prompt") or animation.get("action") or "").strip(),
            f"camera: {camera_move}",
            f"style: {style}",
        ]))
        scene_seed = (int(seed) + scene_index) if seed is not None else None
        output.append(ShotSpec(
            index=index,
            prompt=prompt or f"Approved scene {scene_number}, editorial beat {within_scene + 1}",
            duration_seconds=5,
            image_refs=refs,
            seed=(int(seed) + index) if seed is not None else None,
            continuity={
                "bible": bible,
                "shot": {
                    "stillPrompt": still_prompt or f"Approved scene {scene_number}",
                    "stillSeed": scene_seed,
                    "cameraMove": camera_move,
                    "sceneNumber": visual_scene_number,
                    "approvedSceneNumber": scene_number,
                    "sceneShotNumber": scene_shot_number,
                    "crewApproved": True,
                    "storyboardPanel": panel,
                    "animationPlan": animation,
                },
                "chat_provider": None,
            },
            hero_shot=scene_shot_number == 1,
        ))
    return deduplicate_shots(output)


class ShotListPlanner:
    """Uses the chat pool in batched calls while retaining a compact continuity bible."""

    def __init__(self, chat: ChatPoolClient, *, batch_size: int = 6) -> None:
        self.chat = chat
        self.batch_size = max(1, int(batch_size))

    async def create_bible(
        self,
        script: str,
        *,
        style: str = "cinematic",
        image_refs: Optional[List[str]] = None,
        character_refs: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        prompt = (
            "Create a compact film continuity bible from this screenplay. Return JSON only with "
            "keys characters (object of stable visual descriptions), wardrobe, locations, lighting, "
            "style, and imageRefs (array). Do not add prose outside JSON.\n\nSCREENPLAY:\n" + script
        )
        reply = await self.chat.message(prompt, max_tokens=1024, model="session-pool/auto")
        try:
            data = _extract_json(reply.text)
        except ValueError as exc:
            raise ValueError(f"planner JSON contract failure from {reply.provider or 'unknown provider'}: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError("continuity bible must be a JSON object")
        data.setdefault("style", style)
        data.setdefault("characters", {})
        data.setdefault("wardrobe", "consistent with character bible")
        data.setdefault("locations", [])
        data.setdefault("lighting", "continuous cinematic lighting")
        data["imageRefs"] = merge_image_refs(image_refs or [], data.get("imageRefs") or [])
        return enrich_bible_references(data, character_refs)

    async def decompose(
        self,
        script: str,
        *,
        target_seconds: int,
        bible: Dict[str, Any],
        seed: Optional[int],
    ) -> List[ShotSpec]:
        """Make batched free chat calls (not one call per five-second clip)."""
        bible = enrich_bible_references(bible)
        approved = _approved_crew_shots(
            script=script, target_seconds=target_seconds, bible=bible, seed=seed,
        )
        if approved:
            return approved
        total = max(1, int(math.ceil(int(target_seconds) / 5)))
        output: List[ShotSpec] = []
        # Six editorial moves over one scene still yield a coherent Ken Burns sequence
        # while keeping image supply bounded by scenes rather than clip slots.
        scene_size = 6
        scene_still_prompts: Dict[int, str] = {}
        scene_camera_moves: Dict[int, set[str]] = {}
        compact_bible = canonical_json(bible)
        for start in range(0, total, self.batch_size):
            count = min(self.batch_size, total - start)
            assignments = "; ".join(
                f"shot {index + 1}=scene {index // scene_size + 1}, move {index % scene_size + 1}"
                for index in range(start, start + count)
            )
            request = (
                "Turn the screenplay into the next ordered five-second film beats. Return JSON only: "
                "an array of exactly {count} objects. Every object MUST have prompt, stillPrompt, cameraMove, "
                "imageRefs, continuity, and heroShot keys. prompt is the unique moving-video prompt for this "
                "individual shot. stillPrompt is the scene's static image prompt: it MUST be byte-identical for "
                "all six shots in the same scene and different between scenes. cameraMove is this shot's gentle "
                "Ken-Burns movement: it MUST be distinct within the six-shot scene (for example slow push in, "
                "pan left, pan right, zoom out, tilt up, slow drift). "
                "Every prompt must preserve this persistent bible's characters, wardrobe, location and lighting. "
                "Avoid introducing a new character unless the screenplay requires it. Use the image refs supplied "
                "in the bible. Do not number or wrap the JSON. Required global scene assignments: {assignments}.\n\n"
                "BIBLE:\n{bible}\n\nSCREENPLAY:\n{script}\n\nBATCH: shots {first} through {last}."
            ).format(
                count=count, bible=compact_bible, script=script, assignments=assignments,
                first=start + 1, last=start + count,
            )
            # One complete six-shot scene is the smallest scene-coherent planner
            # transaction. It avoids both the 39/40 response truncation and the
            # >45-second timeout observed for larger structured replies.
            reply = await self.chat.message(request, max_tokens=max(1024, count * 150), model="session-pool/auto")
            provider = reply.provider
            try:
                raw = _extract_json(reply.text)
            except ValueError as exc:
                raise ValueError(
                    f"planner JSON contract failure in scene batch {start // self.batch_size + 1} "
                    f"from {provider or 'unknown provider'}: {exc}"
                ) from exc
            if isinstance(raw, dict):
                raw = raw.get("shots")
            if not isinstance(raw, list) or len(raw) != count:
                received = len(raw) if isinstance(raw, list) else "non-list"
                raise ValueError(
                    f"planner JSON contract breach in batch {start // self.batch_size + 1}: "
                    f"received {received} shots; expected exactly {count}"
                )
            for offset, item in enumerate(raw):
                if not isinstance(item, dict) or not str(item.get("prompt") or "").strip():
                    raise ValueError(f"shot {start + offset + 1} has no generation prompt")
                still_prompt = str(item.get("stillPrompt") or "").strip()
                camera_move = str(item.get("cameraMove") or "").strip()
                if not still_prompt:
                    raise ValueError(f"shot {start + offset + 1} has no scene stillPrompt")
                if not camera_move:
                    raise ValueError(f"shot {start + offset + 1} has no cameraMove")
                absolute_index = start + offset
                scene_number = absolute_index // scene_size + 1
                scene_seed = (int(seed) + scene_number - 1) if seed is not None else None
                earlier_prompt = scene_still_prompts.setdefault(scene_number, still_prompt)
                if earlier_prompt != still_prompt:
                    raise ValueError(
                        f"planner scene {scene_number} has mismatched stillPrompt values; "
                        "scene image identity must be shared"
                    )
                moves = scene_camera_moves.setdefault(scene_number, set())
                if camera_move.casefold() in moves:
                    raise ValueError(
                        f"planner scene {scene_number} repeats cameraMove {camera_move!r}; "
                        "every shot in a scene needs a distinct move"
                    )
                moves.add(camera_move.casefold())
                item_refs = item.get("imageRefs")
                if not isinstance(item_refs, list):
                    item_refs = []
                # Providers may return an empty array even after being given approved
                # character sheets. The durable bible references are mandatory
                # continuity inputs, so never let an advisory reply erase them.
                refs = merge_image_refs(bible.get("imageRefs") or [], item_refs)
                raw_continuity = item.get("continuity")
                # The planner's scene identity and camera contract is explicit above.
                # Ancillary continuity notes may legitimately be a short string from
                # a chat provider, so retain it rather than rejecting otherwise valid
                # structured creative work.
                shot_continuity = (
                    dict(raw_continuity) if isinstance(raw_continuity, dict)
                    else ({"plannerNote": str(raw_continuity)} if raw_continuity else {})
                )
                shot_continuity.update({
                    "stillPrompt": still_prompt,
                    "stillSeed": scene_seed,
                    "cameraMove": camera_move,
                    "sceneNumber": scene_number,
                    "sceneShotNumber": absolute_index % scene_size + 1,
                })
                output.append(ShotSpec(
                    index=absolute_index,
                    prompt=str(item["prompt"]).strip(), duration_seconds=5,
                    image_refs=[str(value) for value in refs],
                    # Real motion video remains unique per shot; only still identity
                    # is shared at scene granularity.
                    seed=(int(seed) + absolute_index) if seed is not None else None,
                    continuity={
                        "bible": bible,
                        "shot": shot_continuity,
                        "chat_provider": provider,
                    },
                    # One hero per scene guarantees scarce true-motion seats first
                    # service the scene-defining editorial beat.
                    hero_shot=bool(item.get("heroShot", False)) or absolute_index % scene_size == 0,
                ))
        for scene_number, moves in scene_camera_moves.items():
            scene_start = (scene_number - 1) * scene_size
            expected = min(scene_size, total - scene_start)
            if len(moves) != expected:
                raise ValueError(
                    f"planner scene {scene_number} supplied {len(moves)} distinct camera moves; expected {expected}"
                )
        return deduplicate_shots(output)
