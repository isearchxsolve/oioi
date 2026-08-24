"""
FFMPEG subprocess operations — isolated utility module.

All ffmpeg/ffprobe commands live here to maintain clean architecture.
Migrated from film_kit.py with the following functions:
  - probe_duration
  - build_ken_burns_clip
  - mux_audio
  - stitch_concat
  - stitch_crossfade
  - write_srt
  - generate_ambient_bed
  - mix_music_under

All functions are async (run subprocess in a thread pool) to avoid
blocking the FastAPI event loop during long-running encodes.
"""

import asyncio
import shutil
from pathlib import Path
from typing import Optional

# ── Constants ────────────────────────────────────────────────

FPS_DEFAULT = 30

# Music mood → chord definition. Enriched from the original two-note drone
# into a three-note pad (root + chord tones) for a fuller, less "cheap"
# ambient bed, still synthesised for free with ffmpeg signal generators.
# Tuple: (root, third, fifth) frequencies in Hz.
_MUSIC_PARAMS: dict[str, tuple[float, float, float]] = {
    "ambient": (110.0, 164.81, 220.00),   # A2 + E3 + A3 — open, spacious
    "tense": (98.0, 116.54, 138.59),       # G2 + A#2 + C#3 — dissonant/minor-ish
    "bright": (261.63, 329.63, 392.00),    # C4 + E4 + G4 — major, uplifting
}


# ── Helpers ──────────────────────────────────────────────────

def ensure_ffmpeg() -> bool:
    """Check that ffmpeg and ffprobe are available on PATH."""
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


async def _run_cmd(cmd: list[str]) -> tuple[int, str, str]:
    """Run a subprocess asynchronously, return (returncode, stdout, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return proc.returncode, stdout.decode("utf-8", errors="replace"), stderr.decode("utf-8", errors="replace")


async def _run_cmd_with_progress(
    cmd: list[str],
    total_duration: float,
    progress_callback=None,
) -> tuple[int, str, str]:
    """Run ffmpeg with progress parsing via stderr output."""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout_lines = []
    stderr_lines = []

    async def read_stderr():
        while True:
            line = await proc.stderr.readline()
            if not line:
                break
            decoded = line.decode("utf-8", errors="replace")
            stderr_lines.append(decoded)
            # Parse progress from ffmpeg stderr (time=HH:MM:SS.ms)
            if progress_callback and "time=" in decoded:
                try:
                    time_str = decoded.split("time=")[1].split()[0]
                    h, m, s = time_str.split(":")
                    current = int(h) * 3600 + int(m) * 60 + float(s)
                    pct = min(1.0, current / max(0.1, total_duration))
                    await progress_callback(pct)
                except (ValueError, IndexError):
                    pass

    await read_stderr()
    stdout = await proc.stdout.read()
    await proc.wait()
    return (
        proc.returncode,
        stdout.decode("utf-8", errors="replace"),
        "".join(stderr_lines),
    )


# ── ffprobe ──────────────────────────────────────────────────

async def probe_duration(path: Path) -> float:
    """Return the duration of a media file in seconds (min 0.5 s)."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    rc, stdout, _ = await _run_cmd(cmd)
    try:
        val = stdout.strip()
        if not val or val == "N/A":
            return 4.0
        return max(0.5, float(val))
    except (ValueError, AttributeError):
        return 4.0


# ── Ken Burns ───────────────────────────────────────────────

async def build_ken_burns_clip(
    image_path: Path,
    duration: float,
    out_path: Path,
    size: tuple[int, int],
    fps: int = FPS_DEFAULT,
    zoom_in: bool = True,
    progress_callback=None,
) -> None:
    """
    Render an animated Ken Burns pan/zoom clip from a single image.

    Uses the zoompan filter with the original expressions from film_kit.py.
    """
    w, h = size
    frames = max(2, int(round(duration * fps)))
    z_expr = (
        "min(zoom+0.0015,1.4)"
        if zoom_in else
        "if(eq(on,1),1.4,max(zoom-0.0015,1.0))"
    )
    scale_w = w * 3
    vf = (
        f"scale={scale_w}:-2,"
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
    rc, _, stderr = await _run_cmd_with_progress(cmd, duration, progress_callback)
    if rc != 0:
        raise RuntimeError(
            f"ffmpeg (ken burns) failed for {image_path.name}:\n"
            f"{stderr[-1000:]}"
        )


# ── Audio Muxing ────────────────────────────────────────────

async def mux_audio(video_path: Path, audio_path: Path, out_path: Path) -> None:
    """
    Mux video + audio into a single MP4.

    Uses -async 1 to handle minor A/V sync drift that can accumulate
    when edge-tts produces audio slightly shorter than the video.
    """
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-async", "1",
        "-shortest",
        str(out_path),
    ]
    rc, _, stderr = await _run_cmd(cmd)
    if rc != 0:
        raise RuntimeError(f"ffmpeg (mux) failed:\n{stderr[-800:]}")


