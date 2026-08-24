#!/usr/bin/env python3
"""
Film Kit v2.0 — Free-Tier AI Filmmaking Pipeline
──────────────────────────────────────────────────
idea → script → storyboard images → narration → Ken-Burns clips → stitched film

Free-tier services (bring your own free key where noted):
  • NVIDIA NIM          (https://build.nvidia.com)  — free LLM for script/storyboard
  • Pollinations.ai     (https://pollinations.ai)    — free, keyless text-to-image
  • Microsoft Edge TTS  (via edge-tts package)       — free, keyless narration
  • ffmpeg              (local, open-source)          — Ken Burns + stitching

Install:
    pip install openai edge-tts
    # + ffmpeg available on PATH (ffmpeg.org)

First run prompts for a free NVIDIA NIM API key (build.nvidia.com → API Keys).
Everything else is keyless.

Non-interactive batch mode:
    python film_kit.py --idea "a lighthouse keeper meets a sea dragon" \
        --scenes 8 --mode crossfade --music --project lighthouse
"""

import argparse
import asyncio
import json
import os
import random
import re
import shutil
import subprocess
import sys
import textwrap
import time
import urllib.parse
import urllib.request
from collections import deque
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

try:
    import edge_tts
    HAS_EDGE_TTS = True
except ImportError:
    HAS_EDGE_TTS = False


# ─────────────────────────────────────────────────────────────
# TERMINAL DETECTION
# ─────────────────────────────────────────────────────────────
def _supports_color() -> bool:
    if not hasattr(sys.stdout, "isatty") or not sys.stdout.isatty():
        return False
    if sys.platform == "win32":
        try:
            import ctypes
            kernel = ctypes.windll.kernel32
            kernel.SetConsoleMode(kernel.GetStdHandle(-11), 7)
            return True
        except Exception:
            return False
    return True

USE_COLOR = _supports_color()


# ─────────────────────────────────────────────────────────────
# ANSI COLOR SYSTEM  (modern agent-style palette)
# Inspired by: Claude Code / OpenCode / Hermes — clean slate
# blacks, whites, a single vivid accent (cyan-mint #00D4AA),
# dim grays for scaffolding, warm amber for warnings.
# ─────────────────────────────────────────────────────────────
def _c(code: str) -> str:
    return code if USE_COLOR else ""

class C:
    # resets
    R     = _c("\033[0m")
    BOLD  = _c("\033[1m")
    DIM   = _c("\033[2m")
    ITAL  = _c("\033[3m")
    UL    = _c("\033[4m")

    # palette — 256-color for precise "agent" look
    # accent: cyan-mint  (matches Claude Code sidebar active)
    ACCENT  = _c("\033[38;5;43m")   # #00AF87 — strong teal-mint
    ACCENTB = _c("\033[38;5;49m")   # #00FF87 — bright mint (headings)
    # neutrals
    WHITE   = _c("\033[38;5;255m")  # near-white
    GRAY    = _c("\033[38;5;245m")  # mid gray
    DIMGRAY = _c("\033[38;5;238m")  # dim border gray
    SILVER  = _c("\033[38;5;251m")  # light text
    # status
    GREEN   = _c("\033[38;5;78m")   # success
    RED     = _c("\033[38;5;203m")  # error
    AMBER   = _c("\033[38;5;214m")  # warning
    BLUE    = _c("\033[38;5;75m")   # info
    PURPLE  = _c("\033[38;5;141m")  # scene index labels
    PINK    = _c("\033[38;5;213m")  # prompt arrow


# ─────────────────────────────────────────────────────────────
# BOX-DRAWING  (same half-width chars used by OpenCode/Hermes)
# ─────────────────────────────────────────────────────────────
H  = "─"; V  = "│"
TL = "╭"; TR = "╮"; BL = "╰"; BR = "╯"
ML = "├"; MR = "┤"; MT = "┬"; MB = "┴"
DOT = "·"; BULLET = "◆"; ARROW = "❯"
TICK = "✓"; CROSS = "✗"; WARN_SYM = "▲"; INFO_SYM = "◆"
SPINNER_FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")


# ─────────────────────────────────────────────────────────────
# STATUS PRINTERS
# ─────────────────────────────────────────────────────────────
def ok(msg: str):
    print(f"  {C.GREEN}{TICK}{C.R}  {C.WHITE}{msg}{C.R}")

def err(msg: str):
    print(f"  {C.RED}{CROSS}{C.R}  {C.RED}{msg}{C.R}")

def warn(msg: str):
    print(f"  {C.AMBER}{WARN_SYM}{C.R}  {C.AMBER}{msg}{C.R}")

def info(msg: str):
    print(f"  {C.BLUE}{INFO_SYM}{C.R}  {C.GRAY}{msg}{C.R}")

def dim(msg: str):
    print(f"  {C.DIMGRAY}{DOT}{C.R}  {C.DIMGRAY}{msg}{C.R}")


def _pad(text: str, width: int) -> str:
    """Pad text to fixed display width, stripping ANSI escapes for measurement."""
    raw = re.sub(r"\033\[[^m]*m", "", text)
    pad = max(0, width - len(raw))
    return text + " " * pad


def banner():
    """Top-of-session banner — matches the compact style of Claude Code / OpenCode."""
    w = 62
    inner = w - 2
    title = f"{C.BOLD}{C.ACCENTB}Film Kit{C.R}{C.BOLD}{C.WHITE}  v2.0{C.R}"
    sub   = f"{C.DIMGRAY}idea → script → images → narration → Ken Burns → film{C.R}"

    print()
    print(f"  {C.DIMGRAY}{TL}{H * inner}{TR}{C.R}")
    print(f"  {C.DIMGRAY}{V}{C.R}  {_pad(title, inner - 2)}{C.DIMGRAY}{V}{C.R}")
    print(f"  {C.DIMGRAY}{V}{C.R}  {_pad(sub, inner - 2)}{C.DIMGRAY}{V}{C.R}")
    print(f"  {C.DIMGRAY}{BL}{H * inner}{BR}{C.R}")
    print()


def section(label: str):
    """Section header — tight rule style used by Hermes/OpenCode."""
    w = 58
    line = f"{H * 2} {label} "
    rest = H * max(0, w - len(line))
    print(f"\n  {C.ACCENT}{line}{C.DIMGRAY}{rest}{C.R}")


def kv_row(key: str, val: str, key_w: int = 9):
    """Key-value line with aligned columns."""
    k = f"{C.DIMGRAY}{key:<{key_w}}{C.R}"
    v = f"{C.SILVER}{val}{C.R}"
    print(f"    {k}  {v}")


