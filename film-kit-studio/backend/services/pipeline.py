"""
Pipeline orchestration service.

Coordinates the full filmmaking pipeline:
  1. Script & Storyboard Generation (NIM LLM)
  2. Visual Generation (Cosmos3 NIM)
  3. Audio & Narration Synthesis (edge-tts + FFMPEG ambient bed)
  4. Video Assembly & Stitching (FFMPEG)

Each step updates task progress via the TaskManager and emits SSE events.
"""

import logging
import random
import uuid
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from config import ASPECTS, settings
from database import async_session
from models import Character, Project, Scene, SceneStatus
from services.nim_llm import generate_script
from services.visual_providers import generate_visual
from services.voice_providers import synthesize_narration
from tasks.task_manager import task_manager
from utils.ffmpeg_ops import (
    build_ken_burns_clip,
    ensure_ffmpeg,
    mix_music_under,
    mux_audio,
    probe_duration,
    stitch_concat,
    stitch_crossfade,
    trim_clip,
    write_srt,
)

logger = logging.getLogger(__name__)


def _project_dir(project_id: str) -> Path:
    """Get the project's storage directory, creating subdirs."""
    base = settings.projects_path / project_id
    for sub in ("images", "audio", "clips", "output"):
        (base / sub).mkdir(parents=True, exist_ok=True)
    return base


def _compose_cinematic_prompt(scene: Scene, character: Character | None = None) -> str:
    """
    Compose the full visual prompt for a scene.

    Combines the global cinematography style prefix (config), the scene's
    structured cinematography fields (shot/lens/lighting/camera/grade), the
    character's description (identity-lock fallback), and the scene's base
    visual_prompt into one fluent, filmic prompt that the active visual
    provider receives. This is the single biggest free lever for raising
    visual quality.
    """
    parts: list[str] = []
    if settings.cinematography_style:
        parts.append(settings.cinematography_style)

    # Structured direction from the upgraded LLM schema
    direction_bits = []
    for label, value in (
        ("shot", scene.shot_type),
        (None, scene.lens),          # lens is self-describing (e.g. "85mm")
        ("lighting", scene.lighting),
        ("camera", scene.camera_move),
        ("grade", scene.color_grade),
    ):
        if value:
            direction_bits.append(f"{label} {value}" if label else str(value))
    if direction_bits:
        parts.append(", ".join(direction_bits))

    # Character description fold-in (identity-lock fallback for all providers)
    if character and character.description:
        parts.append(f"character: {character.description}")

    # The scene's own description is the core
    parts.append(scene.visual_prompt)

    return ", ".join(parts)


async def _get_project(project_id: str) -> Project:
    """Load a project with its scenes."""
    async with async_session() as session:
        stmt = (
            select(Project)
            .where(Project.id == project_id)
            .options(selectinload(Project.scenes))
        )
        result = await session.execute(stmt)
        project = result.scalar_one_or_none()
        if project is None:
            raise ValueError(f"Project {project_id} not found")
        return project


# ── Step 1: Script Generation ───────────────────────────────

async def run_script_generation(
    task_id: str,
    project_id: str,
    num_scenes: int,
) -> dict:
    """Generate script/storyboard via NIM LLM."""
    await task_manager.update_progress(task_id, 0.05, "Loading project...")

    project = await _get_project(project_id)

    await task_manager.update_progress(task_id, 0.1, "Calling NVIDIA NIM LLM...")

    scenes_data = await generate_script(
        idea=project.idea,
        num_scenes=num_scenes,
        style=project.style,
    )

    await task_manager.update_progress(task_id, 0.8, "Saving storyboard to database...")

    # Clear existing scenes and create new ones
    async with async_session() as session:
        # Delete existing scenes
        stmt = select(Scene).where(Scene.project_id == project_id)
        result = await session.execute(stmt)
        for old_scene in result.scalars():
            await session.delete(old_scene)

        # Create new scenes
        for i, scene_data in enumerate(scenes_data):
            scene = Scene(
                id=str(uuid.uuid4()),
                project_id=project_id,
                index=i,
                narration=scene_data["narration"],
                visual_prompt=scene_data["visual_prompt"],
                # Cinematography direction (nullable; the LLM emits these
                # via the upgraded system prompt, older flows leave them None)
                shot_type=scene_data.get("shot_type"),
                lens=scene_data.get("lens"),
                lighting=scene_data.get("lighting"),
                camera_move=scene_data.get("camera_move"),
                color_grade=scene_data.get("color_grade"),
                status=SceneStatus.SCRIPT_DONE.value,
            )
            session.add(scene)

        # Update project status
        stmt_proj = select(Project).where(Project.id == project_id)
        result_proj = await session.execute(stmt_proj)
        proj = result_proj.scalar_one_or_none()
        if proj:
            proj.status = "script_generated"
            proj.num_scenes = len(scenes_data)

        await session.commit()

    await task_manager.update_progress(task_id, 1.0, f"Generated {len(scenes_data)} scenes")

    return {"scenes_generated": len(scenes_data)}


