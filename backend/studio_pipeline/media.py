"""FFmpeg + HTTP media primitives: clip synthesis, normalisation, audio, concatenation.

Why local synthesis matters here: the OmniRoute video route is not live (STAGE 0), and
the previous pipeline papered over that by emitting URLs that do not resolve
(``https://cdn.pollinations.ai/video/clip_*.mp4``) or a stock Elephants-Dream sample
for every scene. Neither produces a film.

Instead the Animator's fallback is real: fetch the scene's Pollinations still (keyless,
verified working) and synthesise a genuine H.264 clip of the requested duration with a
Ken-Burns move. The output is a true MP4 with true frames, so the Director's FFmpeg
concat produces a real 3-hour feature today, and swapping in OmniRoute video later
changes only which branch fills ``clips/scene_NNNNN.mp4``.

Every clip is normalised to one codec profile (same resolution, fps, pixel format,
audio layout), which lets the concat demuxer stream-copy hundreds of clips instead of
re-encoding three hours of video.
"""
from __future__ import annotations

import asyncio
import math
import os
import shutil
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import httpx

# ---------------------------------------------------------------- render profile
TARGET_FPS = 24
TARGET_SIZE: Dict[str, Tuple[int, int]] = {
    "16:9": (1280, 720),
    "9:16": (720, 1280),
    "1:1": (1024, 1024),
    "4:3": (1024, 768),
    "21:9": (1680, 720),
}
AUDIO_RATE = 44100
AUDIO_CHANNELS = 2

#: Batch size for chunked concatenation. Keeps concat manifests small and gives the
#: Director a resumable checkpoint every N clips.
CONCAT_BATCH = 60


class MediaError(RuntimeError):
    """An ffmpeg invocation or media download failed."""


@dataclass
class ProcResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def tail(self, n: int = 600) -> str:
        return (self.stderr or self.stdout or "").strip()[-n:]


def ffmpeg_bin() -> str:
    return os.getenv("FFMPEG_BIN") or shutil.which("ffmpeg") or "ffmpeg"


def ffprobe_bin() -> str:
    return os.getenv("FFPROBE_BIN") or shutil.which("ffprobe") or "ffprobe"


def ffmpeg_available() -> bool:
    return shutil.which(ffmpeg_bin()) is not None or Path(ffmpeg_bin()).exists()


def resolve_size(aspect_ratio: str) -> Tuple[int, int]:
    return TARGET_SIZE.get(aspect_ratio, TARGET_SIZE["16:9"])


async def run_proc(args: Sequence[str], *, timeout: float = 900.0) -> ProcResult:
    """Run a subprocess, capture both streams, and kill it on timeout."""
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        await asyncio.gather(proc.wait(), return_exceptions=True)
        raise MediaError(f"timed out after {timeout:g}s: {' '.join(args[:6])} …")
    return ProcResult(
        returncode=proc.returncode if proc.returncode is not None else -1,
        stdout=(out or b"").decode("utf-8", "replace"),
        stderr=(err or b"").decode("utf-8", "replace"),
    )


