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
    *, script: str, target_seconds: int, aspect_ratio: str, bible: Dict[str, Any], seed: Optional[int]
) -> str:
    return stable_hash({
        "script": script.strip(), "targetSeconds": int(target_seconds), "aspectRatio": aspect_ratio,
        "bible": bible, "seed": seed,
    })


_WORD = re.compile(r"[a-z0-9]+")


def normalize_prompt(prompt: str) -> str:
    return " ".join(_WORD.findall((prompt or "").lower()))


def _similarity(left: str, right: str) -> float:
    a, b = set(normalize_prompt(left).split()), set(normalize_prompt(right).split())
    if not a and not b:
        return 1.0
    return len(a & b) / max(1, len(a | b))


def deduplicate_shots(shots: Iterable[ShotSpec], *, threshold: float = 0.92) -> List[ShotSpec]:
    """Reference exact or very-near duplicate shots rather than buying them twice."""
    result: List[ShotSpec] = []
    canonical: List[ShotSpec] = []
    for shot in shots:
        found: Optional[int] = None
        for prior in canonical:
            if (
                int(prior.duration_seconds) == int(shot.duration_seconds)
                and sorted(prior.image_refs) == sorted(shot.image_refs)
                and prior.seed == shot.seed
                and _similarity(prior.prompt, shot.prompt) >= threshold
            ):
                found = prior.index
                break
        if found is None:
            canonical.append(shot)
            found = shot.index
        result.append(ShotSpec(
            index=shot.index, prompt=shot.prompt, duration_seconds=shot.duration_seconds,
            image_refs=list(shot.image_refs), seed=shot.seed, continuity=dict(shot.continuity),
            canonical_index=found,
        ))
    return result


def _extract_json(text: str) -> Any:
    clean = text.strip()
    if clean.startswith("```"):
        clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", clean, flags=re.IGNORECASE)
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        start = min((i for i in (clean.find("["), clean.find("{")) if i >= 0), default=-1)
        end = max(clean.rfind("]"), clean.rfind("}"))
        if start < 0 or end <= start:
            raise ValueError("chat response did not contain JSON")
        return json.loads(clean[start : end + 1])


class ShotListPlanner:
    """Uses the chat pool in batched calls while retaining a compact continuity bible."""

    def __init__(self, chat: ChatPoolClient, *, batch_size: int = 40) -> None:
        self.chat = chat
        self.batch_size = max(1, int(batch_size))

    async def create_bible(self, script: str, *, style: str = "cinematic", image_refs: Optional[List[str]] = None) -> Dict[str, Any]:
        prompt = (
            "Create a compact film continuity bible from this screenplay. Return JSON only with "
            "keys characters (object of stable visual descriptions), wardrobe, locations, lighting, "
            "style, and imageRefs (array). Do not add prose outside JSON.\n\nSCREENPLAY:\n" + script
        )
        reply = await self.chat.message(prompt, max_tokens=1024, model="pool/auto")
        data = _extract_json(reply.text)
        if not isinstance(data, dict):
            raise ValueError("continuity bible must be a JSON object")
        data.setdefault("style", style)
        data.setdefault("characters", {})
        data.setdefault("wardrobe", "consistent with character bible")
        data.setdefault("locations", [])
        data.setdefault("lighting", "continuous cinematic lighting")
        data["imageRefs"] = list(image_refs or data.get("imageRefs") or [])
        return data

    async def decompose(
        self,
        script: str,
        *,
        target_seconds: int,
        bible: Dict[str, Any],
        seed: Optional[int],
    ) -> List[ShotSpec]:
        """Make batched free chat calls (not one call per five-second clip)."""
        total = max(1, int(math.ceil(int(target_seconds) / 5)))
        output: List[ShotSpec] = []
        compact_bible = canonical_json(bible)
        for start in range(0, total, self.batch_size):
            count = min(self.batch_size, total - start)
            request = (
                "Turn the screenplay into the next ordered five-second film beats. Return JSON only: "
                "an array of exactly {count} objects with prompt, imageRefs, and continuity keys. "
                "Every prompt must preserve this persistent bible's characters, wardrobe, location and lighting. "
                "Avoid introducing a new character unless the screenplay requires it. Use the image refs supplied "
                "in the bible. Do not number or wrap the JSON.\n\n"
                "BIBLE:\n{bible}\n\nSCREENPLAY:\n{script}\n\nBATCH: shots {first} through {last}."
            ).format(count=count, bible=compact_bible, script=script, first=start + 1, last=start + count)
            reply = await self.chat.message(request, max_tokens=max(1024, count * 80), model="pool/auto")
            raw = _extract_json(reply.text)
            if isinstance(raw, dict):
                raw = raw.get("shots")
            if not isinstance(raw, list) or len(raw) != count:
                raise ValueError(f"shot batch {start // self.batch_size + 1} returned {len(raw) if isinstance(raw, list) else 'non-list'} entries; expected {count}")
            for offset, item in enumerate(raw):
                if not isinstance(item, dict) or not str(item.get("prompt") or "").strip():
                    raise ValueError(f"shot {start + offset + 1} has no generation prompt")
                refs = item.get("imageRefs", bible.get("imageRefs") or [])
                if not isinstance(refs, list):
                    refs = list(bible.get("imageRefs") or [])
                output.append(ShotSpec(
                    index=start + offset,
                    prompt=str(item["prompt"]).strip(), duration_seconds=5,
                    image_refs=[str(value) for value in refs],
                    seed=(int(seed) + start + offset) if seed is not None else None,
                    continuity={
                        "bible": bible,
                        "shot": item.get("continuity") or {},
                        "chat_provider": reply.provider,
                    },
                ))
        return deduplicate_shots(output)