# ── Step 2: Visual Generation ──────────────────────────────

async def run_visual_generation(
    task_id: str,
    project_id: str,
    scene_indices: Optional[list[int]] = None,
) -> dict:
    """Generate visuals via NVIDIA Cosmos3 NIM for all (or specified) scenes."""
    project = await _get_project(project_id)
    proj_dir = _project_dir(project_id)

    async with async_session() as session:
        stmt = (
            select(Scene)
            .where(Scene.project_id == project_id)
            .order_by(Scene.index)
        )
        result = await session.execute(stmt)
        scenes = result.scalars().all()

        if scene_indices is not None:
            scenes = [s for s in scenes if s.index in scene_indices]

        total = len(scenes)
        generated = 0
        failed = 0

        for i, scene in enumerate(scenes):
            pct = i / max(1, total)
            await task_manager.update_progress(
                task_id, pct,
                f"Generating visual for scene {scene.index} ({i + 1}/{total})..."
            )
            await task_manager.update_scene(
                task_id, scene.index, "visual_pending",
                f"Generating visual..."
            )

            out_path = proj_dir / "images" / f"scene_{scene.index:02}.mp4"

            try:
                # Character reference image for visual consistency
                reference_image = None
                if scene.character_id:
                    char_stmt = select(Character).where(Character.id == scene.character_id)
                    char_result = await session.execute(char_stmt)
                    character = char_result.scalar_one_or_none()
                    if character and character.reference_image_path:
                        reference_image = Path(character.reference_image_path)

                async def progress_cb(p, msg):
                    await task_manager.update_progress(
                        task_id, pct + p * (1.0 / total), msg
                    )

                video_path = await generate_visual(
                    visual_prompt=_compose_cinematic_prompt(scene),
                    out_path=out_path,
                    aspect=project.aspect,
                    seed=project.seed + scene.index,
                    reference_image=reference_image,
                    progress_callback=progress_cb,
                )

                scene.video_path = video_path
                scene.status = SceneStatus.VISUAL_DONE.value
                generated += 1

                await task_manager.update_scene(
                    task_id, scene.index, "visual_done",
                    f"Visual generated"
                )

            except Exception as exc:
                logger.error(f"Visual generation failed for scene {scene.index}: {exc}")
                scene.status = SceneStatus.ERROR.value
                scene.error_message = str(exc)
                failed += 1

                await task_manager.update_scene(
                    task_id, scene.index, "error",
                    f"Visual failed: {exc}"
                )

        # Update project status
        stmt_proj = select(Project).where(Project.id == project_id)
        result_proj = await session.execute(stmt_proj)
        proj = result_proj.scalar_one_or_none()
        if proj:
            proj.status = "visuals_generated"

        await session.commit()

    await task_manager.update_progress(
        task_id, 1.0,
        f"Visuals: {generated} generated, {failed} failed"
    )

    return {"generated": generated, "failed": failed}


# ── Step 3: Audio & Narration ───────────────────────────────

