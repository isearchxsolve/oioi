"""
Director Loop — Orchestrates the full autonomous pipeline:
Plan → Generate Scenes → Critique → Re-roll (if needed) → Assemble → Export
"""

import asyncio
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from config import settings
from services.director import (
    DirectorPlanner,
    DirectorCritic,
    FallbackCritic,
    ContinuityTracker,
    DirectorPlan,
    DirectorRun,
    DirectorRunEvent,
    DirectorRunStatus,
    CritiqueResult,
    SceneSpec,
    enforce_continuity_on_spec,
)
from services.director.models import Beat
from services.pipeline import run_scene_generation, run_stitching
from services.visual_providers import generate_visual
from services.voice_providers import synthesize_narration
from utils.ffmpeg_ops import build_ken_burns_clip, mux_audio, stitch_concat

logger = logging.getLogger(__name__)


class DirectorLoop:
    """
    Main orchestration loop for autonomous filmmaking.

    Flow:
    1. PLANNING - Call planner (Claude) to create beat sheet + scene specs
    2. For each iteration (max N):
       a. GENERATE - Run pipeline for each scene (visual + audio + clip)
       b. CRITIQUING - Call critic (Gemini Vision) to evaluate all clips
       c. If passed → ASSEMBLE + EXPORT
       d. If failed → RE-ROLL failed scenes (up to max_iterations)
    3. EXPORT - EDL, NLE XML, ProRes master, etc.
    """

    def __init__(
        self,
        run: DirectorRun,
        event_callback: Optional[callable] = None,
    ):
        self.run = run
        self.event_callback = event_callback
        self.planner = DirectorPlanner()
        self.critic = DirectorCritic()
        self.fallback_critic = FallbackCritic()
        self.continuity = ContinuityTracker()
        self.project_dir = settings.projects_path / run.project_id / "director" / run.id
        self.project_dir.mkdir(parents=True, exist_ok=True)

    async def _emit(self, event_type: str, message: str, data: dict = None, scene_index: int = None, beat_slug: str = None):
        """Emit SSE event."""
        self.run.updated_at = datetime.utcnow()
        event = DirectorRunEvent(
            run_id=self.run.id,
            event_type=event_type,
            iteration=self.run.current_iteration,
            scene_index=scene_index,
            beat_slug=beat_slug,
            message=message,
            data=data or {},
        )
        if self.event_callback:
            await self.event_callback(event)

    async def run_full_pipeline(self) -> DirectorRun:
        """
        Execute the complete autonomous pipeline.
        Returns the updated DirectorRun with results.
        """
        try:
            # ──────────────────────────────────────────────
            # PHASE 1: PLANNING
            # ──────────────────────────────────────────────
            self.run.status = DirectorRunStatus.PLANNING
            await self._emit("planning", "Planning film structure with AI Director...")

            plan = await self._planning_phase()
            self.run.plan = plan

            # Initialize continuity from plan
            self.continuity.initialize_from_plan(plan.continuity_setup.dict())
            self.run.continuity_state = self.continuity.state

            # ──────────────────────────────────────────────
            # PHASE 2: ITERATIVE GENERATION + CRITIQUE
            # ──────────────────────────────────────────────
            for iteration in range(self.run.max_iterations):
                self.run.current_iteration = iteration
                logger.info(f"Director run {self.run.id}: Iteration {iteration + 1}/{self.run.max_iterations}")

                # Generate all scenes
                clips = await self._generation_phase(plan.scene_specs)

                # Critique
                critique = await self._critique_phase(plan, clips)

                self.run.critique_history.append(critique)
                self.run.total_generations += len(clips)

                # Check if passed
                if critique.passed:
                    logger.info(f"Director run {self.run.id}: PASSED at iteration {iteration + 1}")
                    break

                # Determine which scenes need re-roll
                failed_scenes = self._identify_failed_scenes(critique, plan.scene_specs)
                if not failed_scenes:
                    logger.warning("Critique failed but no specific scenes identified for re-roll")
                    break

                # Re-roll failed scenes
                await self._re_roll_phase(failed_scenes, clips)

            # ──────────────────────────────────────────────
            # PHASE 3: FINAL ASSEMBLY & EXPORT
            # ──────────────────────────────────────────────
            self.run.status = DirectorRunStatus.COMPLETED
            await self._emit("completed", "Final assembly and export...", {"total_iterations": self.run.current_iteration + 1})

            final_outputs = await self._assembly_and_export_phase(plan)

            self.run.final_clips = final_outputs.get("clips", [])
            self.run.final_audio = final_outputs.get("audio", [])
            self.run.edl_path = final_outputs.get("edl")
            self.run.fcpxml_path = final_outputs.get("fcpxml")
            self.run.premiere_xml_path = final_outputs.get("premiere_xml")
            self.run.davinci_drt_path = final_outputs.get("davinci_drt")
            self.run.prores_master_path = final_outputs.get("prores_master")
            self.run.completed_at = datetime.utcnow()

            logger.info(f"Director run {self.run.id} completed successfully")
            return self.run

        except Exception as e:
            self.run.status = DirectorRunStatus.FAILED
            logger.exception(f"Director run {self.run.id} failed: {e}")
            await self._emit("error", f"Pipeline failed: {str(e)}", {"error": str(e)})
            raise

    # ═══════════════════════════════════════════════════════════════
    # PLANNING PHASE
    # ═══════════════════════════════════════════════════════════════

    async def _planning_phase(self) -> DirectorPlan:
        """Call planner to create beat sheet and scene specs."""
        plan_dict = await self.planner.generate_plan(
            idea=self.run.idea,
            genre=self.run.genre,
            target_duration=self.run.target_duration,
            beats_per_minute=1.5,
            existing_continuity=self.run.continuity_state.to_dict() if self.run.continuity_state.characters else None,
        )

        # Convert to typed models
        beats = [Beat(**b) for b in plan_dict["beats"]]
        scene_specs = [SceneSpec(**s) for s in plan_dict["scene_specs"]]
        continuity_setup = ContinuitySetup(**plan_dict["continuity_setup"])

        return DirectorPlan(
            beats=beats,
            scene_specs=scene_specs,
            continuity_setup=continuity_setup,
            estimated_total_duration=sum(s.duration_seconds for s in scene_specs),
            target_genre=self.run.genre,
        )

    # ═══════════════════════════════════════════════════════════════
    # GENERATION PHASE
    # ═══════════════════════════════════════════════════════════════

    async def _generation_phase(self, scene_specs: list[SceneSpec]) -> list[dict]:
        """
        Generate all scenes in the plan.
        Returns list of dicts with clip_path, audio_path, scene_spec, beat_slug.
        """
        self.run.status = DirectorRunStatus.GENERATING
        clips = []

        for i, scene in enumerate(scene_specs):
            self.run.current_scene_index = i
            beat = next((b for b in self.run.plan.beats if b.slug == scene.beat_id), None)
            beat_slug = beat.slug if beat else "unknown"

            await self._emit(
                "generating_scene",
                f"Generating scene {i + 1}/{len(scene_specs)}: {beat_slug}",
                {"scene_index": i, "beat_slug": beat_slug, "total": len(scene_specs)},
                scene_index=i,
                beat_slug=beat_slug,
            )

            # Enforce continuity on scene spec
            scene = enforce_continuity_on_spec(scene, self.continuity.state)

            # Generate scene (visual + audio + clip)
            clip_data = await self._generate_single_scene(scene, i)
            clips.append(clip_data)

            await self._emit(
                "scene_done",
                f"Scene {i + 1} complete",
                {"scene_index": i, "clip_path": clip_data["clip_path"]},
                scene_index=i,
                beat_slug=beat_slug,
            )

        return clips

    async def _generate_single_scene(self, scene: SceneSpec, scene_index: int) -> dict:
        """Generate one scene: visual → audio → clip."""
        scene_dir = self.project_dir / f"scene_{scene_index:03d}_{scene.beat_id}"
        scene_dir.mkdir(parents=True, exist_ok=True)

        # 1. Visual generation
        visual_path = scene_dir / "visual.mp4"
        visual_prompt = self._build_visual_prompt(scene)

        reference_image = None
        if scene.reference_images:
            reference_image = Path(scene.reference_images[0]) if Path(scene.reference_images[0]).exists() else None

        controlnet_images = []
        for k, v in scene.controlnet_inputs.items():
            if v and Path(v).exists():
                controlnet_images.append(v)

        await generate_visual(
            visual_prompt=visual_prompt,
            out_path=visual_path,
            aspect="16:9",  # TODO: from project
            duration_seconds=scene.duration_seconds,
            reference_image=reference_image,
            controlnet_images=controlnet_images,
        )

        # 2. Narration audio
        audio_path = scene_dir / "narration.wav"
        await synthesize_narration(
            text=scene.narration,
            out_path=audio_path,
        ) if scene.narration else audio_path.write_bytes(b"")

        # 3. Clip (Ken Burns / mux)
        clip_path = scene_dir / "clip.mp4"
        await build_ken_burns_clip(
            src_path=visual_path,
            out_path=clip_path,
            duration=scene.duration_seconds,
            audio_path=audio_path,
        )

        # 4. Update continuity
        self.continuity.state = self.continuity.update_after_generation(scene, scene_index, clip_path)
        self.run.continuity_state = self.continuity.state

        return {
            "scene_spec": scene,
            "beat_slug": scene.beat_id,
            "visual_path": str(visual_path),
            "audio_path": str(audio_path),
            "clip_path": str(clip_path),
            "scene_index": scene_index,
        }

    def _build_visual_prompt(self, scene: SceneSpec) -> str:
        """Build the full visual prompt with continuity additions."""
        parts = [scene.visual_prompt]

        # Shot type, lens, lighting, camera move, color grade
        if scene.shot_type:
            parts.append(f"shot type: {scene.shot_type}")
        if scene.lens:
            parts.append(f"lens: {scene.lens}")
        if scene.lighting:
            parts.append(f"lighting: {scene.lighting}")
        if scene.camera_move:
            parts.append(f"camera: {scene.camera_move}")
        if scene.color_grade:
            parts.append(f"color grade: {scene.color_grade}")

        # Continuity: character descriptions
        for char_name, desc in scene.lora_paths.items():
            parts.append(f"character {char_name}: {desc}")

        # Continuity: location
        if scene.location:
            parts.append(f"location: {scene.location}")

        # Global style
        global_style = self.continuity.state.global_lighting_mood
        if global_style:
            parts.append(f"global mood: {global_style}")

        return ", ".join(parts)

    # ═══════════════════════════════════════════════════════════════
    # CRITIQUE PHASE
    # ═══════════════════════════════════════════════════════════════

    async def _critique_phase(self, plan: DirectorPlan, clips: list[dict]) -> CritiqueResult:
        """Run critic on all generated clips."""
        self.run.status = DirectorRunStatus.CRITIQUING
        await self._emit("critiquing", "AI Critic evaluating generated clips...")

        clip_paths = [c["clip_path"] for c in clips]
        audio_paths = [c["audio_path"] for c in clips if c["audio_path"]]
        beat_slugs = [c["beat_slug"] for c in clips]

        try:
            critique = await self.critic.critique_clips(
                run_id=self.run.id,
                iteration=self.run.current_iteration,
                beats=[b.dict() for b in plan.beats],
                scene_specs=[s.dict() for s in plan.scene_specs],
                clip_paths=clip_paths,
                audio_paths=audio_paths,
                continuity_state=self.run.continuity_state.to_dict(),
                critic_threshold=self.run.critic_threshold,
            )
        except Exception as e:
            logger.warning(f"VLM critic failed, using fallback: {e}")
            await self._emit("critiquing", "VLM unavailable, using heuristic critic...")
            critique = await self.fallback_critic.critique_clips(
                run_id=self.run.id,
                iteration=self.run.current_iteration,
                beats=[b.dict() for b in plan.beats],
                scene_specs=[s.dict() for s in plan.scene_specs],
                clip_paths=clip_paths,
                audio_paths=audio_paths,
                continuity_state=self.run.continuity_state.to_dict(),
                critic_threshold=self.run.critic_threshold,
            )

        return CritiqueResult(**critique)

    def _identify_failed_scenes(self, critique: CritiqueResult, scene_specs: list[SceneSpec]) -> list[int]:
        """Identify which scene indices need re-rolling based on critique."""
        failed = []

        # Scenes with critical issues
        for issue in critique.get_critical_issues():
            failed.append(issue.scene_index)

        # Scenes with major issues
        for issue in critique.get_major_issues():
            if issue.scene_index not in failed:
                failed.append(issue.scene_index)

        # Scenes below threshold
        for idx, score in critique.per_scene_scores.items():
            if score < self.run.critic_threshold and idx not in failed:
                failed.append(idx)

        return sorted(set(failed))

    # ═══════════════════════════════════════════════════════════════
    # RE-ROLL PHASE
    # ═══════════════════════════════════════════════════════════════

    async def _re_roll_phase(self, failed_indices: list[int], clips: list[dict]):
        """Re-generate failed scenes with critic's fix suggestions."""
        if not failed_indices:
            return

        self.run.status = DirectorRunStatus.RE_ROLLING
        self.run.total_re_rolls += len(failed_indices)

        plan = self.run.plan
        critique = self.run.critique_history[-1]

        await self._emit(
            "re_rolling",
            f"Re-rolling {len(failed_indices)} failed scenes...",
            {"failed_indices": failed_indices},
        )

        # Build fix suggestions map
        fix_suggestions = {}
        for issue in critique.issues:
            if issue.scene_index in failed_indices:
                fix_suggestions.setdefault(issue.scene_index, []).append(issue.fix_suggestion)

        for idx in failed_indices:
            scene = plan.scene_specs[idx]
            beat = next((b for b in plan.beats if b.slug == scene.beat_id), None)

            await self._emit(
                "generating_scene",
                f"Re-rolling scene {idx + 1}: {scene.beat_id}",
                {"scene_index": idx, "beat_slug": scene.beat_id},
                scene_index=idx,
                beat_slug=scene.beat_id,
            )

            # Apply fix suggestions to scene spec
            if idx in fix_suggestions:
                fixes = "; ".join(fix_suggestions[idx])
                scene.visual_prompt = f"{scene.visual_prompt}. FIX: {fixes}"

            # Re-generate
            clip_data = await self._generate_single_scene(scene, idx)
            clips[idx] = clip_data  # Replace in place

    # ═══════════════════════════════════════════════════════════════
    # ASSEMBLY & EXPORT PHASE
    # ═══════════════════════════════════════════════════════════════

    async def _assembly_and_export_phase(self, plan: DirectorPlan) -> dict:
        """Stitch final clips, generate EDL/NLE exports, ProRes master."""
        from services.director.exporter import NLEExporter

        clips = [c["clip_path"] for c in sorted(
            [c for c in self.run.critique_history[-1].per_scene_scores.keys()],
            key=lambda x: x
        )] if self.run.critique_history else [c["clip_path"] for c in clips]

        # Actually we need the final clips from the last generation
        # Get clips from last iteration
        last_critique = self.run.critique_history[-1] if self.run.critique_history else None
        if last_critique:
            # Use the clips that were critiqued
            final_clips = []
            # This would need to track which clips correspond to which scenes
            # For now, use the last generated clips

        # Use the project's run_stitching for final assembly
        # But first we need to assemble in order
        clip_paths = [c["clip_path"] for c in clips]

        # Stitch with transitions from scene specs
        transitions = []
        for scene in plan.scene_specs:
            t = scene.transition_out
            if t not in ("cut", "crossfade", "fade_out"):
                t = "cut"
            transitions.append(t)

        output_path = self.project_dir / "final_film.mp4"
        srt_path = self.project_dir / "final_film.srt"

        await run_stitching(
            task_id=self.run.id,
            project_id=self.run.project_id,
            clip_paths=clip_paths,
            output_path=output_path,
            srt_path=srt_path,
            transition_mode="per_scene",
            transitions=transitions,
        )

        # Export NLE formats
        exporter = NLEExporter()
        exports = await exporter.export_all(
            project_dir=self.project_dir,
            clips=clips,
            plan=plan,
            final_video=output_path,
            srt_path=srt_path,
        )

        return {
            "clips": clip_paths,
            "audio": [c["audio_path"] for c in clips],
            **exports,
        }


# ═══════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS (async wrappers for pipeline services)
# ═══════════════════════════════════════════════════════════════════════════

async def generate_visual(
    visual_prompt: str,
    out_path: Path,
    aspect: str = "16:9",
    duration_seconds: float = 5.0,
    reference_image: Optional[Path] = None,
    controlnet_images: list[str] = None,
) -> str:
    """Generate visual using the visual provider."""
    from services.visual_providers import get_visual_provider

    provider = get_visual_provider()
    return await provider.generate(
        visual_prompt=visual_prompt,
        out_path=out_path,
        aspect=aspect,
        duration_seconds=duration_seconds,
        reference_image=reference_image,
    )


async def synthesize_narration(text: str, out_path: Path) -> str:
    """Generate narration audio."""
    from services.voice_providers import synthesize

    return await synthesize(text=text, out_path=out_path)