# ─────────────────────────────────────────────────────────────
# INLINE SPINNER  (non-blocking — used before blocking calls)
# ─────────────────────────────────────────────────────────────
class Spinner:
    def __init__(self, msg: str):
        self.msg = msg
        self._frame = 0
        self._active = False

    def start(self):
        if not USE_COLOR:
            print(f"  {self.msg}…")
            return
        self._active = True
        self._draw()

    def _draw(self):
        frame = SPINNER_FRAMES[self._frame % len(SPINNER_FRAMES)]
        sys.stdout.write(f"\r  {C.ACCENT}{frame}{C.R}  {C.GRAY}{self.msg}{C.R}   ")
        sys.stdout.flush()
        self._frame += 1

    def tick(self):
        if self._active:
            self._draw()

    def stop(self, success: bool = True, msg: str = ""):
        if not self._active:
            return
        self._active = False
        sym  = f"{C.GREEN}{TICK}" if success else f"{C.RED}{CROSS}"
        line = msg or self.msg
        sys.stdout.write(f"\r  {sym}{C.R}  {C.WHITE}{line}{C.R}   \n")
        sys.stdout.flush()


# ─────────────────────────────────────────────────────────────
# PATHS / CONFIG
# ─────────────────────────────────────────────────────────────
CONFIG_FILE   = Path.home() / ".film_kit_config.json"
PROJECTS_DIR  = Path.home() / "film_kit_projects"
NIM_BASE      = "https://integrate.api.nvidia.com/v1"
OPENROUTER_BASE = "https://openrouter.ai/api/v1"
DEFAULT_NIM_MODEL = "meta/llama-3.1-70b-instruct"

OPENROUTER_FREE_MODELS: List[Tuple[str, str]] = [
    ("OpenRouter Llama-3.1-8B free", "meta-llama/llama-3.1-8b-instruct:free"),
    ("OpenRouter Gemma-2-9B free",   "google/gemma-2-9b-it:free"),
]

ASPECTS: Dict[str, Tuple[int, int]] = {
    "16:9": (1920, 1080),
    "9:16": (1080, 1920),
    "1:1":  (1080, 1080),
}

VOICES: Dict[str, str] = {
    "aria":   "en-US-AriaNeural",
    "guy":    "en-US-GuyNeural",
    "jenny":  "en-US-JennyNeural",
    "sonia":  "en-GB-SoniaNeural",
    "ryan":   "en-GB-RyanNeural",
    "natasha":"en-AU-NatashaNeural",
}

MUSIC_MOODS = ["ambient", "tense", "bright"]

FPS_DEFAULT = 30


def load_config() -> Dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

def save_config(cfg: Dict):
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

def ensure_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None

def run_cmd(cmd: List[str], quiet: bool = True) -> subprocess.CompletedProcess:
    """Run a subprocess; capture output by default."""
    return subprocess.run(cmd, capture_output=quiet, text=True)


# ─────────────────────────────────────────────────────────────
# TOKEN BUCKET  (lightweight RPM guard)
# ─────────────────────────────────────────────────────────────
class TokenBucket:
    """Minimal adaptive RPM guard — targets 80% of the ceiling,
    backs off hard on 429."""
    def __init__(self, rpm: float = 20.0, min_gap: float = 2.0):
        self.rpm     = max(1.0, rpm) * 0.8
        self.min_gap = min_gap
        self.last_call = 0.0

    def wait(self):
        gap     = max(self.min_gap, 60.0 / self.rpm)
        elapsed = time.monotonic() - self.last_call
        if elapsed < gap:
            time.sleep(gap - elapsed)
        self.last_call = time.monotonic()

    def penalize(self):
        self.rpm = max(2.0, self.rpm * 0.5)


class TokenMeter:
    """Rolling 60-second TPM observer."""
    def __init__(self):
        self._window: deque = deque()   # (monotonic_ts, tokens)
        self.total_prompt     = 0
        self.total_completion = 0

    def _prune(self):
        now = time.monotonic()
        while self._window and self._window[0][0] < now - 60.0:
            self._window.popleft()

    def record(self, prompt_tokens: int, completion_tokens: int):
        now = time.monotonic()
        self._window.append((now, max(0, prompt_tokens) + max(0, completion_tokens)))
        self.total_prompt     += max(0, prompt_tokens)
        self.total_completion += max(0, completion_tokens)
        self._prune()

    def tpm(self) -> int:
        self._prune()
        return sum(t for _, t in self._window)

    def stats(self) -> str:
        return (f"{self.tpm()} TPM  ·  lifetime "
                f"{self.total_prompt} in / {self.total_completion} out")


TOKEN_METER = TokenMeter()