async def run_audio_generation(
    task_id: str,
    project_id: str,
    voice: Optional[str] = None,
) -> dict:
    """Generate narration audio via edge-tts for all scenes."""
    project = await _get_project(project_id)
    proj_dir = _project_dir(project_id)

    voice_key = voice or project.voice

    async with async_session() as session:
        stmt = (
            select(Scene)
            .where(Scene.project_id == project_id)
            .order_by(Scene.index)
        )
        result = await session.execute(stmt)
        scenes = result.scalars().all()

        total = len(scenes)
        generated = 0

        for i, scene in enumerate(scenes):
            pct = i / max(1, total)
            await task_manager.update_progress(
                task_id, pct,
                f"Synthesizing narration for scene {scene.index} ({i + 1}/{total})..."
            )
            await task_manager.update_scene(
                task_id, scene.index, "audio_pending",
                f"Synthesizing narration..."
            )

            out_path = proj_dir / "audio" / f"scene_{scene.index:02}.mp3"

            try:
                duration = await synthesize_narration(
                    text=scene.narration,
                    voice_key=voice_key,
                    out_path=out_path,
                )

                scene.audio_path = str(out_path)
                scene.duration = duration + 0.4  # pad so Ken Burns isn't cut short
                scene.status = SceneStatus.AUDIO_DONE.value
                generated += 1

                await task_manager.update_scene(
                    task_id, scene.index, "audio_done",
                    f"Narration: {duration:.1f}s"
                )

            except Exception as exc:
                logger.error(f"Audio generation failed for scene {scene.index}: {exc}")
                scene.status = SceneStatus.ERROR.value
                scene.error_message = str(exc)

                await task_manager.update_scene(
                    task_id, scene.index, "error",
                    f"Audio failed: {exc}"
                )

        # Update project status
        stmt_proj = select(Project).where(Project.id == project_id)
        result_proj = await session.execute(stmt_proj)
        proj = result_proj.scalar_one_or_none()
        if proj:
            proj.status = "audio_generated"
            proj.voice = voice_key

        await session.commit()

    await task_manager.update_progress(task_id, 1.0, f"Narration: {generated} scenes done")
    return {"generated": generated}


# ── Step 4: Clip Rendering ──────────────────────────────────

async def run_clip_generation(
    task_id: str,
    project_id: str,
) -> dict:
    """Render Ken Burns clips (or use Cosmos video) + mux audio."""
    if not ensure_ffmpeg():
        raise RuntimeError("ffmpeg/ffprobe not found — install ffmpeg and add it to PATH.")

    project = await _get_project(project_id)
    proj_dir = _project_dir(project_id)
    size = ASPECTS.get(project.aspect, ASPECTS["16:9"])

    async with async_session() as session:
        stmt = (
            select(Scene)
            .where(Scene.project_id == project_id)
            .order_by(Scene.index)
        )
        result = await session.execute(stmt)
        scenes = result.scalars().all()

        total = len(scenes)
        rendered = 0

        for i, scene in enumerate(scenes):
            pct = i / max(1, total)
            await task_manager.update_progress(
                task_id, pct,
                f"Rendering clip for scene {scene.index} ({i + 1}/{total})..."
            )
            await task_manager.update_scene(
                task_id, scene.index, "clip_pending",
                f"Rendering clip..."
            )

            # Check if we have a Cosmos-generated video
            has_video = scene.video_path and Path(scene.video_path).exists()
            has_audio = scene.audio_path and Path(scene.audio_path).exists()

            if not has_audio:
                logger.warning(f"Scene {scene.index}: missing audio — skipping")
                await task_manager.update_scene(
                    task_id, scene.index, "error",
                    f"Missing audio"
                )
                continue

            try:
                final_clip = proj_dir / "clips" / f"scene_{scene.index:02}.mp4"

                if has_video:
                    # Cosmos generated a video — just mux audio
                    await task_manager.update_scene(
                        task_id, scene.index, "clip_pending",
                        f"Muxing Cosmos video with audio..."
                    )
                    await mux_audio(
                        Path(scene.video_path),
                        Path(scene.audio_path),
                        final_clip,
                    )
                elif scene.image_path and Path(scene.image_path).exists():
                    # Fallback: Ken Burns from static image
                    raw = proj_dir / "clips" / f"_raw_{scene.index:02}.mp4"
                    duration = scene.duration or 4.0

                    async def progress_cb(p):
                        await task_manager.update_progress(
                            task_id, pct + p * (1.0 / total * 0.7),
                            f"Ken Burns rendering scene {scene.index}..."
                        )

                    await build_ken_burns_clip(
                        Path(scene.image_path),
                        duration,
                        raw,
                        size,
                        fps=settings.fps_default,
                        zoom_in=(scene.index % 2 == 0),
                        progress_callback=progress_cb,
                    )
                    await mux_audio(raw, Path(scene.audio_path), final_clip)
                    raw.unlink(missing_ok=True)
                else:
                    logger.warning(f"Scene {scene.index}: no video or image — skipping")
                    await task_manager.update_scene(
                        task_id, scene.index, "error",
                        f"No visual source"
                    )
                    continue

                scene.clip_path = str(final_clip)
                scene.status = SceneStatus.CLIP_DONE.value
                rendered += 1

                await task_manager.update_scene(
                    task_id, scene.index, "clip_done",
                    f"Clip rendered"
                )

            except Exception as exc:
                logger.error(f"Clip rendering failed for scene {scene.index}: {exc}")
                scene.status = SceneStatus.ERROR.value
                scene.error_message = str(exc)

                await task_manager.update_scene(
                    task_id, scene.index, "error",
                    f"Clip failed: {exc}"
                )

        # Update project status
        stmt_proj = select(Project).where(Project.id == project_id)
        result_proj = await session.execute(stmt_proj)
        proj = result_proj.scalar_one_or_none()
        if proj:
            proj.status = "clips_generated"

        await session.commit()

    await task_manager.update_progress(task_id, 1.0, f"Clips: {rendered} rendered")
    return {"rendered": rendered}