async def probe_duration(path: Path) -> Optional[float]:
    """Duration in seconds, or ``None`` if the file is missing/unreadable/not media."""
    if not path.exists():
        return None
    res = await run_proc(
        [
            ffprobe_bin(),
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        timeout=60.0,
    )
    if not res.ok:
        return None
    try:
        value = float(res.stdout.strip().splitlines()[0])
    except (ValueError, IndexError):
        return None
    return value if value > 0 else None


async def is_playable(path: Path, *, min_seconds: float = 0.4) -> bool:
    """True when the file decodes as media of at least ``min_seconds``.

    Used for idempotent resume: a clip that already exists and probes clean is not
    re-rendered, and a clip truncated by a crash is.
    """
    duration = await probe_duration(path)
    return duration is not None and duration >= min_seconds


# ------------------------------------------------------------------- downloads
def pollinations_image_url(
    prompt: str,
    *,
    width: int = 1280,
    height: int = 720,
    seed: Optional[int] = None,
    model: str = "flux",
) -> str:
    """Keyless Pollinations still-image URL. Verified working without a key."""
    encoded = urllib.parse.quote(prompt.strip()[:1800], safe="")
    params = {
        "width": str(width),
        "height": str(height),
        "nologo": "true",
        "model": model,
    }
    if seed is not None:
        params["seed"] = str(int(seed))
    return f"https://image.pollinations.ai/prompt/{encoded}?{urllib.parse.urlencode(params)}"


def streamelements_tts_url(text: str, voice: str = "Brian") -> str:
    """Legacy keyless TTS URL. **No longer usable** - kept only to document the failure.

    As of 2026-08-22 this returns ``401 {"error":"Unauthorized","message":"No API key
    was found"}``. The previous pipeline hard-coded such a URL as its ``voice_track``,
    so every "finished" film pointed at an unauthorised endpoint. Use
    :func:`synthesize_narration` instead.
    """
    return (
        "https://api.streamelements.com/kappa/v2/speech"
        f"?voice={urllib.parse.quote(voice)}&text={urllib.parse.quote(text[:550])}"
    )


#: Google Translate's TTS endpoint. Verified keyless and working (HTTP 200,
#: audio/mpeg, 24 kHz mono) but it requires a browser-ish User-Agent and caps each
#: request at roughly 200 characters, hence :func:`chunk_text`.
GTTS_ENDPOINT = "https://translate.google.com/translate_tts"
GTTS_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
TTS_CHUNK_LIMIT = 190


def google_tts_url(text: str, *, lang: str = "en", idx: int = 0, total: int = 1) -> str:
    return (
        f"{GTTS_ENDPOINT}?ie=UTF-8&client=tw-ob"
        f"&q={urllib.parse.quote(text)}"
        f"&tl={urllib.parse.quote(lang)}"
        f"&total={max(1, total)}&idx={max(0, idx)}&textlen={len(text)}"
    )


def chunk_text(text: str, limit: int = TTS_CHUNK_LIMIT) -> List[str]:
    """Split narration into TTS-sized pieces, preferring sentence boundaries.

    Splitting mid-sentence produces audibly wrong prosody, so sentences are packed
    greedily and only over-long sentences are broken on whitespace.
    """
    clean = " ".join((text or "").split())
    if not clean:
        return []
    sentences: List[str] = []
    buf = ""
    for token in clean.replace("!", "!|").replace("?", "?|").replace(". ", ". |").split("|"):
        token = token.strip()
        if not token:
            continue
        if len(buf) + len(token) + 1 <= limit:
            buf = f"{buf} {token}".strip()
        else:
            if buf:
                sentences.append(buf)
            while len(token) > limit:
                cut = token.rfind(" ", 0, limit)
                if cut <= 0:
                    cut = limit
                sentences.append(token[:cut].strip())
                token = token[cut:].strip()
            buf = token
    if buf:
        sentences.append(buf)
    return [s for s in sentences if s]


async def _sapi_narrate(text: str, dest_wav: Path, *, voice_hint: str = "", timeout: float = 600.0) -> Path:
    """Offline narration via the Windows SAPI voice bundled with the OS.

    No network, no key, no length cap - the dependable floor under the network TTS
    path. Text is passed via a temp file so quoting never mangles the script.
    """
    dest_wav.parent.mkdir(parents=True, exist_ok=True)
    txt = dest_wav.with_suffix(".txt")
    txt.write_text(text, encoding="utf-8")
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        + (f"try {{ $s.SelectVoice('{voice_hint}') }} catch {{ }}; " if voice_hint else "")
        + f"$s.SetOutputToWaveFile('{dest_wav.resolve().as_posix()}'); "
        f"$s.Speak([IO.File]::ReadAllText('{txt.resolve().as_posix()}', "
        "[Text.Encoding]::UTF8)); $s.Dispose()"
    )
    res = await run_proc(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        timeout=timeout,
    )
    try:
        txt.unlink()
    except OSError:
        pass
    if not res.ok or not dest_wav.exists() or dest_wav.stat().st_size < 1024:
        raise MediaError(f"SAPI narration failed: {res.tail(300)}")
    return dest_wav