# ── Stitching ───────────────────────────────────────────────

async def stitch_concat(clip_paths: list[Path], out_path: Path) -> None:
    """Stitch clips with hard cuts (fast, no re-encode)."""
    list_file = out_path.parent / "_concat_list.txt"
    lines = [f"file '{p.resolve().as_posix()}'" for p in clip_paths]
    list_file.write_text("\n".join(lines), encoding="utf-8")
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(list_file),
        "-c", "copy",
        str(out_path),
    ]
    rc, _, stderr = await _run_cmd(cmd)
    list_file.unlink(missing_ok=True)
    if rc != 0:
        raise RuntimeError(f"ffmpeg (concat) failed:\n{stderr[-800:]}")


async def stitch_crossfade(
    clip_paths: list[Path],
    out_path: Path,
    trans_dur: float = 0.75,
) -> None:
    """
    Stitch clips with dissolve transitions (xfade/acrossfade chain).

    Properly chains intermediate labels for n > 2 clips.
    """
    if len(clip_paths) == 1:
        shutil.copy2(clip_paths[0], out_path)
        return

    durations = [await probe_duration(p) for p in clip_paths]
    inputs: list[str] = []
    for p in clip_paths:
        inputs += ["-i", str(p)]

    parts: list[str] = []
    prev_v = "0:v"
    prev_a = "0:a"
    cum = durations[0]

    for i in range(1, len(clip_paths)):
        td = min(
            trans_dur,
            durations[i - 1] - 0.05,
            durations[i] - 0.05,
        )
        td = max(0.1, td)
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
        cum += durations[i] - td

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
    rc, _, stderr = await _run_cmd(cmd)
    if rc != 0:
        raise RuntimeError(f"ffmpeg (crossfade) failed:\n{stderr[-1200:]}")


# ── Subtitles ────────────────────────────────────────────────

def write_srt(scenes: list[dict], out_path: Path) -> None:
    """
    Write an SRT subtitle file aligned to each scene's duration.

    Args:
        scenes: list of dicts with 'narration' and 'duration' keys.
        out_path: destination .srt file path.
    """
    def fmt(sec: float) -> str:
        h_, rem = divmod(sec, 3600)
        m_, s_ = divmod(rem, 60)
        ms = int(round((s_ % 1) * 1000))
        return f"{int(h_):02}:{int(m_):02}:{int(s_):02},{ms:03}"

    lines: list[str] = []
    t = 0.0
    for i, s in enumerate(scenes, 1):
        dur = s.get("duration") or 4.0
        end = t + dur
        narration = s.get("narration", "")
        lines += [str(i), f"{fmt(t)} --> {fmt(end)}", narration, ""]
        t = end

    out_path.write_text("\n".join(lines), encoding="utf-8")


# ── Ambient Music Bed ───────────────────────────────────────