def _estimate_tokens(text: Optional[str]) -> int:
    """~4 chars/token estimate for pacing visibility."""
    if not text:
        return 0
    return max(1, len(text) // 4)


# ─────────────────────────────────────────────────────────────
# PROVIDER POOL
# ─────────────────────────────────────────────────────────────
class Provider:
    def __init__(self, name: str, base_url: str, api_key: str,
                 model_id: str, rpm: float = 20.0):
        self.name     = name
        self.base_url = base_url
        self.model_id = model_id
        self.bucket   = TokenBucket(rpm=rpm)
        self.client: Optional[OpenAI] = (
            OpenAI(base_url=base_url, api_key=api_key, timeout=120)
            if HAS_OPENAI else None
        )
        self.cooldown_until = 0.0

    def is_available(self) -> bool:
        return time.monotonic() >= self.cooldown_until

    def cooldown(self, secs: float = 90.0):
        self.cooldown_until = time.monotonic() + secs


class ProviderPool:
    def __init__(self, providers: List[Provider]):
        if not providers:
            raise ValueError("Need at least one LLM provider (set a NIM API key).")
        self.providers = providers

    def _next_available(self) -> Optional[Provider]:
        for p in self.providers:
            if p.is_available():
                return p
        return None

    def chat(self, messages: List[Dict], temperature: float = 0.8,
             max_tokens: int = 2000) -> str:
        last_exc: Optional[Exception] = None
        for _ in range(len(self.providers) * 2):
            p = self._next_available()
            if p is None:
                time.sleep(5)
                continue
            if p.client is None:
                raise RuntimeError("OpenAI client not initialised — install the 'openai' package.")
            p.bucket.wait()
            try:
                resp = p.client.chat.completions.create(
                    model=p.model_id,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                content = resp.choices[0].message.content or ""
                usage   = getattr(resp, "usage", None)
                if usage:
                    TOKEN_METER.record(usage.prompt_tokens, usage.completion_tokens)
                else:
                    prompt_est = sum(_estimate_tokens(m.get("content")) for m in messages)
                    TOKEN_METER.record(prompt_est, _estimate_tokens(content))
                return content
            except Exception as exc:
                last_exc = exc
                msg = str(exc).lower()
                if "429" in msg or "rate" in msg:
                    warn(f"{p.name}: rate-limited — backing off 90 s")
                    p.bucket.penalize()
                    p.cooldown(90.0)
                elif "401" in msg or "403" in msg or "unauthorized" in msg:
                    err(f"{p.name}: authentication error — check your API key")
                    p.cooldown(300.0)   # BUG FIX: don't hammer auth-failed providers
                else:
                    p.cooldown(20.0)
        raise RuntimeError(f"All LLM providers failed. Last error: {last_exc}")


def build_provider_pool(cfg: Dict) -> ProviderPool:
    if not HAS_OPENAI:
        raise RuntimeError("Install the 'openai' package: pip install openai")
    if not cfg.get("nim_key"):
        raise RuntimeError("No NIM API key configured.")
    providers: List[Provider] = [
        Provider(
            name="NVIDIA NIM",
            base_url=NIM_BASE,
            api_key=cfg["nim_key"],
            model_id=cfg.get("model", DEFAULT_NIM_MODEL),
            rpm=float(cfg.get("rpm", 20.0)),
        )
    ]
    or_key = os.environ.get("OPENROUTER_API_KEY", "")
    if or_key:
        for name, model_id in OPENROUTER_FREE_MODELS:
            providers.append(Provider(name, OPENROUTER_BASE, or_key, model_id, rpm=18.0))
    return ProviderPool(providers)


# ─────────────────────────────────────────────────────────────
# SCENE / PROJECT MODEL
# ─────────────────────────────────────────────────────────────
@dataclass
class Scene:
    index:         int
    narration:     str
    visual_prompt: str
    image_path:    Optional[str]  = None
    audio_path:    Optional[str]  = None
    clip_path:     Optional[str]  = None
    duration:      Optional[float] = None

    # BUG FIX: asdict() serialises correctly because all fields have
    # defaults; old code would crash if 'duration' was missing in saved JSON
    # because Scene(**s) would receive an unexpected kwarg type from older
    # manifests that stored None as JSON null. Handled by _from_dict below.

    @classmethod
    def from_dict(cls, d: Dict) -> "Scene":
        """Safe deserialisation — ignores unknown keys, coerces types."""
        return cls(
            index         = int(d.get("index", 0)),
            narration     = str(d.get("narration", "")),
            visual_prompt = str(d.get("visual_prompt", "")),
            image_path    = d.get("image_path") or None,
            audio_path    = d.get("audio_path") or None,
            clip_path     = d.get("clip_path") or None,
            duration      = float(d["duration"]) if d.get("duration") is not None else None,
        )


class Project:
    def __init__(self, name: str):
        # BUG FIX: sanitise project names — reject names with path separators
        # to prevent directory traversal when building self.dir
        if "/" in name or "\\" in name or not name.strip():
            raise ValueError(f"Invalid project name: {name!r}")
        self.name = name.strip()
        self.dir  = PROJECTS_DIR / self.name
        for sub in ("images", "audio", "clips", "output"):
            (self.dir / sub).mkdir(parents=True, exist_ok=True)

        # defaults
        self.idea:       str   = ""
        self.style:      str   = "cinematic, warm lighting, detailed"
        self.aspect:     str   = "16:9"
        self.voice:      str   = "aria"
        self.seed:       int   = random.randint(0, 999_999)
        self.music:      bool  = False
        self.music_mood: str   = "ambient"
        self.scenes:     List[Scene] = []
        self.manifest_path = self.dir / "manifest.json"
        self.load()

    def save(self):
        data = {
            "idea":       self.idea,
            "style":      self.style,
            "aspect":     self.aspect,
            "voice":      self.voice,
            "seed":       self.seed,
            "music":      self.music,
            "music_mood": self.music_mood,
            "scenes":     [asdict(s) for s in self.scenes],
        }
        self.manifest_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def load(self):
        if not self.manifest_path.exists():
            return
        try:
            data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            self.idea       = data.get("idea", self.idea)
            self.style      = data.get("style", self.style)
            self.aspect     = data.get("aspect", self.aspect)
            self.voice      = data.get("voice", self.voice)
            self.seed       = int(data.get("seed", self.seed))
            self.music      = bool(data.get("music", self.music))
            self.music_mood = data.get("music_mood", self.music_mood)
            # BUG FIX: use safe Scene.from_dict instead of Scene(**s) which
            # would raise TypeError if stored JSON has unknown/missing fields
            self.scenes     = [Scene.from_dict(s) for s in data.get("scenes", [])]
        except json.JSONDecodeError as exc:
            warn(f"Manifest parse error ({exc}) — starting fresh.")
        except Exception as exc:
            warn(f"Could not load manifest: {exc}")

    def output_path(self) -> Path:
        return self.dir / "output" / f"{self.name}.mp4"

    def srt_path(self) -> Path:
        return self.dir / "output" / f"{self.name}.srt"


# ─────────────────────────────────────────────────────────────
# 1) SCRIPT / STORYBOARD  (NIM LLM)
# ─────────────────────────────────────────────────────────────
_SCRIPT_SYSTEM = """\
You are a concise film storyboard writer.
Given a story idea, break it into a numbered sequence of short scenes.
Respond with ONLY a JSON array — no prose, no markdown fences. Each element:
{"narration": "1–2 sentence voiceover line for this scene",
 "visual_prompt": "a vivid, concrete text-to-image prompt describing exactly what is on screen"}
Keep narration lines short (under 25 words) since each is read aloud over one shot.\
"""

# BUG FIX: the old regex r"\[.*\]" with re.DOTALL is too greedy —
# it will match from the first [ to the very last ] in the response,
# breaking if the model emits commentary after the JSON array.
# Use a non-greedy variant and validate the parse result.
_ARRAY_RE = re.compile(r"\[.*?\]|\[.*\]", re.DOTALL)


def _extract_json_array(text: str) -> List[Dict]:
    """Extract the first valid JSON array from an LLM response string.

    The model may wrap output in markdown fences or add preamble/postamble.
    Strategy: strip fences, try full text, then fall back to regex extraction.
    """
    # Strip markdown code fences
    stripped = re.sub(r"```(?:json)?\s*", "", text).strip()

    # Try parsing the whole cleaned string first
    if stripped.startswith("["):
        try:
            result = json.loads(stripped)
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

    # Find the outermost [...] block (handles preamble/postamble)
    # Walk char-by-char to find balanced brackets — robust against
    # nested objects inside the array.
    start = stripped.find("[")
    if start == -1:
        raise ValueError("No JSON array found in model response.")
    depth = 0
    for i, ch in enumerate(stripped[start:], start):
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                try:
                    result = json.loads(stripped[start : i + 1])
                    if isinstance(result, list):
                        return result
                except json.JSONDecodeError as exc:
                    raise ValueError(f"JSON parse error in model response: {exc}") from exc
    raise ValueError("Unbalanced brackets in model response.")


def generate_script(pool: ProviderPool, idea: str,
                    num_scenes: int, style: str) -> List[Scene]:
    user_prompt = (
        f"Story idea: {idea}\n"
        f"Visual style to weave into every visual_prompt: {style}\n"
        f"Produce exactly {num_scenes} scenes."
    )
    raw = pool.chat(
        [{"role": "system", "content": _SCRIPT_SYSTEM},
         {"role": "user",   "content": user_prompt}],
        temperature=0.85,
        max_tokens=2000,
    )
    items = _extract_json_array(raw)

    # BUG FIX: validate that each item has the required keys before
    # constructing a Scene — old code would raise a confusing KeyError
    scenes: List[Scene] = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            warn(f"Scene {i}: unexpected item type {type(item).__name__}, skipping")
            continue
        narration     = str(item.get("narration", "")).strip()
        visual_prompt = str(item.get("visual_prompt", "")).strip()
        if not narration or not visual_prompt:
            warn(f"Scene {i}: missing narration or visual_prompt, skipping")
            continue
        scenes.append(Scene(
            index         = len(scenes),        # re-index after skips
            narration     = narration,
            visual_prompt = f"{visual_prompt}, {style}",
        ))
    if not scenes:
        raise ValueError("Model returned no usable scenes.")
    return scenes


# ─────────────────────────────────────────────────────────────
# 2) IMAGES  (Pollinations.ai — free, keyless)
# ─────────────────────────────────────────────────────────────
_POLLINATIONS_MAX_RETRIES = 3
_POLLINATIONS_RETRY_DELAY = 4.0  # seconds


def generate_image(prompt: str, out_path: Path,
                   width: int, height: int,
                   seed: Optional[int] = None):
    """Download one image from Pollinations.ai with retry on transient errors.

    BUG FIX: old code had no retry logic — a single transient HTTP error
    would silently fail and leave image_path as None, causing downstream
    steps to skip the scene with no actionable message.
    """
    seed = seed if seed is not None else random.randint(0, 999_999)
    # BUG FIX: urllib.parse.quote with safe='' percent-encodes commas and
    # other characters that can break Pollinations URL routing.
    q   = urllib.parse.quote(prompt, safe="")
    url = (
        f"[https://image.pollinations.ai/prompt/](https://image.pollinations.ai/prompt/){q}"
        f"?width={width}&height={height}&nologo=true&seed={seed}"
    )
    last_exc: Optional[Exception] = None
    for attempt in range(_POLLINATIONS_MAX_RETRIES):
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "film-kit/2.0"}
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = resp.read()
            # BUG FIX: verify we actually received image data before writing;
            # Pollinations sometimes returns a short HTML error page on overload.
            if len(data) < 1024:
                raise IOError(
                    f"Response too small ({len(data)} bytes) — likely an error page."
                )
            out_path.write_bytes(data)
            return
        except Exception as exc:
            last_exc = exc
            if attempt < _POLLINATIONS_MAX_RETRIES - 1:
                time.sleep(_POLLINATIONS_RETRY_DELAY * (attempt + 1))
    raise IOError(f"Pollinations download failed after {_POLLINATIONS_MAX_RETRIES} attempts: {last_exc}")


# ─────────────────────────────────────────────────────────────
# 3) NARRATION  (edge-tts — free, keyless)
# ─────────────────────────────────────────────────────────────
async def _synthesize(text: str, voice: str, out_path: Path):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(out_path))