def _audio_codec_args(dest: Path, bitrate: str = "160k") -> List[str]:
    """Pick an encoder the destination container will actually accept.

    Getting this wrong stays silent until a fallback tier fires: the MP4 muxer takes AAC
    and the MP3 muxer refuses it outright, so a hardcoded ``-c:a aac`` write to a ``.mp3``
    path fails at runtime - exactly where the code is trying to recover from something
    else.
    """
    suffix = dest.suffix.lower()
    if suffix == ".mp3":
        codec = ["-c:a", "libmp3lame", "-b:a", bitrate]
    elif suffix == ".wav":
        codec = ["-c:a", "pcm_s16le"]
    elif suffix in (".opus", ".ogg"):
        codec = ["-c:a", "libopus", "-b:a", bitrate]
    else:
        codec = ["-c:a", "aac", "-b:a", bitrate]
    return codec + ["-ar", str(AUDIO_RATE), "-ac", str(AUDIO_CHANNELS)]


async def synthesize_silence(dest: Path, *, duration: float, timeout: float = 600.0) -> Path:
    """A silent stereo track - the last-resort narration so timing still holds."""
    duration = max(0.5, float(duration))
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp" + dest.suffix)
    res = await run_proc(
        [
            ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error", "-nostdin",
            "-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate={AUDIO_RATE}",
            "-t", f"{duration:.3f}",
            *_audio_codec_args(dest, "96k"),
            str(tmp),
        ],
        timeout=timeout,
    )
    if not res.ok or not tmp.exists():
        raise MediaError(f"silence synthesis failed: {res.tail()}")
    os.replace(tmp, dest)
    return dest


async def synthesize_narration(
    text: str,
    dest: Path,
    *,
    workdir: Path,
    lang: str = "en",
    client: Optional[httpx.AsyncClient] = None,
    fallback_duration: float = 4.0,
) -> Tuple[Path, str]:
    """Render narration to ``dest``, returning ``(path, source_used)``.

    Three tiers, tried in order, so narration is never a dead link:
      1. Google Translate TTS - keyless, verified working, chunked to its ~200 char cap.
      2. Windows SAPI - offline, unlimited length.
      3. Silence of ``fallback_duration`` - keeps the cut's timing intact.
    """
    pieces = chunk_text(text)
    if not pieces:
        await synthesize_silence(dest, duration=fallback_duration)
        return dest, "silence(empty text)"

    workdir.mkdir(parents=True, exist_ok=True)
    owned = client is None
    http = client or httpx.AsyncClient(follow_redirects=True, headers={"User-Agent": GTTS_UA})
    try:
        parts: List[Path] = []
        for i, piece in enumerate(pieces):
            part = workdir / f"{dest.stem}_tts_{i:03d}.mp3"
            try:
                await download(
                    google_tts_url(piece, lang=lang, idx=i, total=len(pieces)),
                    part,
                    client=http,
                    timeout=60.0,
                    attempts=2,
                    min_bytes=512,
                )
                parts.append(part)
            except MediaError:
                parts = []
                break
        if parts:
            try:
                if len(parts) == 1:
                    shutil.copy2(parts[0], dest)
                else:
                    await concat_audio(parts, dest, workdir=workdir)
                return dest, "google-translate-tts"
            except MediaError:
                pass
    finally:
        if owned:
            await http.aclose()

    wav = workdir / f"{dest.stem}_sapi.wav"
    try:
        await _sapi_narrate(text, wav)
        res = await run_proc(
            [
                ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error", "-nostdin",
                "-i", str(wav),
                *_audio_codec_args(dest, "160k"),
                str(dest),
            ],
            timeout=900.0,
        )
        if res.ok and dest.exists():
            return dest, "windows-sapi"
    except MediaError:
        pass

    await synthesize_silence(dest, duration=fallback_duration)
    return dest, "silence(tts unavailable)"