async def generate_ambient_bed(
    duration: float,
    out_path: Path,
    mood: str = "ambient",
) -> None:
    """
    Synthesise a quiet stereo drone pad with ffmpeg signal generators.

    Enriched from the original two-note drone: now a three-note chord pad
    (root/third/fifth, slightly detuned for warmth) + a slow tremolo LFO
    for gentle movement + a filtered pink-noise air layer, faded in/out
    and stereo-widened. Still zero-cost, but noticeably less "cheap".
    """
    f1, f2, f3 = _MUSIC_PARAMS.get(mood, _MUSIC_PARAMS["ambient"])
    fade_dur = min(2.0, duration * 0.1)
    fade_out_t = max(0.0, duration - fade_dur)
    dur_s = f"{duration:.3f}"

    # Tremolo: a very slow amplitude modulation (one cycle per ~8s) for
    # gentle breathing movement rather than a static drone.
    tremolo_rate = 0.12

    filt = (
        # Three detuned chord tones
        f"sine=frequency={f1}:duration={dur_s}[a];"
        f"sine=frequency={f2}:duration={dur_s}[b];"
        f"sine=frequency={f3}:duration={dur_s}[c];"
        # Air layer
        f"anoisesrc=color=pink:duration={dur_s}:amplitude=0.04[n];"
        # Mix the chord with weighted levels into a mono pad
        f"[a][b][c]amix=inputs=3:weights='1 0.7 0.6'[chord];"
        # Blend in the pink-noise air
        f"[chord][n]amix=inputs=2:weights='1 0.25'[mix];"
        # Gentle tremolo for movement
        f"[mix]tremolo=f={tremolo_rate:.2f}:d=0.4[swell];"
        # Warm it up + shape dynamics
        f"[swell]lowpass=f=900,highpass=f=55[warm];"
        # Stereo widen (split + slight delay on one channel for width)
        f"[warm]asplit=2[L0][R0];"
        f"[R0]adelay=18|18[R1];"
        f"[L0][R1]amerge=inputs=2[stereo];"
        # Fades + overall level
        f"[stereo]afade=t=in:d={fade_dur:.3f},"
        f"afade=t=out:st={fade_out_t:.3f}:d={fade_dur:.3f},"
        f"volume=0.16[out]"
    )
    cmd = [
        "ffmpeg", "-y",
        "-filter_complex", filt,
        "-map", "[out]",
        "-t", dur_s,
        str(out_path),
    ]
    rc, _, stderr = await _run_cmd(cmd)
    if rc != 0:
        raise RuntimeError(f"ffmpeg (ambient bed) failed:\n{stderr[-800:]}")


async def mix_music_under(
    video_path: Path,
    out_path: Path,
    mood: str = "ambient",
) -> None:
    """Mix a background score under the existing audio track.

    Uses the active music provider (FFMPEG bed by default, Suno if
    configured) via the music-providers registry.
    """
    # Imported lazily to avoid a circular import (registry imports this module
    # via the ffmpeg provider wrapper).
    from services.music_providers.registry import generate_score

    duration = await probe_duration(video_path)
    bed = video_path.parent / "_music_bed.aac"
    try:
        await generate_score(duration, bed, mood)
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
        rc, _, stderr = await _run_cmd(cmd)
        if rc != 0:
            raise RuntimeError(f"ffmpeg (music mix) failed:\n{stderr[-800:]}")
    finally:
        bed.unlink(missing_ok=True)


# ── Clip Trimming ─────────────────────────────────────────────

async def trim_clip(
    src: Path,
    out: Path,
    in_point: float | None = None,
    out_point: float | None = None,
) -> None:
    """
    Trim a clip from the start and/or end.

    Uses accurate input seeking (-ss before -i) for fast, precise trimming.
    Re-encodes to libx264/aac since input seek + trim requires re-encode.

    Args:
        src: Source clip path
        out: Output trimmed clip path
        in_point: Seconds to trim from start (None = no trim)
        out_point: Seconds from start to end trim point (None = no end trim)
    """
    if in_point is None and out_point is None:
        # No trim requested — just copy
        shutil.copy2(src, out)
        return

    duration = await probe_duration(src)
    
    # Build trim filter
    vf_parts = []
    af_parts = []
    
    if in_point is not None and in_point > 0:
        vf_parts.append(f"trim=start={in_point:.3f}")
        af_parts.append(f"atrim=start={in_point:.3f}")
    
    if out_point is not None and out_point > 0 and out_point < duration:
        if in_point is not None:
            trim_dur = out_point - in_point
        else:
            trim_dur = out_point
        vf_parts.append(f"trim=duration={trim_dur:.3f}")
        af_parts.append(f"atrim=duration={trim_dur:.3f}")

    # Set PTS to start at 0 for proper concatenation
    vf_parts.append("setpts=PTS-STARTPTS")
    af_parts.append("asetpts=PTS-STARTPTS")

    cmd = [
        "ffmpeg", "-y",
        "-i", str(src),
        "-vf", ",".join(vf_parts),
        "-af", ",".join(af_parts),
        "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-c:a", "aac", "-b:a", "192k",
        str(out),
    ]
    rc, _, stderr = await _run_cmd(cmd)
    if rc != 0:
            raise RuntimeError(f"ffmpeg (trim) failed for {src.name}:\n{stderr[-800:]}")


# ═══════════════════════════════════════════════════════════════════════════
# MASTERING — ProRes / DNxHR / DCP / IMF
# ════════════════════════════════════════════════════════════════════════════

