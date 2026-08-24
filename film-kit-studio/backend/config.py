"""
Central configuration for Film Kit Studio backend.
Loads from environment variables / .env file.
"""

from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── NVIDIA NIM ──────────────────────────────────────────
    nim_api_key: str = ""
    nim_llm_model: str = "meta/llama-3.1-70b-instruct"
    nim_cosmos_model: str = "nvidia/cosmos-3-generator"
    nim_base_url: str = "https://integrate.api.nvidia.com/v1"
    nim_infer_url: str = "https://integrate.api.nvidia.com/v1/infer"
    nim_rpm: float = 40.0

    # ── Database ────────────────────────────────────────────
    database_url: str = "sqlite+aiosqlite:///./film_kit_studio.db"

    # ── Server ──────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8000
    frontend_url: str = "http://localhost:3000"

    # ── Storage ─────────────────────────────────────────────
    projects_dir: str = "./projects"

    # ── Pipeline defaults ───────────────────────────────────
    fps_default: int = 30
    max_retries: int = 3
    retry_delay: float = 4.0

    # ── Cinematography / trim defaults ────────────────────
    # Default trim (seconds) to trim from start/end of each generated clip
    clip_trim_seconds: float = 0.5
    # Default crossfade duration (seconds) for per-scene transitions
    default_transition_duration: float = 0.5
    # Default transition type per scene ("crossfade", "cut", "fade_to_black")
    default_transition_type: str = "crossfade"

    # ── Provider selection (free defaults if no key set) ────
    # script: "nim" (free default) | "openai" | "anthropic" | "gemini"
    script_provider: str = "nim"
    # visual: "cosmos" (free default) | "veo" | "kling"
    visual_provider: str = "cosmos"
    # voice:  "edge" (free default) | "elevenlabs"
    voice_provider: str = "edge"
    # music:  "ffmpeg" (free default) | "suno"
    music_provider: str = "ffmpeg"

    # ── OpenAI (script LLM tier) ────────────────────────────
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"

    # ── Anthropic Claude (script LLM tier) ──────────────────
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-5-20250929"

    # ── Gemini (script LLM tier; reuses gemini_api_key from Veo) ─
    gemini_model: str = "gemini-2.0-flash"

    # ── Google Veo 3.1 (Gemini API) ─────────────────────────
    gemini_api_key: str = ""
    veo_model: str = "veo-3.1"  # or "veo-3.1-lite" for cheaper preview

    # ── Kling 3.0 ───────────────────────────────────────────
    kling_api_key: str = ""
    kling_api_secret: str = ""
    kling_base_url: str = "https://api.klingai.com"

    # ── ElevenLabs (voice) ──────────────────────────────────
    elevenlabs_api_key: str = ""
    elevenlabs_model: str = "eleven_v3"

    # ── Suno (music, via gateway provider) ──────────────────
    suno_api_key: str = ""
    suno_base_url: str = "https://api.musicapi.ai"

    # ── Cinematography ──────────────────────────────────────
    # Global style prefix injected into every visual prompt to push
    # toward a consistent, cinematic look. Empty = rely on per-scene
    # prompts only.
    cinematography_style: str = (
        "cinematic, shot on anamorphic lenses, shallow depth of field, "
        "film grain, professional color grade, 24fps motion cadence"
    )

    # ── Director Agent (M1) ────────────────────────────────
    director_max_iterations: int = 3
    director_critic_provider: str = "gemini"      # gemini | openai
    director_planner_provider: str = "anthropic"  # anthropic | openai
    director_critic_threshold: float = 0.75
    director_beats_per_minute: float = 1.5
    director_target_duration: float = 60.0

    # ── ControlNet / LoRA / Training (M2) ────────────────────────
    controlnet_model_path: str = ""
    lora_storage_path: str = "./loras"
    # LoRA training
    kohya_ss_path: str = "./kohya-ss"
    base_model_path: str = "stabilityai/stable-diffusion-xl-base-1.0"

    # ── Lip-sync (M2) ──────────────────────────────────────
    liveportrait_model_path: str = ""

    # ── Audio Post (M3) ────────────────────────────────────
    demucs_model: str = "htdemucs"

    # ── Color / LUT (M3) ───────────────────────────────────
    lut_library_path: str = "./luts"
    colourlab_api_key: str = ""

    # ── DaVinci Resolve Scripting (M3) ─────────────────────
    resolve_script_path: str = ""

    # ── Aspect ratios ───────────────────────────────────────
    # Maps aspect string → (width, height). See the ASPECTS constant
    # below; used for both Cosmos generation and FFMPEG output.

    # ── Voices (edge-tts) ───────────────────────────────────
    # Friendly voice keys → full edge-tts voice names. See VOICES below.

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @property
    def projects_path(self) -> Path:
        p = Path(self.projects_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p


# ── Static constants (mirrors original film_kit.py) ─────────

ASPECTS: dict[str, tuple[int, int]] = {
    "16:9": (1920, 1080),
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
}

VOICES: dict[str, str] = {
    "aria": "en-US-AriaNeural",
    "guy": "en-US-GuyNeural",
    "jenny": "en-US-JennyNeural",
    "sonia": "en-GB-SoniaNeural",
    "ryan": "en-GB-RyanNeural",
    "natasha": "en-AU-NatashaNeural",
}

MUSIC_MOODS: list[str] = ["ambient", "tense", "bright"]

VISUAL_STYLES: list[str] = [
    "cinematic, warm lighting, detailed",
    "anime, vibrant colors, cel-shaded",
    "film noir, high contrast, black and white",
    "watercolor, soft pastels, painterly",
    "photorealistic, natural lighting, 8k",
    "cyberpunk, neon, futuristic, moody",
    "fantasy, ethereal, magical atmosphere",
    "documentary, realistic, handheld camera",
]

# The system prompt for the script/storyboard LLM.
#
# Upgraded from the original film_kit.py prompt: the model now emits a
# structured cinematography schema per scene (shot type, lens, lighting,
# camera move, color grade) in addition to narration + visual_prompt.
# This gives the visual-generation provider concrete, filmic direction
# instead of a bare description, which is the single biggest free lever
# for raising output quality.
SCRIPT_SYSTEM_PROMPT = """\
You are an expert film director and storyboard writer.
Given a story idea, break it into a numbered sequence of short, visually \
distinct scenes. Think cinematically — vary shot size, lens, and lighting \
across scenes to build rhythm and mood.

Respond with ONLY a JSON array — no prose, no markdown fences. Each element:
{"shot_type": "one of: establishing, wide, medium, close-up, extreme close-up, over-the-shoulder, POV",
 "lens": "a focal length / lens, e.g. 24mm, 35mm, 50mm, 85mm, anamorphic",
 "lighting": "concrete lighting, e.g. golden hour, volumetric god rays, chiaroscuro, neon practicals, soft window light",
 "camera_move": "one of: locked-off, slow push-in, slow pull-out, dolly left/right, handheld, crane up, orbit",
 "color_grade": "a grade, e.g. teal-and-orange, bleach bypass, desaturated cool, warm filmic",
 "narration": "1–2 sentence voiceover line for this scene, under 25 words",
 "visual_prompt": "a vivid, concrete cinematic description of exactly what is on screen — compose the shot, subject, setting, and atmosphere into one fluent image/video prompt"}
Keep narration lines short (under 25 words) since each is read aloud over one shot.\
"""

settings = Settings()
