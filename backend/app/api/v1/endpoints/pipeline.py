from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from agent_pipeline import create_animation_pipeline
from app.core.config import settings
from app.services.provider_service import get_provider_registry
from app.api.v1.endpoints.assets import remember_run_outputs
from app.api.v1.endpoints.legacy import require_legacy_demo_mode
from app.api.v1.dependencies.auth import get_current_user
from app.models.user import User

router = APIRouter()


class PipelineRunRequest(BaseModel):
    idea: str
    style: Optional[str] = "Anime"
    aspect_ratio: Optional[str] = "16:9"
    # The UI's "AI Model" dropdown. Was tracked in frontend state and never transmitted, and there
    # was no field here to receive it, so picking a model could not affect a run. None = server
    # default (settings.DEFAULT_CHAT_MODEL).
    model: Optional[str] = None

class PipelineAnimateRequest(BaseModel):
    scenes: List[Dict[str, Any]]
    model: Optional[str] = None

# Store pipelines in memory for this demo, in a real app use DB
active_pipelines = {}

# The crew, in the order it works. Seven agents, matching src/app/page.tsx's agentTeam and its own
# description of the Director as the one who "Coordinates the 7-agent pipeline" -- so the Director is
# the coordinator, reported under "director" below, not an eighth stage. The Storyboard Artist used
# to be missing from the backend entirely while the frontend advertised it.
SEVEN_STAGES = [
    "Scriptwriter",
    "Art Director",
    "Character Designer",
    "Scene Designer",
    "Storyboard Artist",
    "Animator",
    "Sound Director",
]


def _describe(exc: Exception) -> str:
    """Render an exception so the cause survives into the HTTP response.

    MEASURED 2026-08-24: a 7-stage run failed after 497 seconds with the detail
    "Animator execution error:" -- nothing after the colon. The cause was httpx.ReadTimeout, and
    str() on that exception is the EMPTY STRING, so an f-string interpolation of {e} reported
    absolutely nothing about what went wrong. Always lead with the class name.
    """
    return f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__


# ---------------------------------------------------------------------------
# Per-stage reporting, derived from what a run actually produced.
#
# All three routes below used to describe their stages with hardcoded strings: /pipeline/scriptwriter
# answered "Characters generated" / "Scene boards mapped" and /pipeline/animate answered "Animation
# frames rendered" / "Audio soundtrack synthesized" with status "completed" nailed on, whatever the
# agents did or failed to do. A run where the Animator rendered nothing reported the same success as
# one that rendered every clip. These helpers are the single source of that truth for /run and both
# halves of the split flow, so the three can no longer disagree.
# ---------------------------------------------------------------------------
def _script_stages(script_state: Dict[str, Any], style: str) -> Dict[str, tuple]:
    """(status, output) for Agents 1-4, read off the scriptwriter state."""
    art = script_state.get("art_direction", {}) or {}
    chars = script_state.get("characters", []) or []
    scenes = script_state.get("scenes", []) or []
    script = script_state.get("script", "") or ""
    return {
        "Scriptwriter": ("completed" if script else "degraded",
                         script or "no script returned"),
        "Art Director": ("completed" if art else "degraded",
                         f"Visual style: {art.get('style', style)}; "
                         f"palette: {art.get('color_palette', 'n/a')}" if art
                         else "no art direction returned"),
        "Character Designer": ("completed" if chars else "degraded",
                               f"{len(chars)} characters designed" if chars
                               else "no characters returned"),
        "Scene Designer": ("completed" if scenes else "degraded",
                           f"{len(scenes)} scenes mapped" if scenes else "no scenes returned"),
    }


def _animate_stages(anim_state: Dict[str, Any]) -> tuple:
    """((status, output) for Agents 5-7, the clip tally, the failed clips)."""
    clips = anim_state.get("animation", []) or []
    rendered = [c for c in clips if c.get("video_url")]
    failed = [c for c in clips if c.get("error")]
    skipped = [c for c in clips if c.get("skipped")]
    charged = sum(c.get("credits_charged") or 0 for c in clips)
    panels = anim_state.get("storyboard_panels", []) or []
    sb_error = anim_state.get("storyboard_error")
    sound = anim_state.get("sound_plan") or {}

    if not clips:
        animator_status = "completed"  # nothing to render
    elif failed and not rendered:
        animator_status = "failed"
    elif failed or skipped:
        animator_status = "degraded"
    else:
        animator_status = "completed"

    stages = {
        "Storyboard Artist": ("completed" if panels else "degraded",
                              f"{len(panels)} panels boarded" if panels
                              else f"no panels: {sb_error}" if sb_error else "no panels"),
        "Animator": (animator_status,
                     f"{len(rendered)}/{len(clips)} clips rendered, {charged} credits charged"
                     + (f", {len(skipped)} skipped (run budget)" if skipped else "")
                     + (f", {len(failed)} failed" if failed else "")),
        "Sound Director": ("completed" if sound else "degraded",
                           ", ".join(filter(None, [
                               sound.get("bgm_track"),
                               f"{len(sound.get('sfx') or [])} sfx",
                           ])) or "no sound plan"),
    }
    video = {
        "rendered": len(rendered),
        "failed": len(failed),
        "skipped": len(skipped),
        "credits_charged": charged,
        "errors": [c["error"] for c in failed][:5],
    }
    return stages, video, failed