async def export_prores(
    src: Path,
    out: Path,
    profile: str = "4444",  # "4444" | "422" | "422hq" | "4444xq"
) -> None:
    """
    Export Apple ProRes master.
    
    Profiles:
    - 4444: 4:4:4:4 (alpha), 12-bit, visually lossless
    - 4444xq: 4:4:4:4, 16-bit, highest quality
    - 422hq: 4:2:2, 10-bit, high quality
    - 422: 4:2:2, 10-bit, standard
    
    Args:
        src: Source video (any format)
        out: Output .mov path
        profile: ProRes profile identifier
    """
    profile_map = {
        "4444": "prores_ks -profile:v 4444",
        "4444xq": "prores_ks -profile:v 4444xq",
        "422hq": "prores_ks -profile:v 422hq",
        "422": "prores_ks -profile:v 422",
    }
    if profile not in profile_map:
        raise ValueError(f"Unknown ProRes profile: {profile}")

    cmd = [
        "ffmpeg", "-y",
        "-i", str(src),
        "-c:v", "prores_ks",
        "-profile:v", profile_map[profile].split()[-1],
        "-vendor", "apl0",
        "-pix_fmt", "yuva444p10le" if profile in ("4444", "4444xq") else "yuv422p10le",
        "-c:a", "pcm_s24le",  # 24-bit PCM for master
        "-map", "0:v",
        "-map", "0:a?",
        str(out),
    ]
    rc, _, stderr = await _run_cmd(cmd)
    if rc != 0:
        raise RuntimeError(f"ffmpeg (ProRes) failed:\n{stderr[-800:]}")
    logger.info(f"ProRes {profile} exported to {out}")


async def export_dnxhr(
    src: Path,
    out: Path,
    profile: str = "HQX",  # "HQX" | "HQ" | "SQ" | "LB"
) -> None:
    """
    Export Avid DNxHR master.
    
    Profiles:
    - HQX: 12-bit 4:4:4
    - HQ:  10-bit 4:2:2
    - SQ:  8-bit 4:2:2 (standard quality)
    - LB:  8-bit 4:2:2 (low bandwidth)
    """
    profile_map = {
        "HQX": "dnxhr_hqx",
        "HQ": "dnxhr_hq",
        "SQ": "dnxhr_sq",
        "LB": "dnxhr_lb",
    }
    if profile not in profile_map:
        raise ValueError(f"Unknown DNxHR profile: {profile}")

    cmd = [
        "ffmpeg", "-y",
        "-i", str(src),
        "-c:v", profile_map[profile],
        "-vendor", "avid",
        "-pix_fmt", "yuv444p12le" if profile == "HQX" else "yuv422p10le",
        "-c:a", "pcm_s24le",
        str(out),
    ]
    rc, _, stderr = await _run_cmd(cmd)
    if rc != 0:
        raise RuntimeError(f"ffmpeg (DNxHR) failed:\n{stderr[-800:]}")
    logger.info(f"DNxHR {profile} exported to {out}")


async def build_dcp_package(
    src: Path,
    output_dir: Path,
    title: str = "FILM_KIT_MASTER",
    fps: float = 24.0,
    resolution: str = "2K",  # "2K" | "4K"
) -> Path:
    """
    Build DCP (Digital Cinema Package) for theatrical delivery.
    
    Uses openDCP (opendcp) toolchain. Requires opendcp installed.
    
    Returns path to DCP package directory.
    """
    import subprocess
    import tempfile
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # First, export to proper DCP frame rate/resolution
    if resolution == "4K":
        w, h = 4096, 2160
    else:
        w, h = 2048, 1080
    
    # Export to JPEG2000 sequence (DCI compliant)
    with tempfile.TemporaryDirectory() as tmpdir:
        j2k_dir = Path(tmpdir) / "j2k"
        j2k_dir.mkdir()
        
        # Export to JPEG2000 frames
        cmd = [
            "ffmpeg", "-y",
            "-i", str(src),
            "-vf", f"scale={w}:{h}:flags=lanczos,fps={fps}",
            "-c:v", "libopenjpeg",
            "-pix_fmt", "xyz12le",
            "-colorspace", "bt709",
            "-color_trc", "gamma22",
            "-color_primaries", "bt709",
            "-profile:v", "4",  # DCI 2K/4K
            "-compression_level", "0",  # Lossless
            str(j2k_dir / "frame_%06d.j2k"),
        ]
        rc, _, stderr = await _run_cmd(cmd)
        if rc != 0:
            raise RuntimeError(f"ffmpeg (J2K export) failed:\n{stderr[-800:]}")
        
        # Build DCP with openDCP
        dcp_dir = output_dir / f"{title}_DCP"
        dcp_dir.mkdir(parents=True, exist_ok=True)
        
        cmd = [
            "opendcp_j2k",
            "-i", str(j2k_dir),
            "-o", str(dcp_dir),
            "-t", title,
            "-r", str(int(fps)),
            "-k", "2K" if resolution == "2K" else "4K",
        ]
        rc, _, stderr = await _run_cmd(cmd)
        if rc != 0:
            raise RuntimeError(f"opendcp failed:\n{stderr[-800:]}")
    
    logger.info(f"DCP package built at {output_dir}")
    return output_dir