def synthesize_narration(text: str, voice_key: str, out_path: Path):
    if not HAS_EDGE_TTS:
        raise RuntimeError("Install narration support: pip install edge-tts")
    voice = VOICES.get(voice_key, voice_key)
    # BUG FIX: asyncio.run() raises RuntimeError if called inside an
    # already-running event loop (e.g. when film_kit is imported from
    # a Jupyter notebook or an async framework). Use the loop directly
    # when one is already running, otherwise create a fresh one.
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, _synthesize(text, voice, out_path))
            future.result()
    else:
        asyncio.run(_synthesize(text, voice, out_path))


# ─────────────────────────────────────────────────────────────
# 4) KEN BURNS CLIPS + STITCHING  (ffmpeg)
# ─────────────────────────────────────────────────────────────
def probe_duration(path: Path) -> float:
    """Return the duration of a media file in seconds (min 0.5 s)."""
    # BUG FIX: ffprobe can return an empty string or "N/A" for duration;
    # the old code's float() cast would raise ValueError in both cases.
    p = run_cmd([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ])
    try:
        val = p.stdout.strip()
        if not val or val == "N/A":
            return 4.0
        return max(0.5, float(val))
    except (ValueError, AttributeError):
        return 4.0


def build_ken_burns_clip(image_path: Path, duration: float,
                          out_path: Path, size: Tuple[int, int],
                          fps: int = FPS_DEFAULT, zoom_in: bool = True):
    """Render an animated Ken Burns pan/zoom clip from a single image.

    BUG FIX: the zoompan filter requires d (frame count) to be a positive
    integer string.  Old code passed int(duration * fps) directly but didn't
    guard against duration values below 1/fps, which could produce d=0 and
    cause ffmpeg to hang or output a zero-length file.
    """
    w, h   = size
    frames = max(2, int(round(duration * fps)))  # ← was max(1, …); 1 frame = no motion
    z_expr = (
        "min(zoom+0.0015,1.4)"
        if zoom_in else
        "if(eq(on,1),1.4,max(zoom-0.0015,1.0))"
    )
    # scale to 3× so zoompan has room to pan without hitting black borders
    scale_w = w * 3
    vf = (
        f"scale={scale_w}:-2,"      # ← -2 not -1: keeps height even (yuv420p requirement)
        f"zoompan=z='{z_expr}':d={frames}:s={w}x{h}:fps={fps},"
        f"format=yuv420p"
    )
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(image_path),
        "-vf", vf,
        "-t", f"{duration:.3f}",
        "-pix_fmt", "yuv420p",
        str(out_path),
    ]
    result = run_cmd(cmd)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg (ken burns) failed for {image_path.name}:\n"
            f"{result.stderr[-1000:]}"
        )


def mux_audio(video_path: Path, audio_path: Path, out_path: Path):
    """Mux video + audio into a single MP4.

    BUG FIX: added -async 1 to handle minor A/V sync drift that can
    accumulate when edge-tts produces audio slightly shorter than the
    video (which uses the probe_duration + 0.4 s pad).
    """
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-async", "1",          # ← new: fixes occasional A/V desync
        "-shortest",
        str(out_path),
    ]
    result = run_cmd(cmd)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg (mux) failed:\n{result.stderr[-800:]}")


