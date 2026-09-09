"""Library assets owned by this application.

This module was a two-line stub (`router = APIRouter()` and nothing else) while the UI's Library
tab rendered four hardcoded "No saved characters / scenes / styles / assets" cards. The cards were
accurate by accident: there was no endpoint to be empty. Now the tab reflects real state.

Two different kinds of asset live here, and the distinction matters:

* **Clips** are app-owned files on disk. Provider/router harvest directories are deliberately not
  traversed here: they belong to the supply layer and have no customer ownership boundary. Durable
  film artifacts are served by the `/films` routes after an ownership check.
* **Characters, scenes and styles** are produced by a pipeline run and held in memory, exactly like
  projects in projects.py. They do NOT survive a restart, which is a real limitation and is
  reported as such by `persistent: false` rather than hidden.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
import os
import time
import hashlib
import uuid
from pathlib import Path

from app.core.config import settings
from app.api.v1.dependencies.auth import get_current_user
from app.models.user import User

router = APIRouter()

# Local media written by this app (image/audio adapters).
STORAGE_DIR = Path(os.getenv("STORAGE_PATH", "./storage")) / "media"
CHARACTER_REFERENCE_DIR = Path(os.getenv("STORAGE_PATH", "./storage")) / "character_references"
MAX_CHARACTER_REFERENCE_BYTES = 10 * 1024 * 1024

VIDEO_SUFFIXES = {".mp4", ".webm", ".mov"}

# Populated by pipeline runs via remember_run_outputs(). Keyed by kind.
_LIBRARY: Dict[str, Dict[str, Dict[str, Any]]] = {
    "characters": {},
    "scenes": {},
    "styles": {},
}


def _image_suffix(blob: bytes) -> Optional[str]:
    """Identify a small, safe allow-list of image containers by magic bytes."""
    if blob.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if blob.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if blob.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if len(blob) >= 12 and blob[:4] == b"RIFF" and blob[8:12] == b"WEBP":
        return ".webp"
    return None


def remember_run_outputs(project_id: str, characters: List[Dict[str, Any]],
                         scenes: List[Dict[str, Any]], *, user_id: Optional[str] = None) -> None:
    """Record what a pipeline run invented so the Library can show it.

    Deduplicated by name/description so re-running the same idea does not pile up copies. Called
    from the pipeline routes; safe to call with empty lists.
    """
    now = time.time()
    for c in characters or []:
        key = (c.get("name") or "").strip().lower()
        if not key:
            continue
        _LIBRARY["characters"][key] = {
            "id": key, "name": c.get("name"), "description": c.get("description", ""),
            "project_id": project_id, "owner_id": user_id, "saved_at": now,
        }
    for i, s in enumerate(scenes or []):
        desc = (s.get("description") or s.get("visual_prompt") or "").strip()
        if not desc:
            continue
        key = f"{project_id}:{s.get('id', s.get('scene', i + 1))}"
        _LIBRARY["scenes"][key] = {
            "id": key, "name": f"Scene {s.get('id', s.get('scene', i + 1))}",
            "description": desc, "duration": s.get("duration"),
            "project_id": project_id, "owner_id": user_id, "saved_at": now,
        }


def _clips() -> List[Dict[str, Any]]:
    """Every generated clip on disk, newest first.

    Only walks the app-owned media directory. The old provider harvest tree is a sibling service's
    filesystem and is never a customer asset source, even if a stale compatibility flag is set.
    """
    # Local clip files predate tenant ownership. Do not expose their names or URLs
    # to paid users until each file has durable ownership metadata.
    if settings.CLOSED_SAAS_MODE:
        return []
    found: List[Dict[str, Any]] = []
    roots = [(STORAGE_DIR, "local")]
    for root, provider in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in VIDEO_SUFFIXES:
                continue
            try:
                stat = path.stat()
            except OSError:
                continue  # vanished between rglob and stat
            found.append({
                "id": path.stem,
                "name": path.name,
                "provider": provider,
                "bytes": stat.st_size,
                "created_at": stat.st_mtime,
                # Served by the route below rather than exposing a filesystem path to the browser.
                "url": f"/api/v1/assets/clips/{provider}/{path.name}",
            })
    return sorted(found, key=lambda c: c["created_at"], reverse=True)


@router.get("/")
async def list_assets(user: User = Depends(get_current_user)):
    """Everything the Library tab shows, in one call."""
    clips = _clips()
    characters = [item for item in _LIBRARY["characters"].values() if item.get("owner_id") == user.id]
    scenes = [item for item in _LIBRARY["scenes"].values() if item.get("owner_id") == user.id]
    styles = [item for item in _LIBRARY["styles"].values() if item.get("owner_id") == user.id]
    return {
        "characters": sorted(characters,
                             key=lambda a: a["saved_at"], reverse=True),
        "scenes": sorted(scenes,
                         key=lambda a: a["saved_at"], reverse=True),
        "styles": sorted(styles,
                         key=lambda a: a["saved_at"], reverse=True),
        "clips": clips,
        "counts": {
            "characters": len(characters),
            "scenes": len(scenes),
            "styles": len(styles),
            "clips": len(clips),
        },
        # Honest about what is durable. Clips are files; the rest is process memory.
        "persistent": {"clips": True, "characters": False, "scenes": False, "styles": False},
        # Do not reveal machine paths or a sibling router's directory topology.
        "sources": {"local_media": True, "provider_harvest": False},
    }


class SaveStyleRequest(BaseModel):
    id: str
    name: str
    category: Optional[str] = ""
    promptSuffix: Optional[str] = ""


@router.post("/character-references")
async def upload_character_reference(
    request: Request,
    image: UploadFile = File(...),
    character_name: str = "character",
    kind: str = "portrait",
    user: User = Depends(get_current_user),
):
    """Store a customer-provided sheet/portrait without calling an image provider.

    The returned URL is app-controlled and can be reviewed before it is included in a
    crew admission. The storage is intentionally bounded, identifies the actual image
    container by signature rather than the client filename, and never retains a raw
    caller path.
    """
    safe_name = " ".join(character_name.split())[:120]
    if not safe_name:
        raise HTTPException(status_code=422, detail="character_name is required")
    if kind not in {"sheet", "portrait", "reference"}:
        raise HTTPException(status_code=422, detail="kind must be sheet, portrait, or reference")
    blob = await image.read(MAX_CHARACTER_REFERENCE_BYTES + 1)
    if len(blob) > MAX_CHARACTER_REFERENCE_BYTES:
        raise HTTPException(status_code=413, detail="character reference exceeds the 10 MiB limit")
    suffix = _image_suffix(blob)
    if suffix is None:
        raise HTTPException(status_code=415, detail="character reference must be PNG, JPEG, GIF, or WebP")
    asset_id = uuid.uuid4().hex
    path = CHARACTER_REFERENCE_DIR / f"{asset_id}{suffix}"
    path.parent.mkdir(parents=True, exist_ok=True)
    # ``UploadFile`` data is already fully bounded and the opaque generated filename
    # prevents user-controlled path traversal or overwriting another reference.
    path.write_bytes(blob)
    digest = hashlib.sha256(blob).hexdigest()
    _LIBRARY["characters"][asset_id] = {
        "id": asset_id,
        "name": safe_name,
        "kind": kind,
        "bytes": len(blob),
        "sha256": digest,
        "owner_id": user.id,
        "saved_at": time.time(),
        "persistent": True,
    }
    return {
        "assetId": asset_id,
        "characterName": safe_name,
        "kind": kind,
        "sha256": digest,
        "referenceUrl": str(request.url_for("get_character_reference", asset_id=asset_id)),
    }


@router.post("/styles")
async def save_style(request: SaveStyleRequest, user: User = Depends(get_current_user)):
    """Pin a style to the Library so it can be reused across runs."""
    _LIBRARY["styles"][request.id] = {
        "id": request.id, "name": request.name, "category": request.category,
        "promptSuffix": request.promptSuffix, "owner_id": user.id, "saved_at": time.time(),
    }
    return _LIBRARY["styles"][request.id]


@router.delete("/styles/{style_id}")
async def unsave_style(style_id: str, user: User = Depends(get_current_user)):
    if style_id not in _LIBRARY["styles"] or _LIBRARY["styles"][style_id].get("owner_id") != user.id:
        raise HTTPException(status_code=404, detail=f"style {style_id!r} is not in the library")
    return {"removed": _LIBRARY["styles"].pop(style_id)["id"]}


@router.get("/clips/{provider}/{filename}")
async def get_clip(provider: str, filename: str, user: User = Depends(get_current_user)):
    """Stream one generated clip.

    Only app-owned `local` clips are served. Provider-harvest paths are a retired compatibility
    surface, so rejecting them explicitly prevents a caller from turning this app into a sibling
    router filesystem browser.
    """
    if provider != "local":
        raise HTTPException(
            status_code=410,
            detail={
                "code": "legacy_clip_source_retired",
                "message": "provider harvest clips are no longer served by the customer API",
                "replacement": "/api/v1/films/{film_id}/artifact",
            },
        )
    for clip in _clips():
        if clip["name"] == filename and clip["provider"] == provider:
            root = STORAGE_DIR
            for candidate in (root / filename, *root.rglob(filename)):
                if candidate.is_file():
                    # No filename= here on purpose: FileResponse turns that into
                    # `Content-Disposition: attachment`, which makes the browser download the clip
                    # instead of playing it in the Library's <video> element.
                    return FileResponse(str(candidate), media_type="video/mp4")
    raise HTTPException(status_code=404, detail=f"no clip {provider}/{filename}")


@router.get("/character-references/{asset_id}", name="get_character_reference")
async def get_character_reference(asset_id: str, user: User = Depends(get_current_user)):
    """Serve one generated-ID character reference from app-owned storage."""
    if len(asset_id) != 32 or any(ch not in "0123456789abcdef" for ch in asset_id):
        raise HTTPException(status_code=404, detail="character reference not found")
    record = _LIBRARY["characters"].get(asset_id)
    if record is None or record.get("owner_id") != user.id:
        raise HTTPException(status_code=404, detail="character reference not found")
    matches = list(CHARACTER_REFERENCE_DIR.glob(f"{asset_id}.*"))
    if len(matches) != 1 or not matches[0].is_file():
        raise HTTPException(status_code=404, detail="character reference not found")
    media_type = {".png": "image/png", ".jpg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp"}.get(
        matches[0].suffix.lower(), "application/octet-stream"
    )
    return FileResponse(str(matches[0]), media_type=media_type)