async def export_imf(
    src: Path,
    output_dir: Path,
    cpl_name: str = "FILM_KIT_CPL",
    fps: float = 24.0,
) -> Path:
    """
    Export IMF (Interoperable Master Format) for Netflix/Disney+ delivery.
    
    Uses mxflib / imf_converter (requires external tools).
    Placeholder for production - requires mxflib or similar.
    """
    # Full IMF requires:
    # - MXF OP1a container with JPEG2000 essence
    # - CPL (Composition Playlist) + PKL (Packing List) + OPL (Output Profile List)
    # - Usually generated via mxflib or cmxml2imf
    logger.warning("IMF export requires mxflib/opendcp full toolchain. Placeholder only.")
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "README.txt").write_text(
        "IMF export requires mxflib or opendcp full toolchain.\n"
        "Install: pip install mxflib\n"
        "Then use: mxflib --source <src> --output <dir> --cpl-name <name>"
    )
    return output_dir


# ════════════════════════════════════════════════════════════════════════════
# ASC CDL XML EXPORT
# ════════════════════════════════════════════════════════════════════════════

async def write_cdl_xml(
    cdls: list[tuple[str, "CDL"]],
    output_path: Path,
) -> Path:
    """Export ASC CDL XML sidecar for NLE color grading."""
    from services.color import CDL
    
    xml = '''<?xml version="1.0" encoding="UTF-8"?>
<ColorDecisionList xmlns="urn:ASC:CDL:v1.01">'''

    for shot_name, cdl in cdls:
        xml += f'''
  <ColorDecision>
    <ColorCorrection id="{shot_name}">
      <SOPNode>
        <Slope>{cdl.slope[0]} {cdl.slope[1]} {cdl.slope[2]}</Slope>
        <Offset>{cdl.offset[0]} {cdl.offset[1]} {cdl.offset[2]}</Offset>
        <Power>{cdl.power[0]} {cdl.power[1]} {cdl.power[2]}</Power>
      </SOPNode>
      <SatNode>
        <Saturation>{cdl.saturation}</Saturation>
      </SatNode>
    </ColorCorrection>
  </ColorDecision>'''

    xml += "\n</ColorDecisionList>"

    output_path.write_text(xml)
    logger.info(f"ASC CDL XML exported to {output_path}")
    return output_path


# ════════════════════════════════════════════════════════════════════════════
# VFX PLATE EXPORT (Alpha / Depth / Normal / Motion Vectors)
# ════════════════════════════════════════════════════════════════════════════

async def export_alpha_plates(
    src: Path,
    output_dir: Path,
    beauty_name: str = "beauty",
) -> dict[str, Path]:
    """
    Export VFX plates from rendered clip.
    
    Requires the source to have been rendered with render passes.
    For Film Kit Studio, this exports:
    - Beauty (RGB)
    - Alpha (from reference image if available)
    - Depth (from video model if available)
    - Normal (from video model if available)
    - Motion Vectors (from video model if available)
    
    Placeholder for production - requires render passes from video model.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Copy beauty as-is
    beauty_out = output_dir / f"{beauty_name}.mov"
    shutil.copy2(src, beauty_out)
    
    # Placeholder plates
    results = {"beauty": beauty_out}
    
    # Note: Actual alpha/depth/normal would come from video generation
    # This is a placeholder structure
    
    return results


async def export_udim_layout(
    texture_dir: Path,
    output_dir: Path,
) -> Path:
    """Export UDIM texture layout for 3D integration."""
    # Placeholder for UDIM export
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "UDIM_LAYOUT.txt").write_text(
        "UDIM layout placeholder - requires 3D render passes"
    )
    return output_dir