# ── Step 5: Final Stitching ─────────────────────────────────

async def run_stitching(
    task_id: str,
    project_id: str,
    mode: str = "cut",
) -> dict:
    """Stitch all scene clips into the final film.

    Respects per-scene trim/exclude/transition settings:
    - Scenes with included=False are skipped
    - Scenes with trim_in/trim_out are pre-trimmed before stitching
    - Per-scene transition_type/transition_duration overrides global mode
    """
    if not ensure_ffmpeg():
        raise RuntimeError("ffmpeg/ffprobe not found — install ffmpeg and add it to PATH.")

    project = await _get_project(project_id)
    proj_dir = _project_dir(project_id)

    await task_manager.update_progress(task_id, 0.1, "Loading scene clips...")

    async with async_session() as session:
        stmt = (
            select(Scene)
            .where(Scene.project_id == project_id)
            .order_by(Scene.index)
        )
        result = await session.execute(stmt)
        scenes = result.scalars().all()

        # Filter included scenes
        included_scenes = [s for s in scenes if s.included and s.clip_path and Path(s.clip_path).exists()]
        
        if not included_scenes:
            raise RuntimeError("No clips to stitch — run clip generation first or check included flags.")

        # Pre-trim clips if needed
        await task_manager.update_progress(task_id, 0.2, "Preparing clips (trimming)...")
        clip_paths = []
        effective_durations = []
        
        for i, scene in enumerate(included_scenes):
            src = Path(scene.clip_path)
            trimmed_path = src
            
            needs_trim = (scene.trim_in is not None and scene.trim_in > 0) or \
                         (scene.trim_out is not None and scene.trim_out > 0)
            
            if needs_trim:
                trimmed_path = proj_dir / "clips" / f"_trimmed_{scene.index:02}.mp4"
                await trim_clip(
                    src=src,
                    out=trimmed_path,
                    in_point=scene.trim_in,
                    out_point=scene.trim_out,
                )
            
            clip_paths.append(trimmed_path)
            dur = await probe_duration(trimmed_path)
            effective_durations.append(dur)

        missing = [
            s.index for s in scenes
            if not (s.clip_path and Path(s.clip_path).exists())
        ]
        if missing:
            logger.warning(f"Stitching without scenes: {missing}")

        await task_manager.update_progress(task_id, 0.4, f"Stitching {len(clip_paths)} clips...")

        out_mp4 = proj_dir / "output" / f"{project.name}.mp4"

        # Determine transitions per scene (transition applies TO the next scene)
        # For n clips, we need n-1 transitions. Scene i's transition_type/duration
        # controls the transition between clip i and clip i+1.
        if len(clip_paths) == 1:
            shutil.copy2(clip_paths[0], out_mp4)
        else:
            # Build xfade filter chain with per-scene transitions
            inputs = []
            for p in clip_paths:
                inputs += ["-i", str(p)]

            filter_parts = []
            prev_v = "0:v"
            prev_a = "0:a"
            cum_dur = effective_durations[0]

            for i in range(1, len(clip_paths)):
                scene_idx = i - 1  # scene index for transition (between i-1 and i)
                if scene_idx < len(included_scenes):
                    scene = included_scenes[scene_idx]
                    trans_type = scene.transition_type or mode
                    trans_dur = scene.transition_duration if scene.transition_duration is not None else 0.75
                else:
                    trans_type = mode
                    trans_dur = 0.75

                # Clamp transition duration to available overlap
                td = min(
                    trans_dur,
                    effective_durations[i - 1] - 0.05,
                    effective_durations[i] - 0.05,
                )
                td = max(0.1, td)
                offset = max(0.0, cum_dur - td)

                if trans_type == "cut":
                    # Hard cut - just concat with no overlap
                    out_v = f"cv{i}"
                    out_a = f"ca{i}"
                    filter_parts.append(f"[{prev_v}][{i}:v]concat=n=2:v=1:a=0[{out_v}]")
                    filter_parts.append(f"[{prev_a}][{i}:a]concat=n=2:v=0:a=1[{out_a}]")
                    cum_dur += effective_durations[i]
                elif trans_type == "crossfade":
                    out_v = f"xv{i}"
                    out_a = f"xa{i}"
                    filter_parts.append(
                        f"[{prev_v}][{i}:v]xfade=transition=fade"
                        f":duration={td:.3f}:offset={offset:.3f}[{out_v}]"
                    )
                    filter_parts.append(
                        f"[{prev_a}][{i}:a]acrossfade=d={td:.3f}[{out_a}]"
                    )
                    cum_dur += effective_durations[i] - td
                elif trans_type == "fade_to_black":
                    # Fade out prev to black, then fade in next from black
                    out_v = f"fv{i}"
                    out_a = f"fa{i}"
                    # This is a simplification - proper fade_to_black needs two xfades
                    # For now, treat as crossfade
                    filter_parts.append(
                        f"[{prev_v}][{i}:v]xfade=transition=fade"
                        f":duration={td:.3f}:offset={offset:.3f}[{out_v}]"
                    )
                    filter_parts.append(
                        f"[{prev_a}][{i}:a]acrossfade=d={td:.3f}[{out_a}]"
                    )
                    cum_dur += effective_durations[i] - td
                else:
                    # Unknown type -> fallback to cut
                    out_v = f"cv{i}"
                    out_a = f"ca{i}"
                    filter_parts.append(f"[{prev_v}][{i}:v]concat=n=2:v=1:a=0[{out_v}]")
                    filter_parts.append(f"[{prev_a}][{i}:a]concat=n=2:v=0:a=1[{out_a}]")
                    cum_dur += effective_durations[i]

                prev_v = out_v
                prev_a = out_a

            filter_complex = ";".join(filter_parts)
            cmd = [
                "ffmpeg", "-y",
                *inputs,
                "-filter_complex", filter_complex,
                "-map", f"[{prev_v}]",
                "-map", f"[{prev_a}]",
                "-c:v", "libx264", "-preset", "medium", "-crf", "23",
                "-c:a", "aac", "-b:a", "192k",
                str(out_mp4),
            ]
            rc, _, stderr = await _run_cmd(cmd)
            if rc != 0:
                raise RuntimeError(f"ffmpeg (stitch) failed:\n{stderr[-1000:]}")

        await task_manager.update_progress(task_id, 0.7, "Stitching complete")

        # Mix ambient music if enabled
        if project.music:
            await task_manager.update_progress(task_id, 0.8, "Mixing ambient music bed...")
            try:
                with_music = proj_dir / "output" / f"{project.name}_with_music.mp4"
                await mix_music_under(out_mp4, with_music, project.music_mood)
                with_music.replace(out_mp4)
                logger.info("Ambient music mixed in")
            except Exception as exc:
                logger.warning(f"Music mix failed — continuing without music: {exc}")

        # Generate SRT subtitles using effective (trimmed) durations
        await task_manager.update_progress(task_id, 0.9, "Generating subtitles...")
        srt_path = proj_dir / "output" / f"{project.name}.srt"
        scene_dicts = [
            {"narration": s.narration, "duration": eff_dur}
            for s, eff_dur in zip(included_scenes, effective_durations)
        ]
        write_srt(scene_dicts, srt_path)

        # Update project
        stmt_proj = select(Project).where(Project.id == project_id)
        result_proj = await session.execute(stmt_proj)
        proj = result_proj.scalar_one_or_none()
        if proj:
            proj.status = "rendered"
            proj.output_path = str(out_mp4)
            proj.srt_path = str(srt_path)
            proj.transition_mode = mode

        await session.commit()

    await task_manager.update_progress(task_id, 1.0, "Film rendered successfully!")
    return {
        "output_path": str(out_mp4),
        "srt_path": str(srt_path),
        "num_clips": len(clip_paths),
    }