def stitch_concat(clip_paths: List[Path], out_path: Path):
    """Stitch clips with hard cuts (fast, no re-encode).

    BUG FIX: the concat demuxer requires the list file to use forward-slash
    paths even on Windows.  Also added -c:a copy so audio isn't silently
    dropped when all clips already have AAC audio.
    """
    list_file = out_path.parent / "_concat_list.txt"
    # Use as_posix() for cross-platform safety
    lines = [f"file '{p.resolve().as_posix()}'" for p in clip_paths]
    list_file.write_text("\n".join(lines), encoding="utf-8")
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(list_file),
        "-c", "copy",
        str(out_path),
    ]
    result = run_cmd(cmd)
    list_file.unlink(missing_ok=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg (concat) failed:\n{result.stderr[-800:]}")


def stitch_crossfade(clip_paths: List[Path], out_path: Path,
                     trans_dur: float = 0.75):
    """Stitch clips with dissolve transitions (xfade/acrossfade chain).

    BUG FIX (critical): the old filter_complex was wrong for n > 2 clips.
    xfade labels output as [v1], [v2] … but the *next* xfade must reference
    the *previous output label*, not the raw stream index [i:v].
    The corrected version below properly chains intermediate labels.

    BUG FIX: acrossfade duration must be ≤ min(dur_a, dur_b).  The old
    code used min(trans_dur, dur_i-1 - 0.1, dur_i - 0.1) which is correct,
    but the final clamp to max(0.2, …) could still exceed either clip's
    length if a clip is shorter than 0.3 s (shouldn't happen in practice,
    but now guarded).
    """
    if len(clip_paths) == 1:
        shutil.copy2(clip_paths[0], out_path)
        return

    durations = [probe_duration(p) for p in clip_paths]
    inputs: List[str] = []
    for p in clip_paths:
        inputs += ["-i", str(p)]

    parts: List[str] = []
    prev_v = "0:v"
    prev_a = "0:a"
    cum    = durations[0]

    for i in range(1, len(clip_paths)):
        td = min(
            trans_dur,
            durations[i - 1] - 0.05,   # leave 50 ms of source before fade
            durations[i]     - 0.05,
        )
        td = max(0.1, td)               # absolute floor
        offset = max(0.0, cum - td)

        out_v = f"xv{i}"
        out_a = f"xa{i}"
        parts.append(
            f"[{prev_v}][{i}:v]xfade=transition=fade"
            f":duration={td:.3f}:offset={offset:.3f}[{out_v}]"
        )
        parts.append(
            f"[{prev_a}][{i}:a]acrossfade=d={td:.3f}[{out_a}]"
        )
        prev_v = out_v
        prev_a = out_a
        cum   += durations[i] - td

    filter_complex = ";".join(parts)
    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", f"[{prev_v}]",
        "-map", f"[{prev_a}]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-c:a", "aac", "-b:a", "192k",
        str(out_path),
    ]
    result = run_cmd(cmd)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg (crossfade) failed:\n{result.stderr[-1200:]}")


def write_srt(scenes: List[Scene], out_path: Path):
    """Write an SRT subtitle file aligned to each scene's duration."""
    def fmt(sec: float) -> str:
        h_, rem = divmod(sec, 3600)
        m_, s_  = divmod(rem, 60)
        # BUG FIX: SRT uses comma as decimal separator, not period.
        # Old code used str.replace(".", ",") which is correct, but the
        # f-string produced "HH:MM:SS.mmm" and replace gave "HH:MM:SS,mmm"
        # — milliseconds were fine. Keeping the same approach for clarity.
        ms = int(round((s_ % 1) * 1000))
        return f"{int(h_):02}:{int(m_):02}:{int(s_):02},{ms:03}"

    lines: List[str] = []
    t = 0.0
    for i, s in enumerate(scenes, 1):
        dur = s.duration or 4.0
        end = t + dur
        lines += [str(i), f"{fmt(t)} --> {fmt(end)}", s.narration, ""]
        t = end

    out_path.write_text("\n".join(lines), encoding="utf-8")


# ─────────────────────────────────────────────────────────────
# AMBIENT MUSIC BED  (local ffmpeg synthesis — no external API)
# ─────────────────────────────────────────────────────────────
_MUSIC_PARAMS: Dict[str, Tuple[int, int]] = {
    "ambient": (110, 165),
    "tense":   (98,  104),
    "bright":  (220, 330),
}


def generate_ambient_bed(duration: float, out_path: Path, mood: str = "ambient"):
    """Synthesise a quiet stereo drone pad with ffmpeg signal generators.

    Two detuned sine drones + filtered pink noise, faded in/out.
    No external music API — avoids licensing and reliability issues.

    BUG FIX: the afade out start-time must be computed as
    max(0, duration - fade_dur) — the old code had an off-by-one where
    duration values < 2 could produce a negative start time, causing
    ffmpeg to emit a warning and potentially corrupt the output.
    """
    f1, f2     = _MUSIC_PARAMS.get(mood, _MUSIC_PARAMS["ambient"])
    fade_dur   = min(2.0, duration * 0.1)    # proportional fade for short films
    fade_out_t = max(0.0, duration - fade_dur)
    dur_s      = f"{duration:.3f}"

    filt = (
        f"sine=frequency={f1}:duration={dur_s}[a];"
        f"sine=frequency={f2}:duration={dur_s}[b];"
        f"anoisesrc=color=pink:duration={dur_s}:amplitude=0.05[n];"
        f"[a][b]amix=inputs=2:weights='1 0.6'[ab];"    # ← BUG FIX: quote weights
        f"[ab][n]amix=inputs=2:weights='1 0.3',"
        f"lowpass=f=600,"
        f"afade=t=in:d={fade_dur:.3f},"
        f"afade=t=out:st={fade_out_t:.3f}:d={fade_dur:.3f},"
        f"volume=0.18[out]"
    )
    cmd = [
        "ffmpeg", "-y",
        "-filter_complex", filt,
        "-map", "[out]",
        "-t", dur_s,
        str(out_path),
    ]
    result = run_cmd(cmd)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg (ambient bed) failed:\n{result.stderr[-800:]}")


def mix_music_under(video_path: Path, out_path: Path, mood: str = "ambient"):
    """Mix a synthesised ambient bed under the existing audio track."""
    duration = probe_duration(video_path)
    bed      = video_path.parent / "_music_bed.aac"
    try:
        generate_ambient_bed(duration, bed, mood)
        # BUG FIX: amix weights parameter must be quoted in newer ffmpeg versions
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-i", str(bed),
            "-filter_complex",
            "[0:a][1:a]amix=inputs=2:duration=first:weights='1 1'[a]",
            "-map", "0:v",
            "-map", "[a]",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            str(out_path),
        ]
        result = run_cmd(cmd)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg (music mix) failed:\n{result.stderr[-800:]}")
    finally:
        bed.unlink(missing_ok=True)   # BUG FIX: always clean up temp file