async def download(
    url: str,
    dest: Path,
    *,
    client: Optional[httpx.AsyncClient] = None,
    timeout: float = 240.0,
    attempts: int = 3,
    min_bytes: int = 1024,
) -> Path:
    """Stream ``url`` to ``dest`` atomically, with retries.

    Pollinations synthesises on request and can take 20-60s per image, hence the long
    default timeout. Writes to a temp file first so a partial download never looks like
    a finished artifact to the resume logic.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    owned = client is None
    http = client or httpx.AsyncClient(follow_redirects=True)
    last_error = "unknown"
    try:
        for attempt in range(attempts):
            try:
                written = 0
                with open(tmp, "wb") as fh:
                    async with http.stream("GET", url, timeout=timeout, follow_redirects=True) as resp:
                        if resp.status_code >= 400:
                            last_error = f"HTTP {resp.status_code}"
                            raise MediaError(last_error)
                        async for chunk in resp.aiter_bytes(65536):
                            fh.write(chunk)
                            written += len(chunk)
                if written < min_bytes:
                    last_error = f"suspiciously small response ({written} bytes)"
                    raise MediaError(last_error)
                os.replace(tmp, dest)
                return dest
            except (httpx.HTTPError, MediaError, OSError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt < attempts - 1:
                    await asyncio.sleep(2.0 * (attempt + 1))
    finally:
        if owned:
            await http.aclose()
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
    raise MediaError(f"download failed for {url[:120]}…: {last_error}")


# -------------------------------------------------------------- clip synthesis
def _kenburns_filter(motion: str, width: int, height: int, duration: float, fps: int) -> str:
    """Build a zoompan filtergraph implementing the storyboard's camera move.

    ``on`` is the output frame index, so expressions are written against total frame
    count rather than wall time — that keeps the move exactly as long as the clip.
    """
    total = max(2, int(round(duration * fps)))
    m = (motion or "").lower()
    # Oversample before zoompan so the crop is sampled from real detail, not upscaled
    # pixels. 2x the target width is enough for a 1.35x maximum zoom.
    pre = f"scale={width * 2}:{height * 2}:force_original_aspect_ratio=increase,crop={width * 2}:{height * 2}"

    cx = "iw/2-(iw/zoom/2)"
    cy = "ih/2-(ih/zoom/2)"

    if any(k in m for k in ("zoom out", "zoom-out", "pull back", "pullback", "dolly out", "widen")):
        z = f"max(1.35-0.35*on/{total},1.0)"
        x, y = cx, cy
    elif any(k in m for k in ("pan left", "pan-left", "truck left", "dolly left")):
        z = "1.2"
        x, y = f"(iw-iw/zoom)*(1-on/{total})", cy
    elif any(k in m for k in ("pan right", "pan-right", "truck right", "dolly right", "pan")):
        z = "1.2"
        x, y = f"(iw-iw/zoom)*on/{total}", cy
    elif any(k in m for k in ("tilt up", "crane up", "boom up", "rise")):
        z = "1.2"
        x, y = cx, f"(ih-ih/zoom)*(1-on/{total})"
    elif any(k in m for k in ("tilt down", "crane down", "boom down", "descend")):
        z = "1.2"
        x, y = cx, f"(ih-ih/zoom)*on/{total}"
    elif any(k in m for k in ("static", "lock", "still", "hold")):
        z = f"min(1.0+0.03*on/{total},1.03)"
        x, y = cx, cy
    else:  # default: a slow push in — reads as intentional on any subject
        z = f"min(1.0+0.30*on/{total},1.30)"
        x, y = cx, cy

    return (
        f"{pre},"
        f"zoompan=z='{z}':x='{x}':y='{y}':d=1:s={width}x{height}:fps={fps},"
        f"format=yuv420p"
    )


async def synthesize_kenburns_clip(
    still: Path,
    dest: Path,
    *,
    duration: float,
    width: int,
    height: int,
    motion: str = "",
    fps: int = TARGET_FPS,
    fade: float = 0.4,
    timeout: float = 900.0,
) -> Path:
    """Render a real MP4 of ``duration`` seconds from one still image.

    Includes a silent stereo track so every clip in the film has identical stream
    layout — a prerequisite for stream-copy concatenation.
    """
    if not still.exists():
        raise MediaError(f"still image missing: {still}")
    duration = max(1.0, float(duration))
    vf = _kenburns_filter(motion, width, height, duration, fps)
    if fade > 0 and duration > 2 * fade + 0.5:
        vf += f",fade=t=in:st=0:d={fade:.2f},fade=t=out:st={duration - fade:.2f}:d={fade:.2f}"

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp.mp4")
    args = [
        ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error", "-nostdin",
        "-loop", "1", "-framerate", str(fps), "-t", f"{duration:.3f}", "-i", str(still),
        "-f", "lavfi", "-t", f"{duration:.3f}",
        "-i", f"anullsrc=channel_layout=stereo:sample_rate={AUDIO_RATE}",
        "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
        "-pix_fmt", "yuv420p", "-r", str(fps),
        "-c:a", "aac", "-b:a", "128k", "-ar", str(AUDIO_RATE), "-ac", str(AUDIO_CHANNELS),
        "-shortest", "-movflags", "+faststart",
        str(tmp),
    ]
    res = await run_proc(args, timeout=timeout)
    if not res.ok or not tmp.exists():
        raise MediaError(f"ken-burns render failed for {still.name}: {res.tail()}")
    os.replace(tmp, dest)
    return dest


async def normalize_clip(
    src: Path,
    dest: Path,
    *,
    duration: Optional[float] = None,
    width: int = 1280,
    height: int = 720,
    fps: int = TARGET_FPS,
    timeout: float = 1200.0,
) -> Path:
    """Re-encode any source clip into the film's uniform profile.

    Provider clips arrive at assorted resolutions, frame rates and audio layouts;
    concatenating those directly produces timestamp drift and A/V desync. Pad rather
    than crop so nothing composed by the Scene Designer is lost.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp.mp4")
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
        f"fps={fps},format=yuv420p,setsar=1"
    )
    args = [
        ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error", "-nostdin",
        "-i", str(src),
        "-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate={AUDIO_RATE}",
        "-filter_complex", f"[0:v]{vf}[v];[0:a]anull[a0]",
        # Prefer the source's own audio when it has one; anullsrc covers silent inputs.
        "-map", "[v]", "-map", "0:a?", "-map", "1:a",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-ar", str(AUDIO_RATE), "-ac", str(AUDIO_CHANNELS),
        "-movflags", "+faststart",
    ]
    if duration:
        args += ["-t", f"{float(duration):.3f}"]
    args.append(str(tmp))

    res = await run_proc(args, timeout=timeout)
    if not res.ok or not tmp.exists():
        # The dual-audio mapping above fails on inputs with no audio stream at all on
        # some builds; retry with the simple single-source form.
        args_simple = [
            ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error", "-nostdin",
            "-i", str(src),
            "-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate={AUDIO_RATE}",
            "-vf", vf,
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-ar", str(AUDIO_RATE), "-ac", str(AUDIO_CHANNELS),
            "-shortest", "-movflags", "+faststart",
        ]
        if duration:
            args_simple += ["-t", f"{float(duration):.3f}"]
        args_simple.append(str(tmp))
        res = await run_proc(args_simple, timeout=timeout)
        if not res.ok or not tmp.exists():
            raise MediaError(f"normalise failed for {src.name}: {res.tail()}")
    os.replace(tmp, dest)
    return dest