# ── Full Pipeline ───────────────────────────────────────────

async def run_full_pipeline(
    task_id: str,
    project_id: str,
    num_scenes: int,
    mode: str = "cut",
) -> dict:
    """Run the entire pipeline end-to-end."""
    results = {}

    # Step 1: Script
    await task_manager.update_progress(task_id, 0.0, "Step 1/5: Script generation...")
    results["script"] = await run_script_generation(task_id, project_id, num_scenes)

    # Step 2: Visuals
    await task_manager.update_progress(task_id, 0.2, "Step 2/5: Visual generation...")
    results["visuals"] = await run_visual_generation(task_id, project_id)

    # Step 3: Audio
    await task_manager.update_progress(task_id, 0.4, "Step 3/5: Narration synthesis...")
    results["audio"] = await run_audio_generation(task_id, project_id)

    # Step 4: Clips
    await task_manager.update_progress(task_id, 0.6, "Step 4/5: Clip rendering...")
    results["clips"] = await run_clip_generation(task_id, project_id)

    # Step 5: Stitch
    await task_manager.update_progress(task_id, 0.8, "Step 5/5: Final stitching...")
    results["stitch"] = await run_stitching(task_id, project_id, mode)

    await task_manager.update_progress(task_id, 1.0, "Pipeline complete!")
    return results