# ─────────────────────────────────────────────────────────────
# PIPELINE STEPS
# ─────────────────────────────────────────────────────────────
def step_script(proj: Project, pool: ProviderPool, num_scenes: int):
    section("Writing script")
    if not proj.idea:
        err("No idea set — use /idea <your story idea> first.")
        return
    sp = Spinner(f"Asking the LLM for {num_scenes} scenes…")
    sp.start()
    try:
        proj.scenes = generate_script(pool, proj.idea, num_scenes, proj.style)
        proj.save()
        sp.stop(success=True, msg=f"Got {len(proj.scenes)} scenes")
        info(f"Tokens: {TOKEN_METER.stats()}")
        print()
        for s in proj.scenes:
            idx  = f"{C.PURPLE}[{s.index:02}]{C.R}"
            text = f"{C.WHITE}{s.narration}{C.R}"
            print(f"    {idx}  {text}")
    except Exception as exc:
        sp.stop(success=False, msg=str(exc))
        err(str(exc))


def step_images(proj: Project):
    section("Generating storyboard images  (Pollinations.ai)")
    if not proj.scenes:
        err("No scenes yet — run /script first.")
        return
    w, h = ASPECTS[proj.aspect]
    # Use half resolution for generation (faster, still HD for Ken Burns)
    gen_w, gen_h = w // 2, h // 2
    info(
        f"Fixed seed {proj.seed} — consistent palette across all scenes. "
        f"Note: Pollinations has no image-reference support; recurring "
        f"characters may drift — name them explicitly in /style."
    )
    print()
    for s in proj.scenes:
        out = proj.dir / "images" / f"scene_{s.index:02}.jpg"
        sp  = Spinner(f"Scene {s.index:02}  {C.DIMGRAY}{s.visual_prompt[:55]}…{C.R}")
        sp.start()
        try:
            generate_image(s.visual_prompt, out, gen_w, gen_h, seed=proj.seed)
            s.image_path = str(out)
            sp.stop(success=True, msg=f"scene {s.index:02} → {out.name}")
        except Exception as exc:
            sp.stop(success=False, msg=f"scene {s.index:02} failed")
            err(str(exc))
    proj.save()


def step_voice(proj: Project, voice_key: str):
    section(f"Synthesising narration  (edge-tts · {voice_key})")
    if not proj.scenes:
        err("No scenes yet — run /script first.")
        return
    if voice_key not in VOICES and voice_key not in VOICES.values():
        err(f"Unknown voice {voice_key!r}. Use /voices to list options.")
        return
    proj.voice = voice_key
    print()
    for s in proj.scenes:
        out = proj.dir / "audio" / f"scene_{s.index:02}.mp3"
        sp  = Spinner(f'Scene {s.index:02}  "{s.narration[:50]}…"')
        sp.start()
        try:
            synthesize_narration(s.narration, voice_key, out)
            dur          = probe_duration(out)
            s.audio_path = str(out)
            s.duration   = dur + 0.4   # small pad so Ken Burns isn't cut short
            sp.stop(success=True, msg=f"scene {s.index:02} → {s.duration:.1f} s")
        except Exception as exc:
            sp.stop(success=False, msg=f"scene {s.index:02} failed")
            err(str(exc))
    proj.save()


def step_clips(proj: Project):
    section("Rendering Ken Burns clips  (ffmpeg)")
    if not ensure_ffmpeg():
        err("ffmpeg/ffprobe not found — install ffmpeg and add it to PATH.")
        return
    if not proj.scenes:
        err("No scenes yet — run /script first.")
        return
    size = ASPECTS[proj.aspect]
    print()
    for s in proj.scenes:
        if not s.image_path or not Path(s.image_path).exists():
            warn(f"Scene {s.index:02}: missing image — skipping")
            continue
        if not s.audio_path or not Path(s.audio_path).exists():
            warn(f"Scene {s.index:02}: missing audio — skipping")
            continue
        raw   = proj.dir / "clips" / f"_raw_{s.index:02}.mp4"
        final = proj.dir / "clips" / f"scene_{s.index:02}.mp4"
        sp    = Spinner(f"Scene {s.index:02}  Ken Burns ({s.duration:.1f} s)")
        sp.start()
        try:
            build_ken_burns_clip(
                Path(s.image_path), s.duration or 4.0,
                raw, size,
                fps=FPS_DEFAULT,
                zoom_in=(s.index % 2 == 0),
            )
            mux_audio(raw, Path(s.audio_path), final)
            raw.unlink(missing_ok=True)
            s.clip_path = str(final)
            sp.stop(success=True, msg=f"scene {s.index:02} → {final.name}")
        except Exception as exc:
            sp.stop(success=False, msg=f"scene {s.index:02} failed")
            err(str(exc))
            raw.unlink(missing_ok=True)  # BUG FIX: clean up partial raw clip on error
    proj.save()


def step_stitch(proj: Project, mode: str):
    section(f"Stitching final film  ({mode})")
    clips = [Path(s.clip_path) for s in proj.scenes
             if s.clip_path and Path(s.clip_path).exists()]
    if not clips:
        err("No clips built — run /clips first.")
        return
    # BUG FIX: warn if some scenes are missing clips (not all) so the user
    # knows the output won't include every scene.
    missing = [s.index for s in proj.scenes if not (s.clip_path and Path(s.clip_path).exists())]
    if missing:
        warn(f"Stitching without scene(s): {missing} (their clips were not built)")

    out_mp4 = proj.output_path()
    sp = Spinner(f"Stitching {len(clips)} clips…")
    sp.start()
    try:
        if mode == "crossfade":
            stitch_crossfade(clips, out_mp4)
        else:
            stitch_concat(clips, out_mp4)
        sp.stop(success=True, msg=f"Film stitched → {out_mp4.name}")
    except Exception as exc:
        sp.stop(success=False, msg="Stitch failed")
        err(str(exc))
        return

    if proj.music:
        sp2 = Spinner(f"Mixing '{proj.music_mood}' ambient bed…")
        sp2.start()
        try:
            with_music = proj.dir / "output" / f"{proj.name}_with_music.mp4"
            mix_music_under(out_mp4, with_music, proj.music_mood)
            with_music.replace(out_mp4)   # atomic replace
            sp2.stop(success=True, msg="Ambient music mixed in (quiet, under narration)")
        except Exception as exc:
            sp2.stop(success=False, msg="Music mix failed — continuing without music")
            warn(str(exc))

    try:
        write_srt(proj.scenes, proj.srt_path())
        ok(f"Subtitles     → {proj.srt_path()}")
    except Exception as exc:
        warn(f"SRT write failed: {exc}")

    print()
    ok(f"Final film    → {out_mp4}")