# ------------------------------------------------------------------------ audio
async def synthesize_music_bed(
    dest: Path,
    *,
    duration: float,
    key_hz: float = 110.0,
    bpm: int = 84,
    timeout: float = 1800.0,
) -> Path:
    """Procedurally synthesise an ambient score bed with ffmpeg only.

    There is no keyless music-generation API wired into this deployment, so rather
    than reference a track that does not exist, the Sound Director builds one: a root
    + fifth + octave drone, detuned, tremolo-modulated at the tempo, low-passed and
    reverb-ish via a short echo. It is deliberately quiet and unobtrusive.
    """
    duration = max(2.0, float(duration))
    tremolo_hz = max(0.1, bpm / 60.0 / 2.0)
    fifth = key_hz * 1.5
    octave = key_hz * 2.0
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp.m4a")

    filtergraph = (
        f"sine=frequency={key_hz:.2f}:sample_rate={AUDIO_RATE}:duration={duration:.2f}[a];"
        f"sine=frequency={fifth:.2f}:sample_rate={AUDIO_RATE}:duration={duration:.2f}[b];"
        f"sine=frequency={octave:.2f}:sample_rate={AUDIO_RATE}:duration={duration:.2f}[c];"
        f"sine=frequency={key_hz * 1.005:.2f}:sample_rate={AUDIO_RATE}:duration={duration:.2f}[d];"
        "[a][b][c][d]amix=inputs=4:duration=longest:weights=1 0.5 0.28 0.7[mix];"
        f"[mix]tremolo=f={tremolo_hz:.3f}:d=0.35,"
        "lowpass=f=900,highpass=f=45,"
        "aecho=0.8:0.9:60|180:0.28|0.14,"
        f"volume=0.16,afade=t=in:st=0:d=2,afade=t=out:st={max(0.0, duration - 3):.2f}:d=3,"
        f"aformat=sample_rates={AUDIO_RATE}:channel_layouts=stereo[out]"
    )
    args = [
        ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error", "-nostdin",
        "-filter_complex", filtergraph, "-map", "[out]",
        "-c:a", "aac", "-b:a", "160k", "-ar", str(AUDIO_RATE), "-ac", str(AUDIO_CHANNELS),
        "-t", f"{duration:.3f}",
        str(tmp),
    ]
    res = await run_proc(args, timeout=timeout)
    if not res.ok or not tmp.exists():
        raise MediaError(f"music bed synthesis failed: {res.tail()}")
    os.replace(tmp, dest)
    return dest


