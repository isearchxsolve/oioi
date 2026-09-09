"""Animation Pipeline Orchestrator — IMPLEMENTATION.

This module implements the `AgentOrchestrator` ABC defined in `backend/agent_contracts.py`.
It drives the 7-agent idea → short-film pipeline by selecting free-tier adapters through
the `ProviderRegistry`. Every inference routes through the registry's
`get_adapter(capability, prefer=...)` so failover, health tracking, and cooldown apply.

NVIDIA NIM is a TOTAL NO-GO (AC-10). This module never imports `backend.nim_client`.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import async_session_maker
from app.core.config import settings

from app.models.agent_execution import AgentExecution
from agent_contracts import (
    AgentOrchestrator,
    ScriptwriterInput,
    ScriptwriterOutput,
    ArtDirectorInput,
    ArtDirectorOutput,
    CharacterDesignerInput,
    CharacterDesignerOutput,
    SceneDesignerInput,
    SceneDesignerOutput,
    StoryboardArtistInput,
    StoryboardArtistOutput,
    AnimatorInput,
    AnimatorOutput,
    SoundDirectorInput,
    SoundDirectorOutput,
    DirectorInput,
    DirectorOutput,
)
from providers.registry import ProviderRegistry, get_registry
from providers.base import ChatCompletionResponse


def _production_runtime() -> bool:
    """Read deployment mode at construction time, including test overrides."""

    return os.getenv("APP_ENV", settings.APP_ENV).strip().lower() in {"production", "prod"}


class AnimationAgentOrchestrator(AgentOrchestrator):
    """Orchestrator that runs the 7-agent animation pipeline."""

    def __init__(
        self,
        registry: Optional[ProviderRegistry] = None,
        db_session: Optional[Session] = None,
        model: Optional[str] = None,
        film_orchestrator: Optional[Any] = None,
        chat_client: Optional[Any] = None,
    ) -> None:
        if chat_client is None and _production_runtime():
            raise RuntimeError(
                "canonical ChatPoolClient is required in production; "
                "direct ProviderRegistry execution is permanently retired"
            )
        self.registry = registry or get_registry()
        self.db_session = db_session
        # Which LLM the 8 agent calls below ask for. Was settings.DEFAULT_CHAT_MODEL inlined at every
        # call site, which meant the UI's "AI Model" dropdown could not influence a run: the frontend
        # tracked selectedModel in state and never sent it, and there was nowhere to send it to.
        self.model = model or settings.DEFAULT_CHAT_MODEL
        # Optional by design: the legacy crew UI can still be used for ideation, but
        # callers that supply the durable Film Orchestrator get an explicit Director
        # approved hand-off instead of a second, disconnected render workflow.
        self.film_orchestrator = film_orchestrator
        # The approved customer path supplies a ChatPoolClient here.  The old
        # ProviderRegistry remains injectable solely for the explicitly retired
        # local demo path; customer crew work must never select an upstream
        # provider inside OiiOii.
        self.chat_client = chat_client

    # ------------------------------------------------------------------ Helper methods
    async def _persist_execution(
        self,
        project_id: str,
        agent_type: str,
        input_data: dict,
        model_id: Optional[str] = None,
        prompt: Optional[str] = None,
    ) -> Optional[AgentExecution]:
        """Create and persist an AgentExecution row with status 'pending'."""
        if self.db_session is None:
            # A durable film admission owns production history.  The lightweight
            # crew runner deliberately has no parallel legacy AgentExecution
            # store to keep one customer production lineage.
            return None
        execution = AgentExecution(
            id=str(uuid.uuid4()),
            project_id=project_id,
            agent_type=agent_type,
            status="pending",
            input_data=input_data,
            model_id=model_id,
            prompt=prompt,
        )
        self.db_session.add(execution)
        await self.db_session.commit()
        await self.db_session.refresh(execution)
        return execution

    async def _update_execution(
        self,
        execution: Optional[AgentExecution],
        *,
        status: str,
        output_data: Optional[dict] = None,
        error: Optional[str] = None,
        tokens_used: Optional[int] = None,
        duration_seconds: Optional[float] = None,
        model_id: Optional[str] = None,
    ) -> None:
        """Update an AgentExecution row with results or error."""
        if execution is None:
            return
        execution.status = status
        if output_data is not None:
            execution.output_data = output_data
        if error is not None:
            execution.error = error
        if tokens_used is not None:
            execution.tokens_used = tokens_used
        if duration_seconds is not None:
            execution.duration_seconds = duration_seconds
        if model_id is not None:
            execution.model_id = model_id
        import datetime
        if status in ("completed", "failed"):
            execution.completed_at = datetime.datetime.utcnow()
        self.db_session.add(execution)
        await self.db_session.commit()

    async def _call_adapter(
        self,
        capability: str,
        request: Any,
        prefer: Optional[str] = None,
    ) -> Any:
        """Call the provider adapter for a capability and return the raw response."""
        if self.chat_client is not None:
            if capability != "chat" or not (hasattr(request, "model") and hasattr(request, "messages")):
                raise RuntimeError("the canonical crew runner supports chat work only")
            # The supply contract accepts one OpenAI-shaped user message.  Preserve
            # every system/user instruction in order without exposing provider
            # routing to this consumer.
            transcript = "\n\n".join(
                f"{str(message.get('role', 'user')).upper()}:\n{message.get('content', '')}"
                for message in request.messages
            )
            reply = await self.chat_client.message(
                transcript,
                max_tokens=int(request.max_tokens or 2048),
                model="session-pool/auto",
                json_mode=True,
            )
            return ChatCompletionResponse(
                id=f"consumer-{uuid.uuid4().hex}",
                model="session-pool/auto",
                choices=[{"index": 0, "message": {"role": "assistant", "content": reply.text}, "finish_reason": "stop"}],
                usage={"provider": reply.provider, "session": reply.session, "tenant": reply.tenant},
            )
        adapter = await self.registry.get_adapter(capability=capability, prefer=prefer)
        # Dispatch based on request type
        if hasattr(request, "model") and hasattr(request, "messages"):  # ChatCompletionRequest
            return await adapter.chat_completion(request)
        if hasattr(request, "prompt") and hasattr(request, "n"):  # ImageGenerationRequest
            return await adapter.generate_image(request)
        if hasattr(request, "prompt") and hasattr(request, "model") and hasattr(request, "first_frame"):  # VideoGenerationRequest
            return await adapter.generate_video(request)
        if hasattr(request, "input") and hasattr(request, "model"):  # EmbeddingRequest
            return await adapter.create_embedding(request)
        raise TypeError(f"Unsupported request type: {type(request)}")

    def _parse_json(self, content: str) -> dict:
        """Parse the gateway's JSON response strictly and fail loudly on garbage."""
        try:
            return json.loads(content)
        except Exception as exc:
            raise ValueError(f"Failed to parse JSON: {exc}") from exc

    # ------------------------------------------------------------------ Agent implementations
    async def run_scriptwriter(self, input: ScriptwriterInput, project_id: Optional[str] = None) -> ScriptwriterOutput:
        """Run the Scriptwriter agent."""
        project_id = project_id or "default"
        # Persist execution
        execution = await self._persist_execution(
            project_id=project_id,
            agent_type="scriptwriter",
            input_data=input.dict(),
            prompt=input.prompt,
        )
        start = time.time()
        try:
            # Build prompt for LLM
            system_prompt = """You are an expert Scriptwriter for animation. Given a user idea, produce a JSON object with:
            - title: string
            - description: string
            - scenes: list of objects, each with: description (string), duration (int in seconds)
            - characters: list of strings (character names or descriptions)
            Ensure the JSON is valid and matches the expected schema."""
            user_prompt = f"Idea: {input.prompt}\n"
            if input.duration:
                user_prompt += f"Desired total duration: {input.duration} seconds.\n"
            if input.style:
                user_prompt += f"Animation style: {input.style}.\n"

            from providers.base import ChatCompletionRequest
            request = ChatCompletionRequest(
                model=self.model,  # default; registry will override based on priority
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7,
                max_tokens=settings.AGENT_MAX_TOKENS,
                response_format={"type": "json_object"},
            )
            # Note: We cannot guarantee the model supports json_object; we'll parse anyway.
            response = await self._call_adapter("chat", request)
            # Extract text from response
            content = response.choices[0]["message"]["content"]
            # Parse JSON
            data = self._parse_json(content)
            # Validate and construct output
            output = ScriptwriterOutput(
                title=data.get("title", "Untitled"),
                description=data.get("description", ""),
                scenes=data.get("scenes", []),
                characters=data.get("characters", []),
            )
            # Update execution
            await self._update_execution(
                execution,
                status="completed",
                output_data=output.dict(),
                tokens_used=response.usage.get("total_tokens"),
                duration_seconds=time.time() - start,
                model_id=request.model,
            )
            return output
        except Exception as exc:
            import traceback
            traceback.print_exc()
            await self._update_execution(
                execution,
                status="failed",
                error=str(exc),
                duration_seconds=time.time() - start,
            )
            raise

    async def run_art_director(self, input: ArtDirectorInput, project_id: Optional[str] = None) -> ArtDirectorOutput:
        """Run the Art Director agent."""
        project_id = project_id or "default"
        execution = await self._persist_execution(
            project_id=project_id,
            agent_type="art_director",
            input_data=input.dict(),
        )
        start = time.time()
        try:
            system_prompt = """You are an Art Director for animation. Given a scriptwriter's output, produce a JSON object with:
            - visual_style: string (e.g., cyberpunk, pastel, dark fantasy)
            - color_palette: list of hex color codes (strings)
            - character_sheet_prompt: string (prompt for generating character sheets)
            - scene_style_prompt: string (prompt for generating scene backgrounds)
            """
            user_prompt = f"Scriptwriter output: {json.dumps(input.scriptwriter_output.dict(), indent=2)}"
            from providers.base import ChatCompletionRequest
            request = ChatCompletionRequest(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7,
                max_tokens=settings.AGENT_MAX_TOKENS,
                response_format={"type": "json_object"},
            )
            response = await self._call_adapter("chat", request)
            content = response.choices[0]["message"]["content"]
            data = self._parse_json(content)
            output = ArtDirectorOutput(
                visual_style=data.get("visual_style", "anime"),
                color_palette=data.get("color_palette", ["#FFFFFF", "#000000"]),
                character_sheet_prompt=data.get("character_sheet_prompt", ""),
                scene_style_prompt=data.get("scene_style_prompt", ""),
            )
            await self._update_execution(
                execution,
                status="completed",
                output_data=output.dict(),
                tokens_used=response.usage.get("total_tokens"),
                duration_seconds=time.time() - start,
                model_id=request.model,
            )
            return output
        except Exception as exc:
            import traceback
            traceback.print_exc()
            await self._update_execution(
                execution,
                status="failed",
                error=str(exc),
                duration_seconds=time.time() - start,
            )
            raise

    async def run_character_designer(self, input: CharacterDesignerInput, project_id: Optional[str] = None) -> CharacterDesignerOutput:
        """Run the Character Designer agent."""
        project_id = project_id or "default"
        execution = await self._persist_execution(
            project_id=project_id,
            agent_type="character_designer",
            input_data=input.dict(),
        )
        start = time.time()
        try:
            system_prompt = """You are a Character Designer. Given an art director's output, produce a JSON object with:
            - characters: list of objects, each with: name (string), description (string), prompt (string for image generation)
            """
            user_prompt = f"Art director output: {json.dumps(input.art_director_output.dict(), indent=2)}"
            from providers.base import ChatCompletionRequest
            request = ChatCompletionRequest(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7,
                max_tokens=settings.AGENT_MAX_TOKENS,
                response_format={"type": "json_object"},
            )
            response = await self._call_adapter("chat", request)
            content = response.choices[0]["message"]["content"]
            data = self._parse_json(content)
            output = CharacterDesignerOutput(
                characters=data.get("characters", []),
            )
            await self._update_execution(
                execution,
                status="completed",
                output_data=output.dict(),
                tokens_used=response.usage.get("total_tokens"),
                duration_seconds=time.time() - start,
                model_id=request.model,
            )
            return output
        except Exception as exc:
            import traceback
            traceback.print_exc()
            await self._update_execution(
                execution,
                status="failed",
                error=str(exc),
                duration_seconds=time.time() - start,
            )
            raise

    async def run_scene_designer(self, input: SceneDesignerInput, project_id: Optional[str] = None) -> SceneDesignerOutput:
        """Run the Scene Designer agent."""
        project_id = project_id or "default"
        execution = await self._persist_execution(
            project_id=project_id,
            agent_type="scene_designer",
            input_data=input.dict(),
        )
        start = time.time()
        try:
            system_prompt = """You are a Scene Designer. Given an art director's output, produce a JSON object with:
            - scenes: list of objects, each with: description (string), prompt (string for image generation), style (string)
            """
            user_prompt = f"Art director output: {json.dumps(input.art_director_output.dict(), indent=2)}"
            from providers.base import ChatCompletionRequest
            request = ChatCompletionRequest(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7,
                max_tokens=settings.AGENT_MAX_TOKENS,
                response_format={"type": "json_object"},
            )
            response = await self._call_adapter("chat", request)
            content = response.choices[0]["message"]["content"]
            data = self._parse_json(content)
            output = SceneDesignerOutput(
                scenes=data.get("scenes", []),
            )
            await self._update_execution(
                execution,
                status="completed",
                output_data=output.dict(),
                tokens_used=response.usage.get("total_tokens"),
                duration_seconds=time.time() - start,
                model_id=request.model,
            )
            return output
        except Exception as exc:
            import traceback
            traceback.print_exc()
            await self._update_execution(
                execution,
                status="failed",
                error=str(exc),
                duration_seconds=time.time() - start,
            )
            raise

    async def run_storyboard_artist(
        self, input: StoryboardArtistInput, project_id: Optional[str] = None
    ) -> StoryboardArtistOutput:
        """Run the Storyboard Artist agent.

        Sits between Scene Designer and Animator, which is where it sits in a real crew: the panels
        are the thing a director signs off on before anyone spends money animating. That ordering is
        not cosmetic here -- the Animator downstream turns each panel into one paid video clip, so a
        shot list agreed in advance is cheaper than one discovered by rendering.
        """
        project_id = project_id or "default"
        execution = await self._persist_execution(
            project_id=project_id,
            agent_type="storyboard_artist",
            input_data=input.dict(),
        )
        start = time.time()
        try:
            system_prompt = """You are a Storyboard Artist. Given scene designs and character designs, produce a JSON object with:
            - panels: list of objects, each with: scene (int), shot (string, e.g. "wide establishing"), composition (string, what is in frame and where), camera (string, e.g. "slow push in"), action (string, what happens in the panel)
            Produce one panel per scene, in scene order, and keep the camera language consistent between consecutive panels.
            """
            user_prompt = f"Scene designer output: {json.dumps(input.scene_designer_output.dict(), indent=2)}\n"
            user_prompt += f"Character designer output: {json.dumps(input.character_designer_output.dict(), indent=2)}"
            from providers.base import ChatCompletionRequest
            request = ChatCompletionRequest(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7,
                max_tokens=settings.AGENT_MAX_TOKENS,
                response_format={"type": "json_object"},
            )
            response = await self._call_adapter("chat", request)
            content = response.choices[0]["message"]["content"]
            data = self._parse_json(content)
            output = StoryboardArtistOutput(
                panels=data.get("panels", []),
            )
            await self._update_execution(
                execution,
                status="completed",
                output_data=output.dict(),
                tokens_used=response.usage.get("total_tokens"),
                duration_seconds=time.time() - start,
                model_id=request.model,
            )
            return output
        except Exception as exc:
            import traceback
            traceback.print_exc()
            await self._update_execution(
                execution,
                status="failed",
                error=str(exc),
                duration_seconds=time.time() - start,
            )
            raise

    async def run_animator(self, input: AnimatorInput, project_id: Optional[str] = None) -> AnimatorOutput:
        """Run the Animator agent."""
        project_id = project_id or "default"
        execution = await self._persist_execution(
            project_id=project_id,
            agent_type="animator",
            input_data=input.dict(),
        )
        start = time.time()
        try:
            system_prompt = """You are an Animator. Given scene and character designs, produce a JSON object with:
            - animations: list of objects, each with: scene (int), prompt (string for video generation), duration (int in seconds)
            """
            user_prompt = f"Scene designer output: {json.dumps(input.scene_designer_output.dict(), indent=2)}\n"
            user_prompt += f"Character designer output: {json.dumps(input.character_designer_output.dict(), indent=2)}"
            if input.storyboard_artist_output is not None:
                # Panels are the approved shot list. Following them keeps the video prompts in the
                # order and camera language the director already signed off on, instead of the
                # Animator re-inventing coverage scene by scene.
                user_prompt += (
                    f"\nApproved storyboard panels (follow these shots, one animation per panel, "
                    f"in this order): "
                    f"{json.dumps(input.storyboard_artist_output.dict(), indent=2)}"
                )
            from providers.base import ChatCompletionRequest
            request = ChatCompletionRequest(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7,
                max_tokens=settings.AGENT_MAX_TOKENS,
                response_format={"type": "json_object"},
            )
            response = await self._call_adapter("chat", request)
            content = response.choices[0]["message"]["content"]
            data = self._parse_json(content)
            output = AnimatorOutput(
                animations=data.get("animations", []),
            )
            await self._update_execution(
                execution,
                status="completed",
                output_data=output.dict(),
                tokens_used=response.usage.get("total_tokens"),
                duration_seconds=time.time() - start,
                model_id=request.model,
            )
            return output
        except Exception as exc:
            import traceback
            traceback.print_exc()
            await self._update_execution(
                execution,
                status="failed",
                error=str(exc),
                duration_seconds=time.time() - start,
            )
            raise

    async def run_sound_director(self, input: SoundDirectorInput, project_id: Optional[str] = None) -> SoundDirectorOutput:
        """Run the Sound Director agent."""
        project_id = project_id or "default"
        execution = await self._persist_execution(
            project_id=project_id,
            agent_type="sound_director",
            input_data=input.dict(),
        )
        start = time.time()
        try:
            system_prompt = """You are a Sound Director. Given a script and animation plan, produce a JSON object with:
            - music_prompt: string (prompt for generating background music)
            - sound_effects: list of objects, each with: scene (int), description (string), prompt (string for audio generation)
            - voice_over: optional string (voice over script or description)
            """
            user_prompt = f"Scriptwriter output: {json.dumps(input.scriptwriter_output.dict(), indent=2)}\n"
            user_prompt += f"Animator output: {json.dumps(input.animator_output.dict(), indent=2)}"
            from providers.base import ChatCompletionRequest
            request = ChatCompletionRequest(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7,
                max_tokens=settings.AGENT_MAX_TOKENS,
                response_format={"type": "json_object"},
            )
            response = await self._call_adapter("chat", request)
            content = response.choices[0]["message"]["content"]
            data = self._parse_json(content)
            output = SoundDirectorOutput(
                music_prompt=data.get("music_prompt", ""),
                sound_effects=data.get("sound_effects", []),
                voice_over=data.get("voice_over"),
            )
            await self._update_execution(
                execution,
                status="completed",
                output_data=output.dict(),
                tokens_used=response.usage.get("total_tokens"),
                duration_seconds=time.time() - start,
                model_id=request.model,
            )
            return output
        except Exception as exc:
            import traceback
            traceback.print_exc()
            await self._update_execution(
                execution,
                status="failed",
                error=str(exc),
                duration_seconds=time.time() - start,
            )
            raise

    async def run_director(self, input: DirectorInput, project_id: Optional[str] = None) -> DirectorOutput:
        """Run the Director agent."""
        project_id = project_id or "default"
        execution = await self._persist_execution(
            project_id=project_id,
            agent_type="director",
            input_data=input.dict(),
        )
        start = time.time()
        try:
            system_prompt = """You are a Director. Given all the outputs from the pipeline, produce a JSON object with:
            - final_notes: string (final production notes and approval)
            - approved: boolean (whether the director approves the production)
            - revisions: list of strings (list of requested revisions, if any)
            """
            user_prompt = f"Scriptwriter: {json.dumps(input.scriptwriter_output.dict(), indent=2)}\n"
            user_prompt += f"Art Director: {json.dumps(input.art_director_output.dict(), indent=2)}\n"
            user_prompt += f"Character Designer: {json.dumps(input.character_designer_output.dict(), indent=2)}\n"
            user_prompt += f"Scene Designer: {json.dumps(input.scene_designer_output.dict(), indent=2)}\n"
            if input.storyboard_artist_output is not None:
                user_prompt += f"Storyboard Artist: {json.dumps(input.storyboard_artist_output.dict(), indent=2)}\n"
            user_prompt += f"Animator: {json.dumps(input.animator_output.dict(), indent=2)}\n"
            user_prompt += f"Sound Director: {json.dumps(input.sound_director_output.dict(), indent=2)}"
            from providers.base import ChatCompletionRequest
            request = ChatCompletionRequest(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7,
                max_tokens=settings.AGENT_MAX_TOKENS,
                response_format={"type": "json_object"},
            )
            response = await self._call_adapter("chat", request)
            content = response.choices[0]["message"]["content"]
            data = self._parse_json(content)
            output = DirectorOutput(
                final_notes=data.get("final_notes", ""),
                approved=data.get("approved", False),
                revisions=data.get("revisions", []),
            )
            await self._update_execution(
                execution,
                status="completed",
                output_data=output.dict(),
                tokens_used=response.usage.get("total_tokens"),
                duration_seconds=time.time() - start,
                model_id=request.model,
            )
            return output
        except Exception as exc:
            import traceback
            traceback.print_exc()
            await self._update_execution(
                execution,
                status="failed",
                error=str(exc),
                duration_seconds=time.time() - start,
            )
            raise

    # ------------------------------------------------------------------ Pipeline and retry
    async def run_pipeline(
        self,
        prompt: str,
        duration: Optional[int] = None,
        style: Optional[str] = None,
        project_id: Optional[str] = None,
        image_refs: Optional[List[str]] = None,
        character_refs: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Run the full agent pipeline and return all intermediate outputs as a dict."""
        project_id = project_id or "default"
        # Scriptwriter
        script_input = ScriptwriterInput(prompt=prompt, duration=duration, style=style)
        script_output = await self.run_scriptwriter(script_input, project_id=project_id)
        # Art Director
        art_input = ArtDirectorInput(scriptwriter_output=script_output)
        art_output = await self.run_art_director(art_input, project_id=project_id)
        # Character Designer
        char_input = CharacterDesignerInput(art_director_output=art_output)
        char_output = await self.run_character_designer(char_input, project_id=project_id)
        # Scene Designer
        scene_input = SceneDesignerInput(art_director_output=art_output)
        scene_output = await self.run_scene_designer(scene_input, project_id=project_id)
        # Storyboard Artist: the Director-approved panel order is the hand-off from
        # design to animation.  Omitting this call made the implemented stage invisible
        # and let the Animator invent a fresh, potentially expensive shot list.
        storyboard_input = StoryboardArtistInput(
            scene_designer_output=scene_output,
            character_designer_output=char_output,
        )
        storyboard_output = await self.run_storyboard_artist(storyboard_input, project_id=project_id)
        # Animator
        anim_input = AnimatorInput(
            scene_designer_output=scene_output,
            character_designer_output=char_output,
            storyboard_artist_output=storyboard_output,
        )
        anim_output = await self.run_animator(anim_input, project_id=project_id)
        # Sound Director
        sound_input = SoundDirectorInput(
            scriptwriter_output=script_output,
            animator_output=anim_output,
        )
        sound_output = await self.run_sound_director(sound_input, project_id=project_id)
        # Director
        director_input = DirectorInput(
            scriptwriter_output=script_output,
            art_director_output=art_output,
            character_designer_output=char_output,
            scene_designer_output=scene_output,
            storyboard_artist_output=storyboard_output,
            animator_output=anim_output,
            sound_director_output=sound_output,
        )
        director_output = await self.run_director(director_input, project_id=project_id)

        result = {
            "scriptwriter": script_output.dict(),
            "art_director": art_output.dict(),
            "character_designer": char_output.dict(),
            "scene_designer": scene_output.dict(),
            "storyboard_artist": storyboard_output.dict(),
            "animator": anim_output.dict(),
            "sound_director": sound_output.dict(),
            "director": director_output.dict(),
        }
        if self.film_orchestrator is None:
            result["film_handoff"] = {
                "status": "not_configured",
                "detail": "No durable FilmOrchestrator was supplied for this crew run.",
            }
        elif not director_output.approved:
            result["film_handoff"] = {
                "status": "not_approved",
                "detail": "The Director requested revisions; no durable film was admitted.",
                "revisions": list(director_output.revisions),
            }
        else:
            # Import here to keep the older app service importable in deployments that
            # expose the crew only, and to make the explicit dependency injection above
            # the only way a creative run can admit render work.
            from film_pipeline.crew import admit_approved_crew_film
            result["film_handoff"] = await admit_approved_crew_film(
                self.film_orchestrator,
                result,
                target_seconds=duration,
                image_refs=image_refs,
                character_refs=character_refs,
            )
        return result

    async def retry_agent(self, execution_id: str, project_id: Optional[str] = None) -> Any:
        """Re-run a single failed stage using the typed input stored on the AgentExecution row."""
        project_id = project_id or "default"
        if not self.db_session:
            raise RuntimeError("Database session required for retry_agent")
        execution = self.db_session.query(AgentExecution).filter(AgentExecution.id == execution_id).first()
        if not execution:
            raise ValueError(f"AgentExecution not found: {execution_id}")
        if execution.status != "failed":
            raise ValueError(f"AgentExecution is not failed: {execution.status}")
        # Reconstruct input based on agent_type
        agent_type = execution.agent_type
        input_data = execution.input_data or {}
        # We need to map agent_type to the appropriate input model and call the corresponding method.
        # This is simplified; in a real app, we'd have a more robust mapping.
        if agent_type == "scriptwriter":
            input_obj = ScriptwriterInput(**input_data)
            return await self.run_scriptwriter(input_obj, project_id=project_id)
        elif agent_type == "art_director":
            # We need to get the scriptwriter_output from somewhere; for simplicity, we assume it's in input_data.
            # In a real app, we'd fetch the previous execution's output.
            # For now, we'll just pass the input_data and hope it contains the required field.
            input_obj = ArtDirectorInput(**input_data)
            return await self.run_art_director(input_obj, project_id=project_id)
        elif agent_type == "character_designer":
            input_obj = CharacterDesignerInput(**input_data)
            return await self.run_character_designer(input_obj, project_id=project_id)
        elif agent_type == "scene_designer":
            input_obj = SceneDesignerInput(**input_data)
            return await self.run_scene_designer(input_obj, project_id=project_id)
        elif agent_type == "storyboard_artist":
            input_obj = StoryboardArtistInput(**input_data)
            return await self.run_storyboard_artist(input_obj, project_id=project_id)
        elif agent_type == "animator":
            input_obj = AnimatorInput(**input_data)
            return await self.run_animator(input_obj, project_id=project_id)
        elif agent_type == "sound_director":
            input_obj = SoundDirectorInput(**input_data)
            return await self.run_sound_director(input_obj, project_id=project_id)
        elif agent_type == "director":
            input_obj = DirectorInput(**input_data)
            return await self.run_director(input_obj, project_id=project_id)
        else:
            raise ValueError(f"Unknown agent type: {agent_type}")