def step_render_all(proj: Project, pool: ProviderPool,
                    num_scenes: int, mode: str):
    step_script(proj, pool, num_scenes)
    if not proj.scenes:
        return
    step_images(proj)
    step_voice(proj, proj.voice)
    step_clips(proj)
    step_stitch(proj, mode)


# ─────────────────────────────────────────────────────────────
# FIRST-RUN SETUP
# ─────────────────────────────────────────────────────────────
def first_run_setup() -> Dict:
    cfg = load_config()
    if cfg.get("nim_key"):
        return cfg
    w = 62
    print()
    print(f"  {C.DIMGRAY}{TL}{H * (w - 2)}{TR}{C.R}")
    print(f"  {C.DIMGRAY}{V}{C.R}  {C.BOLD}{C.ACCENTB}First-time setup{C.R}  "
          f"{C.DIMGRAY}free NVIDIA NIM key required{C.R}"
          + " " * 10 + f"  {C.DIMGRAY}{V}{C.R}")
    print(f"  {C.DIMGRAY}{BL}{H * (w - 2)}{BR}{C.R}")
    print()
    info("Get a free key at  [https://build.nvidia.com](https://build.nvidia.com)  →  API Keys")
    print()
    try:
        key = input(f"  {C.AMBER}{ARROW} {C.R}{C.BOLD}Paste your NVIDIA NIM API key:{C.R} ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)
    if not key:
        err("No key entered — exiting.")
        sys.exit(1)
    cfg = {"nim_key": key, "model": DEFAULT_NIM_MODEL, "rpm": 20.0}
    save_config(cfg)
    ok("Saved to ~/.film_kit_config.json")
    return cfg


# ─────────────────────────────────────────────────────────────
# HELP & STATUS
# ─────────────────────────────────────────────────────────────
def _cmd(name: str, desc: str, width: int = 34) -> str:
    """Format a command line for /help."""
    cmd_part = f"{C.ACCENT}{name}{C.R}"
    raw_len  = len(name)
    pad      = " " * max(1, width - raw_len)
    return f"    {cmd_part}{pad}{C.SILVER}{desc}{C.R}"


HELP = f"""
  {C.BOLD}{C.WHITE}Pipeline{C.R}
{_cmd('/project <name>',             'create or open a project')}
{_cmd('/idea <text>',                'set the story idea')}
{_cmd('/style <text>',               'set the visual style (default: cinematic, warm lighting)')}
{_cmd('/aspect <16:9|9:16|1:1>',     'set frame aspect ratio (default 16:9)')}
{_cmd('/seed [reroll]',              'show or reroll the image seed')}
{_cmd('/music <on|off> [mood]',      'toggle ambient music: ambient · tense · bright')}
{_cmd('/script [n]',                 'generate an n-scene script (default 6)')}
{_cmd('/images',                     'generate a storyboard image per scene')}
{_cmd('/voice [name]',               'synthesise narration (see /voices)')}
{_cmd('/clips',                      'render each scene into a Ken Burns clip')}
{_cmd('/stitch [cut|crossfade]',     'stitch clips into the final film')}
{_cmd('/render [n] [cut|crossfade]', 'run the entire pipeline end to end')}

  {C.BOLD}{C.WHITE}Utility{C.R}
{_cmd('/status',  'show project status')}
{_cmd('/voices',  'list available narration voices')}
{_cmd('/help',    'show this message')}
{_cmd('/quit',    'save and exit')}
"""


def print_status(proj: Project):
    section("Project status")
    print()
    kv_row("name",   proj.name)
    kv_row("idea",   proj.idea or f"{C.DIMGRAY}(not set){C.R}")
    kv_row("style",  proj.style)
    kv_row("aspect", proj.aspect)
    kv_row("voice",  proj.voice)
    kv_row("seed",   str(proj.seed))
    kv_row("music",  f"{'on' if proj.music else 'off'}  ·  {proj.music_mood}")
    kv_row("scenes", str(len(proj.scenes)))
    print()
    if proj.scenes:
        # BUG FIX: use pathlib.Path.exists() checks instead of truthy path
        # strings — a non-None path could point to a deleted file.
        for s in proj.scenes:
            img = f"{C.ACCENT}img{C.R}" if s.image_path and Path(s.image_path).exists() else f"{C.DIMGRAY}img{C.R}"
            aud = f"{C.ACCENT}aud{C.R}" if s.audio_path and Path(s.audio_path).exists() else f"{C.DIMGRAY}aud{C.R}"
            clp = f"{C.ACCENT}clip{C.R}"if s.clip_path  and Path(s.clip_path).exists()  else f"{C.DIMGRAY}clip{C.R}"
            idx  = f"{C.PURPLE}[{s.index:02}]{C.R}"
            narr = f"{C.SILVER}{s.narration[:58]}{C.R}"
            print(f"    {idx}  {img} {aud} {clp}  {narr}")
    out = proj.output_path()
    if out.exists():
        size_mb = out.stat().st_size / 1_048_576
        print()
        ok(f"Output exists: {out}  ({size_mb:.1f} MB)")


def print_voices():
    section("Narration voices")
    print()
    for k, v in VOICES.items():
        print(f"    {C.ACCENT}{k:<10}{C.R}  {C.DIMGRAY}{v}{C.R}")
    print()


# ─────────────────────────────────────────────────────────────
# ARGUMENT PARSER
# ─────────────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Film Kit v2.0 — free-tier AI filmmaking pipeline. "
            "Run with no arguments for the interactive REPL, "
            "or pass --idea to run the full pipeline non-interactively."
        )
    )
    p.add_argument("--project",    help="project name (default: my_film)")
    p.add_argument("--idea",       help="story idea; triggers batch/non-interactive mode")
    p.add_argument("--style",      default="cinematic, warm lighting, detailed")
    p.add_argument("--aspect",     choices=list(ASPECTS), default="16:9")
    p.add_argument("--voice",      choices=list(VOICES),  default="aria")
    p.add_argument("--scenes",     type=int, default=6)
    p.add_argument("--mode",       choices=["cut", "crossfade"], default="cut")
    p.add_argument("--music",      action="store_true")
    p.add_argument("--music-mood", choices=MUSIC_MOODS, default="ambient")
    p.add_argument("--seed",       type=int)
    p.add_argument("--key",        help="NVIDIA NIM API key (overwrites saved key)")
    return p.parse_args()