async def concat_audio(parts: Sequence[Path], dest: Path, *, workdir: Path, timeout: float = 1800.0) -> Path:
    """Concatenate narration fragments into one track via the concat demuxer."""
    usable = [p for p in parts if p.exists() and p.stat().st_size > 512]
    if not usable:
        raise MediaError("no usable audio parts to concatenate")
    workdir.mkdir(parents=True, exist_ok=True)
    listing = workdir / f"{dest.stem}_audio_concat.txt"
    listing.write_text(
        "".join(f"file '{p.resolve().as_posix()}'\n" for p in usable),
        encoding="utf-8",
    )
    tmp = dest.with_suffix(".tmp" + dest.suffix)
    args = [
        ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error", "-nostdin",
        "-f", "concat", "-safe", "0", "-i", str(listing),
        *_audio_codec_args(dest, "160k"),
        str(tmp),
    ]
    res = await run_proc(args, timeout=timeout)
    if not res.ok or not tmp.exists():
        raise MediaError(f"audio concat failed: {res.tail()}")
    os.replace(tmp, dest)
    return dest


async def mix_final_audio(
    video: Path,
    dest: Path,
    *,
    narration: Optional[Path] = None,
    music: Optional[Path] = None,
    loop_music: bool = False,
    timeout: float = 3600.0,
) -> Path:
    """Mux narration and music onto the cut, ducking music under dialogue.

    ``sidechaincompress`` keys the music's gain off the narration, which is how a real
    mix keeps a score from fighting the voice. Falls back to a flat ``amix`` on builds
    without that filter.

    ``loop_music`` repeats a short score bed for the whole runtime. Synthesising three
    hours of audio up front costs minutes of CPU for something the muxer can loop for
    free, so the Sound Director renders a couple of minutes and sets this.

    Note this maps only the video stream from ``video`` - any audio already on the cut is
    replaced, not mixed. Clips carry a silent track purely so their stream layout matches
    for the concat, so there is nothing to preserve.
    """
    if narration is None and music is None:
        if video.resolve() != dest.resolve():
            shutil.copy2(video, dest)
        return dest

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp.mp4")
    inputs: List[str] = ["-i", str(video)]
    idx = 1
    vo_idx = music_idx = None
    if narration is not None and narration.exists():
        inputs += ["-i", str(narration)]
        vo_idx = idx
        idx += 1
    if music is not None and music.exists():
        # -stream_loop must precede the -i it applies to.
        if loop_music:
            inputs += ["-stream_loop", "-1"]
        inputs += ["-i", str(music)]
        music_idx = idx
        idx += 1

    if vo_idx is not None and music_idx is not None:
        fc = (
            f"[{vo_idx}:a]aformat=sample_rates={AUDIO_RATE}:channel_layouts=stereo,volume=1.0,asplit=2[vo][key];"
            f"[{music_idx}:a]aformat=sample_rates={AUDIO_RATE}:channel_layouts=stereo[mus];"
            "[mus][key]sidechaincompress=threshold=0.05:ratio=8:attack=20:release=600[ducked];"
            "[vo][ducked]amix=inputs=2:duration=longest:dropout_transition=3,"
            f"aformat=sample_rates={AUDIO_RATE}:channel_layouts=stereo,apad[aout]"
        )
    elif vo_idx is not None:
        fc = f"[{vo_idx}:a]aformat=sample_rates={AUDIO_RATE}:channel_layouts=stereo,apad[aout]"
    else:
        fc = f"[{music_idx}:a]aformat=sample_rates={AUDIO_RATE}:channel_layouts=stereo,apad[aout]"

    base = [ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error", "-nostdin", *inputs]
    tail = [
        "-map", "0:v:0", "-map", "[aout]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-shortest", "-movflags", "+faststart", str(tmp),
    ]
    res = await run_proc(base + ["-filter_complex", fc] + tail, timeout=timeout)

    if (not res.ok or not tmp.exists()) and vo_idx is not None and music_idx is not None:
        flat = (
            f"[{vo_idx}:a]aformat=sample_rates={AUDIO_RATE}:channel_layouts=stereo,volume=1.0[vo];"
            f"[{music_idx}:a]aformat=sample_rates={AUDIO_RATE}:channel_layouts=stereo,volume=0.25[mus];"
            "[vo][mus]amix=inputs=2:duration=longest:dropout_transition=3,apad[aout]"
        )
        res = await run_proc(base + ["-filter_complex", flat] + tail, timeout=timeout)

    if not res.ok or not tmp.exists():
        raise MediaError(f"final audio mix failed: {res.tail()}")
    os.replace(tmp, dest)
    return dest


# ---------------------------------------------------------------- concatenation
def write_concat_manifest(clips: Sequence[Path], dest: Path) -> Path:
    """Write an ffmpeg concat-demuxer manifest.

    Paths are emitted POSIX-style and single-quoted: the demuxer treats backslashes as
    escapes, so raw Windows paths break it. Embedded single quotes are escaped per the
    demuxer's own rules.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for clip in clips:
        p = clip.resolve().as_posix().replace("'", "'\\''")
        lines.append(f"file '{p}'\n")
    dest.write_text("".join(lines), encoding="utf-8")
    return dest


async def concat_copy(clips: Sequence[Path], dest: Path, *, manifest: Path, timeout: float = 3600.0) -> Path:
    """Concatenate uniformly-encoded clips with stream copy (no re-encode)."""
    if not clips:
        raise MediaError("nothing to concatenate")
    write_concat_manifest(clips, manifest)
    tmp = dest.with_suffix(".tmp.mp4")
    args = [
        ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error", "-nostdin",
        "-f", "concat", "-safe", "0", "-i", str(manifest),
        "-c", "copy", "-movflags", "+faststart",
        "-fflags", "+genpts",
        str(tmp),
    ]
    res = await run_proc(args, timeout=timeout)
    if not res.ok or not tmp.exists():
        # Stream copy is intolerant of any residual parameter mismatch; a re-encode
        # always works and is only reached when normalisation missed something.
        args_reencode = [
            ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error", "-nostdin",
            "-f", "concat", "-safe", "0", "-i", str(manifest),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-ar", str(AUDIO_RATE), "-ac", str(AUDIO_CHANNELS),
            "-movflags", "+faststart", str(tmp),
        ]
        res = await run_proc(args_reencode, timeout=timeout * 2)
        if not res.ok or not tmp.exists():
            raise MediaError(f"concat failed ({len(clips)} clips): {res.tail()}")
    os.replace(tmp, dest)
    return dest


async def synthesize_slate_clip(
    dest: Path,
    *,
    duration: float,
    width: int = 1280,
    height: int = 720,
    fps: int = TARGET_FPS,
    rgb: str = "0x101418",
    timeout: float = 900.0,
) -> Path:
    """A dark, slowly-breathing colour field of exactly ``duration`` seconds.

    The hole-filler of last resort. If a scene's still cannot be fetched at all, the
    Animator emits one of these rather than skipping the scene - a skipped scene silently
    shortens the film and desynchronises every cut after it, while a slate keeps the
    running time and the edit intact and shows up plainly as a gap in the picture.
    """
    duration = max(0.5, float(duration))
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp.mp4")
    # A gentle vignette pulse so the slate reads as intentional rather than as a freeze.
    vf = (
        f"format=yuv420p,vignette=PI/5,"
        f"eq=brightness='0.02*sin(2*PI*t/6)':eval=frame,setsar=1"
    )
    args = [
        ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error", "-nostdin",
        "-f", "lavfi", "-i", f"color=c={rgb}:s={width}x{height}:r={fps}:d={duration:.3f}",
        "-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate={AUDIO_RATE}",
        "-vf", vf,
        "-map", "0:v:0", "-map", "1:a:0",
        "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "26", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-ar", str(AUDIO_RATE), "-ac", str(AUDIO_CHANNELS),
        "-movflags", "+faststart",
        str(tmp),
    ]
    res = await run_proc(args, timeout=timeout)
    if not res.ok or not tmp.exists():
        raise MediaError(f"slate synthesis failed: {res.tail()}")
    os.replace(tmp, dest)
    return dest


async def fit_video_duration(
    src: Path,
    dest: Path,
    *,
    target: float,
    width: int = 1280,
    height: int = 720,
    fps: int = TARGET_FPS,
    tolerance: float = 0.5,
    timeout: float = 1800.0,
) -> Tuple[Path, str]:
    """Force ``src`` to exactly ``target`` seconds, returning ``(path, how)``.

    This is the reconciliation layer between what a video provider *gives* and what the
    storyboard *asked for*. Real text-to-video models emit fixed short clips (commonly
    5-10s) regardless of a requested 10-30s, so without this every scene's timing would
    silently drift and the cut would no longer match the script.

    Longer than target -> trim. Shorter -> loop with ``-stream_loop`` until the target is
    filled. Within tolerance -> straight normalise.
    """
    actual = await probe_duration(src)
    if actual is None:
        raise MediaError(f"cannot probe duration of {src}")

    target = max(1.0, float(target))
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
        f"fps={fps},format=yuv420p,setsar=1"
    )

    if actual >= target - tolerance and actual <= target + tolerance:
        await normalize_clip(src, dest, width=width, height=height, fps=fps, timeout=timeout)
        return dest, f"normalised ({actual:.2f}s)"

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp.mp4")

    if actual > target:
        pre_input: List[str] = []
        how = f"trimmed {actual:.2f}s -> {target:.2f}s"
    else:
        # -stream_loop must precede -i. Looping is preferable to freezing the last frame:
        # a held frame reads as a stall, a loop reads as a sustained move.
        pre_input = ["-stream_loop", "-1"]
        how = f"looped {actual:.2f}s -> {target:.2f}s"

    args = [
        ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error", "-nostdin",
        *pre_input, "-i", str(src),
        "-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate={AUDIO_RATE}",
        "-vf", vf,
        "-map", "0:v:0", "-map", "1:a:0",
        "-t", f"{target:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-ar", str(AUDIO_RATE), "-ac", str(AUDIO_CHANNELS),
        "-movflags", "+faststart",
        str(tmp),
    ]
    res = await run_proc(args, timeout=timeout)
    if not res.ok or not tmp.exists():
        raise MediaError(f"duration fit failed for {src.name}: {res.tail()}")
    os.replace(tmp, dest)
    return dest, how


async def fit_audio_duration(
    src: Path,
    dest: Path,
    *,
    target: float,
    timeout: float = 900.0,
) -> Path:
    """Pad with silence or trim so an audio file is exactly ``target`` seconds.

    Narration is padded to its scene's length so the voice track stays locked to
    picture across a three-hour cut instead of creeping earlier scene by scene.
    """
    target = max(0.1, float(target))
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp" + (dest.suffix or ".m4a"))
    args = [
        ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error", "-nostdin",
        "-i", str(src),
        "-af", f"apad,atrim=0:{target:.3f},aformat=sample_rates={AUDIO_RATE}:channel_layouts=stereo",
        "-t", f"{target:.3f}",
        *_audio_codec_args(dest, "160k"),
        str(tmp),
    ]
    res = await run_proc(args, timeout=timeout)
    if not res.ok or not tmp.exists():
        raise MediaError(f"audio fit failed for {src.name}: {res.tail()}")
    os.replace(tmp, dest)
    return dest


def batches(items: Sequence[Path], size: int = CONCAT_BATCH) -> List[List[Path]]:
    size = max(1, int(size))
    return [list(items[i : i + size]) for i in range(0, len(items), size)]


def format_hms(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(math.floor(seconds % 60))
    return f"{h:d}:{m:02d}:{s:02d}"


__all__ = [
    "AUDIO_CHANNELS",
    "AUDIO_RATE",
    "CONCAT_BATCH",
    "MediaError",
    "ProcResult",
    "TARGET_FPS",
    "TARGET_SIZE",
    "batches",
    "concat_audio",
    "concat_copy",
    "download",
    "ffmpeg_available",
    "ffmpeg_bin",
    "ffprobe_bin",
    "format_hms",
    "is_playable",
    "mix_final_audio",
    "normalize_clip",
    "pollinations_image_url",
    "probe_duration",
    "resolve_size",
    "run_proc",
    "streamelements_tts_url",
    "synthesize_kenburns_clip",
    "synthesize_music_bed",
    "write_concat_manifest",
]