@router.post("/{project_id}/pipeline/run")
async def run_pipeline_full(project_id: str, request: PipelineRunRequest, user: User = Depends(get_current_user)):
    """Run all 7 agents in one call, Scriptwriter through Director.

    This is the unattended path: the two-call flow above pauses between Scene Designer and
    Animator for human approval, which is the right shape for a UI but no use to a caller that
    wants a finished film. Both halves run here back to back, so the response carries all 7
    stages with real per-stage output rather than the hardcoded strings the split routes return.

    SPENDS REAL CREDITS. Stage 5 (Animator) submits one genuine video job per scene through
    whichever provider serves capability="video" -- omniroute_video at priority 0, which draws on
    a finite Flow/rtst balance (measured 2026-08-24: 930 and 18 credits). One call to this route
    can therefore cost real money in proportion to how many scenes the Scriptwriter invented.
    The spend is bounded by settings.OMNIROUTE_VIDEO_MAX_CREDITS_PER_RUN, enforced inside
    AnimationPipeline.run_animator, and reported back under "video" below. Scenes past the ceiling
    come back marked skipped rather than silently dropped.

    "status" describes the 7-agent run, not the clips: it is "completed" only when every stage ran
    AND no clip reported an error, and "completed_with_errors" otherwise. The old placeholder
    behaviour -- report success, hand back a stock video of a different film -- is gone.
    """
    require_legacy_demo_mode()
    registry = await get_provider_registry()
    pipeline = create_animation_pipeline(registry, model=request.model)
    active_pipelines[project_id] = pipeline

    try:
        script_state = await pipeline.run_scriptwriter(idea=request.idea, style=request.style)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scriptwriter execution error: {_describe(e)}")

    try:
        anim_state = await pipeline.run_animator(scenes_data=script_state.get("scenes", []))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Animator execution error: {_describe(e)}")

    # Publish what this run invented to the Library tab. Best-effort on purpose: a bookkeeping
    # failure must not turn a finished 7-agent run into a 500 for the caller.
    try:
        remember_run_outputs(project_id, script_state.get("characters", []) or [],
                             script_state.get("scenes", []) or [], user_id=user.id)
    except Exception:
        pass

    # Per-stage truth about all 7 agents, from the same helpers the split routes use.
    stages = {**_script_stages(script_state, request.style or "Anime")}
    anim_stages, video, failed = _animate_stages(anim_state)
    stages.update(anim_stages)

    return {
        "project_id": project_id,
        "status": "completed" if not failed else "completed_with_errors",
        "model": pipeline.model or settings.DEFAULT_CHAT_MODEL,
        "stages": [
            {"agent": name, "status": stages[name][0], "output": stages[name][1]}
            for name in SEVEN_STAGES
        ],
        # The Director coordinates and approves; it is not one of the 7 agent stages.
        "director": {
            "notes": anim_state.get("director_notes", ""),
            "approved": not failed,
        },
        "video": video,
        "result": {**script_state, **anim_state,
                   "status": "completed" if not failed else "completed_with_errors"},
    }


@router.post("/{project_id}/pipeline/scriptwriter")
async def run_pipeline_scriptwriter(project_id: str, request: PipelineRunRequest, user: User = Depends(get_current_user)):
    """Run Agents 1-4 (Scriptwriter to Scene Designer) and pause for approval."""
    registry = await get_provider_registry()
    pipeline = create_animation_pipeline(registry, model=request.model)
    active_pipelines[project_id] = pipeline

    try:
        results = await pipeline.run_scriptwriter(idea=request.idea, style=request.style)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scriptwriter execution error: {_describe(e)}")

    try:
        remember_run_outputs(project_id, results.get("characters", []) or [],
                             results.get("scenes", []) or [], user_id=user.id)
    except Exception:
        pass

    done = _script_stages(results, request.style or "Anime")
    return {
        "project_id": project_id,
        "status": "pending_approval",
        # Built from SEVEN_STAGES so this route, /pipeline/animate and /pipeline/run can never
        # again disagree about who the crew is. Agents 1-4 have run; the rest await approval.
        "stages": [
            {
                "agent": name,
                "status": done[name][0] if name in done else "pending",
                "output": done[name][1] if name in done else "Waiting for approval",
            }
            for name in SEVEN_STAGES
        ],
        "model": pipeline.model or settings.DEFAULT_CHAT_MODEL,
        "result": results,
    }

@router.post("/{project_id}/pipeline/animate")
async def run_pipeline_animate(project_id: str, request: PipelineAnimateRequest, user: User = Depends(get_current_user)):
    """Run Agents 5-7 (Animator to Director) after human approval."""
    require_legacy_demo_mode()
    pipeline = active_pipelines.get(project_id)
    if not pipeline:
        # Recreate if lost from memory
        registry = await get_provider_registry()
        pipeline = create_animation_pipeline(registry, model=request.model)

    try:
        results = await pipeline.run_animator(scenes_data=request.scenes)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Animator execution error: {_describe(e)}")

    done, video, failed = _animate_stages(results)
    return {
        "project_id": project_id,
        # Agents 1-4 ran in the earlier call, so they are reported completed here; 5-7 report what
        # they measured. "completed" no longer means "the HTTP call returned".
        "status": "completed" if not failed else "completed_with_errors",
        "stages": [
            {
                "agent": name,
                "status": done[name][0] if name in done else "completed",
                "output": done[name][1] if name in done else "Approved",
            }
            for name in SEVEN_STAGES
        ],
        "director": {
            "notes": results.get("director_notes", "") or "Final film cut compiled",
            "approved": not failed,
        },
        "video": video,
        "result": results,
    }
