"""Library assets — characters, scenes, styles and the video clips that actually exist.

This module was a two-line stub (`router = APIRouter()` and nothing else) while the UI's Library
tab rendered four hardcoded "No saved characters / scenes / styles / assets" cards. The cards were
accurate by accident: there was no endpoint to be empty. Now the tab reflects real state.

Two different kinds of asset live here, and the distinction matters:

* **Clips** are files on disk. The video router writes every finished generation under its harvest
  directory, so these are enumerated from the filesystem and are true whether or not this process
  produced them. They survive a restart.
* **Characters, scenes and styles** are produced by a pipeline run and held in memory, exactly like
  projects in projects.py. They do NOT survive a restart, which is a real limitation and is
  reported as such by `persistent: false` rather than hidden.
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
import os
import time
from pathlib import Path

router = APIRouter()

# Where the OmniRoute video router deposits finished clips. Same default as the router itself uses;
# override with OMNIROUTE_VIDEO_HARVEST_DIR when the state directory moves.
HARVEST_DIR = Path(
    os.getenv("OMNIROUTE_VIDEO_HARVEST_DIR", r"D:\omniroute-monetizer\state\harvest")
)
# Local media written by this app (image/audio adapters).
STORAGE_DIR = Path(os.getenv("STORAGE_PATH", "./storage")) / "media"

VIDEO_SUFFIXES = {".mp4", ".webm", ".mov"}

# Only these subdirectories of the harvest tree hold generated films, one per video provider.
# MEASURED: walking the whole tree found 51 "clips", but 45 were screen-recording debris from a
# sibling rec/ directory (win_recording.mp4 at 48 MB, seg000..seg044 segments) left over from
# harness debugging. The Library is for the user's films, not the harness's own capture files.
PROVIDER_DIRS = ("flow", "rtst")

# Populated by pipeline runs via remember_run_outputs(). Keyed by kind.
_LIBRARY: Dict[str, Dict[str, Dict[str, Any]]] = {
    "characters": {},
    "scenes": {},
    "styles": {},
}


def remember_run_outputs(project_id: str, characters: List[Dict[str, Any]],
                         scenes: List[Dict[str, Any]]) -> None:
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
            "project_id": project_id, "saved_at": now,
        }
    for i, s in enumerate(scenes or []):
        desc = (s.get("description") or s.get("visual_prompt") or "").strip()
        if not desc:
            continue
        key = f"{project_id}:{s.get('id', s.get('scene', i + 1))}"
        _LIBRARY["scenes"][key] = {
            "id": key, "name": f"Scene {s.get('id', s.get('scene', i + 1))}",
            "description": desc, "duration": s.get("duration"),
            "project_id": project_id, "saved_at": now,
        }


def _clips() -> List[Dict[str, Any]]:
    """Every generated clip on disk, newest first.

    Walks the harvest tree (flow/, rtst/, ...) and the app's own media directory. The provider is
    taken from the containing directory name, which is how the router organises its output.
    """
    found: List[Dict[str, Any]] = []
    roots = [(HARVEST_DIR / d, d) for d in PROVIDER_DIRS] + [(STORAGE_DIR, "local")]
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
async def list_assets():
    """Everything the Library tab shows, in one call."""
    clips = _clips()
    return {
        "characters": sorted(_LIBRARY["characters"].values(),
                             key=lambda a: a["saved_at"], reverse=True),
        "scenes": sorted(_LIBRARY["scenes"].values(),
                         key=lambda a: a["saved_at"], reverse=True),
        "styles": sorted(_LIBRARY["styles"].values(),
                         key=lambda a: a["saved_at"], reverse=True),
        "clips": clips,
        "counts": {
            "characters": len(_LIBRARY["characters"]),
            "scenes": len(_LIBRARY["scenes"]),
            "styles": len(_LIBRARY["styles"]),
            "clips": len(clips),
        },
        # Honest about what is durable. Clips are files; the rest is process memory.
        "persistent": {"clips": True, "characters": False, "scenes": False, "styles": False},
        "sources": {"harvest_dir": str(HARVEST_DIR), "storage_dir": str(STORAGE_DIR)},
    }


class SaveStyleRequest(BaseModel):
    id: str
    name: str
    category: Optional[str] = ""
    promptSuffix: Optional[str] = ""


@router.post("/styles")
async def save_style(request: SaveStyleRequest):
    """Pin a style to the Library so it can be reused across runs."""
    _LIBRARY["styles"][request.id] = {
        "id": request.id, "name": request.name, "category": request.category,
        "promptSuffix": request.promptSuffix, "saved_at": time.time(),
    }
    return _LIBRARY["styles"][request.id]


@router.delete("/styles/{style_id}")
async def unsave_style(style_id: str):
    if style_id not in _LIBRARY["styles"]:
        raise HTTPException(status_code=404, detail=f"style {style_id!r} is not in the library")
    return {"removed": _LIBRARY["styles"].pop(style_id)["id"]}


@router.get("/clips/{provider}/{filename}")
async def get_clip(provider: str, filename: str):
    """Stream one generated clip.

    Both path segments are validated against the enumerated set rather than joined onto
    HARVEST_DIR directly -- a caller-supplied filename reaching os.path.join is a path-traversal
    hole (`..%2f..%2fwindows%2fsystem32`), and this route is reachable from the browser.
    """
    for clip in _clips():
        if clip["name"] == filename and clip["provider"] == provider:
            root = STORAGE_DIR if provider == "local" else HARVEST_DIR / provider
            for candidate in (root / filename, *root.rglob(filename)):
                if candidate.is_file():
                    # No filename= here on purpose: FileResponse turns that into
                    # `Content-Disposition: attachment`, which makes the browser download the clip
                    # instead of playing it in the Library's <video> element.
                    return FileResponse(str(candidate), media_type="video/mp4")
    raise HTTPException(status_code=404, detail=f"no clip {provider}/{filename}")