# ─────────────────────────────────────────────────────────────
# BATCH MODE
# ─────────────────────────────────────────────────────────────
def run_batch(args: argparse.Namespace) -> int:
    banner()
    info("Batch mode — running full pipeline")
    print()

    missing: List[str] = []
    if not HAS_OPENAI:
        missing.append("pip install openai")
    if not HAS_EDGE_TTS:
        missing.append("pip install edge-tts")
    if not ensure_ffmpeg():
        missing.append("ffmpeg + ffprobe on PATH")
    if missing:
        for m in missing:
            err(f"Missing dependency: {m}")
        return 1

    cfg = load_config()
    if args.key:
        cfg["nim_key"] = args.key
        cfg.setdefault("model", DEFAULT_NIM_MODEL)
        cfg.setdefault("rpm", 20.0)
        save_config(cfg)
    if not cfg.get("nim_key"):
        err("No NIM API key. Pass --key <key> or run interactively to set it up.")
        return 1

    try:
        pool = build_provider_pool(cfg)
    except Exception as exc:
        err(f"LLM pool not ready: {exc}")
        return 1

    # BUG FIX: catch invalid project names early in batch mode too
    proj_name = args.project or "my_film"
    try:
        proj = Project(proj_name)
    except ValueError as exc:
        err(str(exc))
        return 1

    proj.idea       = args.idea
    proj.style      = args.style
    proj.aspect     = args.aspect
    proj.voice      = args.voice
    proj.music      = args.music
    proj.music_mood = args.music_mood
    if args.seed is not None:
        proj.seed   = args.seed
    proj.save()
    ok(f"Project ready at {proj.dir}")
    print()

    step_render_all(proj, pool, args.scenes, args.mode)

    success = bool(proj.scenes) and all(s.clip_path for s in proj.scenes)
    return 0 if success else 1


# ─────────────────────────────────────────────────────────────
# INTERACTIVE REPL
# ─────────────────────────────────────────────────────────────
def repl(cfg: Dict, args: argparse.Namespace):
    pool: Optional[ProviderPool] = None
    try:
        pool = build_provider_pool(cfg)
    except Exception as exc:
        warn(f"LLM pool not ready ({exc}) — /script will fail until fixed.")

    proj_name = args.project
    if not proj_name:
        try:
            proj_name = input(
                f"\n  {C.AMBER}{ARROW} {C.R}{C.BOLD}Project name{C.R}"
                f" {C.DIMGRAY}[my_film]{C.R}: "
            ).strip() or "my_film"
        except (EOFError, KeyboardInterrupt):
            print()
            return

    try:
        proj = Project(proj_name)
    except ValueError as exc:
        err(str(exc))
        return

    ok(f"Project ready at {proj.dir}")
    print(HELP)

    while True:
        try:
            raw = input(
                f"{C.ACCENT}{ARROW}{C.R}{C.BOLD} {C.R}"
            ).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not raw:
            continue

        cmd  = raw.split()[0].lower()
        rest = raw[len(cmd):].strip()

        if cmd in ("/quit", "/exit", "quit", "exit"):
            break

        elif cmd == "/help":
            print(HELP)

        elif cmd == "/status":
            print_status(proj)

        elif cmd == "/voices":
            print_voices()

        elif cmd == "/project":
            if not rest:
                err("Usage: /project <name>")
            else:
                try:
                    proj = Project(rest)
                    ok(f"Switched to project '{proj.name}'")
                except ValueError as exc:
                    err(str(exc))

        elif cmd == "/idea":
            if not rest:
                err("Usage: /idea <your story idea>")
            else:
                proj.idea = rest
                proj.save()
                ok("Idea set.")

        elif cmd == "/style":
            if not rest:
                err("Usage: /style <visual style description>")
            else:
                proj.style = rest
                proj.save()
                ok("Style set.")

        elif cmd == "/aspect":
            if rest in ASPECTS:
                proj.aspect = rest
                proj.save()
                ok(f"Aspect set to {rest}")
            else:
                err(f"Choose one of: {', '.join(ASPECTS)}")

        elif cmd == "/seed":
            parts = rest.split()
            if parts and parts[0] == "reroll":
                proj.seed = random.randint(0, 999_999)
                proj.save()
                ok(f"New seed: {proj.seed}  (re-run /images to apply)")
            else:
                info(f"Current seed: {proj.seed}")

        elif cmd == "/music":
            # /music <on|off> [mood]
            parts = rest.split()
            if not parts or parts[0] not in ("on", "off"):
                err(f"Usage: /music <on|off> [{' | '.join(MUSIC_MOODS)}]")
            else:
                proj.music = (parts[0] == "on")
                if len(parts) > 1 and parts[1] in MUSIC_MOODS:
                    proj.music_mood = parts[1]
                proj.save()
                ok(f"Music {'on' if proj.music else 'off'}  ·  mood: {proj.music_mood}")

        elif cmd == "/script":
            # BUG FIX: validate that the argument is actually a digit before
            # calling int() — old code would raise ValueError on /script abc
            parts = rest.split()
            n = 6
            if parts:
                if parts[0].isdigit():
                    n = int(parts[0])
                else:
                    err(f"Expected a number of scenes, got {parts[0]!r}")
                    continue
            if pool is None:
                err("LLM pool unavailable — check your NIM key.")
            else:
                step_script(proj, pool, n)

        elif cmd == "/images":
            step_images(proj)

        elif cmd == "/voice":
            vk = rest or proj.voice
            step_voice(proj, vk)

        elif cmd == "/clips":
            step_clips(proj)

        elif cmd == "/stitch":
            mode = rest if rest in ("cut", "crossfade") else "cut"
            step_stitch(proj, mode)

        elif cmd == "/render":
            parts = rest.split()
            n    = 6
            mode = "cut"
            for part in parts:
                if part.isdigit():
                    n = int(part)
                elif part in ("cut", "crossfade"):
                    mode = part
                else:
                    warn(f"Ignoring unknown /render argument: {part!r}")
            if pool is None:
                err("LLM pool unavailable — check your NIM key.")
            else:
                step_render_all(proj, pool, n, mode)

        else:
            warn(f"Unknown command {cmd!r}  —  type /help for a list.")

    ok("Bye — project saved.")


# ─────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────
def main():
    args = parse_args()

    if args.idea:
        sys.exit(run_batch(args))

    banner()

    # Dependency checks — print warnings, don't abort
    if not HAS_OPENAI:
        warn("openai not installed — run:  pip install openai")
    if not HAS_EDGE_TTS:
        warn("edge-tts not installed — run:  pip install edge-tts")
    if not ensure_ffmpeg():
        warn("ffmpeg/ffprobe not found — install ffmpeg and add it to PATH")

    cfg = first_run_setup()
    if args.key:
        cfg["nim_key"] = args.key
        save_config(cfg)

    repl(cfg, args)


if __name__ == "__main__":
    main()