# ═══════════════════════════════════════════════════════════════════════════
# SURGICAL SCENE GENERATION (for Director Agent re-rolls)
# ═══════════════════════════════════════════════════════════════════════════

async def run_scene_generation(
    task_id: str,
    project_id: str,
    scene_spec: dict,
) -> dict:
    """
    Generate a single scene from a Director SceneSpec.
    Used by the Director Agent for surgical re-rolls of failed scenes.

    Returns dict with clip_path, visual_path, audio_path, duration.
    """
    from config import settings
    from database import async_session
    from models import Project, Scene, SceneStatus, Character
    from sqlalchemy import select
    from pathlib import Path
    from services.visual_providers import generate_visual
    from services.voice_providers import synthesize_narration
    from utils.ffmpeg_ops import build_ken_burns_clip, trim_clip, mux_audio

    project = await _get_project(project_id)
    proj_dir = _project_dir(project_id)

    # Create a temporary scene object in memory (don't persist to DB)
    scene = Scene(
        id=scene_spec.get("id", "temp"),
        project_id=project_id,
        index=scene_spec.get("index_in_beat", 0),
        narration=scene_spec.get("narration", ""),
        visual_prompt=scene_spec.get("visual_prompt", ""),
        shot_type=scene_spec.get("shot_type", "medium"),
        lens=scene_spec.get("lens", "35mm"),
        lighting=scene_spec.get("lighting", "natural"),
        camera_move=scene_spec.get("camera_move", "static"),
        color_grade=scene_spec.get("color_grade", "cinematic"),
        duration=scene_spec.get("duration_seconds", 5.0),
        status=SceneStatus.VISUAL_PENDING.value,
        character_id=None,
    )

    # Character reference image
    reference_image = None
    char_name = scene_spec.get("characters", [None])[0]
    if char_name:
        async with async_session() as session:
            char_stmt = select(Character).where(
                Character.project_id == project_id,
                Character.name == char_name
            )
            char_result = await session.execute(char_stmt)
            character = char_result.scalar_one_or_none()
            if character and character.reference_image_path:
                reference_image = Path(character.reference_image_path)

    # 1. Visual generation
    visual_path = proj_dir / "images" / f"director_scene_{scene.index:02}.mp4"
    visual_prompt = _compose_cinematic_prompt(scene)

    # Add controlnet/LORA info from scene spec
    controlnet_images = []
    for k, v in scene_spec.get("controlnet_inputs", {}).items():
        if v and Path(v).exists():
            controlnet_images.append(v)

    video_path = await generate_visual(
        visual_prompt=visual_prompt,
        out_path=visual_path,
        aspect=project.aspect,
        seed=project.seed + scene.index,
        duration_seconds=scene.duration,
        reference_image=reference_image,
        controlnet_images=controlnet_images if controlnet_images else None,
    )

    scene.video_path = video_path
    scene.status = SceneStatus.VISUAL_DONE.value

    # 2. Narration audio
    audio_path = proj_dir / "audio" / f"director_scene_{scene.index:02}.mp3"
    await synthesize_narration(
        text=scene.narration,
        voice_key=project.voice,
        out_path=audio_path,
    )
    scene.audio_path = str(audio_path)

    # 3. Clip (Ken Burns + mux)
    clip_path = proj_dir / "clips" / f"director_scene_{scene.index:02}.mp4"
    await build_ken_burns_clip(
        src_path=Path(video_path),
        out_path=clip_path,
        duration=scene.duration,
        audio_path=Path(audio_path) if scene.narration else None,
    )
    scene.clip_path = str(clip_path)
    scene.status = SceneStatus.CLIP_DONE.value

    return {
        "clip_path": str(clip_path),
        "visual_path": video_path,
        "audio_path": str(audio_path),
        "duration": scene.duration,
    }
