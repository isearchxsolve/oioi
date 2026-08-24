"""Self-check for the pipeline's external dependencies.

Run before trusting a long render:

    python -m studio_pipeline.selfcheck

Exercises every external edge the pipeline touches - OmniRoute chat, OmniRoute video,
keyless Pollinations stills, keyless TTS, and the full ffmpeg chain (Ken-Burns synthesis
-> duration probe -> music bed -> concat -> audio mix) - and prints a PASS/FAIL table.
Nothing here mutates a real run; artifacts go to ``storage/runs/_selfcheck``.
"""
from __future__ import annotations

import asyncio
import shutil
import sys
import time
from pathlib import Path
from typing import List, Tuple

from . import media
from .omniroute import OmniRouteClient
from .store import RunStore

Result = Tuple[str, bool, str]


def _fmt(results: List[Result]) -> str:
    width = max(len(name) for name, _, _ in results) + 2
    lines = []
    for name, ok, detail in results:
        mark = "PASS" if ok else "FAIL"
        lines.append(f"  [{mark}] {name.ljust(width)} {detail}")
    return "\n".join(lines)


async def run_selfcheck(*, keep: bool = False) -> List[Result]:
    results: List[Result] = []
    store = RunStore("_selfcheck")
    client = OmniRouteClient()

    # ---------------------------------------------------------------- toolchain
    if media.ffmpeg_available():
        res = await media.run_proc([media.ffmpeg_bin(), "-version"], timeout=30)
        version = res.stdout.splitlines()[0] if res.stdout else "unknown"
        results.append(("ffmpeg", res.ok, version[:80]))
    else:
        results.append(("ffmpeg", False, "not found on PATH (set FFMPEG_BIN)"))
        return results

    # ------------------------------------------------------------ omniroute llm
    started = time.time()
    chat = await client.probe_chat()
    results.append((
        "omniroute chat",
        bool(chat["available"]),
        f"{chat['latency_ms']:.0f}ms - {chat['detail']}",
    ))

    # -------------------------------------------------- omniroute json contract
    if chat["available"]:
        try:
            payload = await client.chat_json(
                [{
                    "role": "user",
                    "content": 'Return exactly this JSON and nothing else: {"ok": true, "n": 3}',
                }],
                temperature=0.0,
                max_tokens=200,
            )
            ok = isinstance(payload, dict) and payload.get("ok") is True
            results.append(("omniroute json mode", ok, f"parsed {payload!r}"[:90]))
        except Exception as exc:  # noqa: BLE001
            results.append(("omniroute json mode", False, f"{type(exc).__name__}: {exc}"[:120]))
    else:
        results.append(("omniroute json mode", False, "skipped - chat unavailable"))

    # ---------------------------------------------------------- omniroute video
    cap = await client.probe_video()
    results.append((
        "omniroute video",
        cap.available,
        (cap.route or "none") + " - " + cap.detail[:150],
    ))

    # --------------------------------------------------------- pollinations still
    still = store.still_path(1)
    url = media.pollinations_image_url(
        "a lone lighthouse on a black basalt cliff, storm light, cinematic wide shot",
        width=1280,
        height=720,
        seed=7,
    )
    try:
        await media.download(url, still, timeout=180.0)
        size_kb = still.stat().st_size / 1024
        results.append(("pollinations still", True, f"{size_kb:.0f} KB -> {still.name}"))
    except Exception as exc:  # noqa: BLE001
        results.append(("pollinations still", False, f"{type(exc).__name__}: {exc}"[:140]))
        return results

    # -------------------------------------------------------- ken-burns synthesis
    clips: List[Path] = []
    for scene_id, motion, dur in ((1, "slow push in", 6.0), (2, "pan right", 5.0)):
        dest = store.clip_path(scene_id)
        try:
            await media.synthesize_kenburns_clip(
                still, dest, duration=dur, width=1280, height=720, motion=motion
            )
            actual = await media.probe_duration(dest)
            ok = actual is not None and abs(actual - dur) < 1.5
            clips.append(dest)
            results.append((
                f"kenburns clip ({motion})",
                ok,
                f"asked {dur:g}s, got {actual:.2f}s, {dest.stat().st_size / 1024:.0f} KB"
                if actual else "no duration probed",
            ))
        except Exception as exc:  # noqa: BLE001
            results.append((f"kenburns clip ({motion})", False, f"{type(exc).__name__}: {exc}"[:140]))

    # -------------------------------------------------------------- narration TTS
    vo = store.narration_path(1)
    try:
        await media.download(
            media.streamelements_tts_url("The lighthouse held the last light on the coast."),
            vo,
            timeout=90.0,
        )
        vo_dur = await media.probe_duration(vo)
        results.append(("tts narration", vo_dur is not None, f"{vo_dur:.2f}s" if vo_dur else "unreadable"))
    except Exception as exc:  # noqa: BLE001
        results.append(("tts narration", False, f"{type(exc).__name__}: {exc}"[:140]))
        vo = None  # type: ignore[assignment]

    # ------------------------------------------------------------------ music bed
    music = store.audio_dir / "selfcheck_score.m4a"
    try:
        await media.synthesize_music_bed(music, duration=12.0, key_hz=110.0, bpm=84)
        m_dur = await media.probe_duration(music)
        results.append(("music bed", m_dur is not None and m_dur > 10, f"{m_dur:.2f}s" if m_dur else "unreadable"))
    except Exception as exc:  # noqa: BLE001
        results.append(("music bed", False, f"{type(exc).__name__}: {exc}"[:140]))
        music = None  # type: ignore[assignment]

    # ------------------------------------------------------------------- concat
    stitched = store.final_dir / "selfcheck_cut.mp4"
    if len(clips) >= 2:
        try:
            await media.concat_copy(clips, stitched, manifest=store.final_dir / "selfcheck_concat.txt")
            total = await media.probe_duration(stitched)
            expected = 11.0
            ok = total is not None and abs(total - expected) < 2.0
            results.append(("ffmpeg concat (copy)", ok, f"{total:.2f}s from {len(clips)} clips" if total else "unreadable"))
        except Exception as exc:  # noqa: BLE001
            results.append(("ffmpeg concat (copy)", False, f"{type(exc).__name__}: {exc}"[:140]))
    else:
        results.append(("ffmpeg concat (copy)", False, "skipped - fewer than 2 clips"))

    # ---------------------------------------------------------------- final mix
    if stitched.exists():
        mixed = store.final_dir / "selfcheck_mixed.mp4"
        try:
            await media.mix_final_audio(
                stitched,
                mixed,
                narration=vo if vo and vo.exists() else None,
                music=music if music and music.exists() else None,
            )
            mix_dur = await media.probe_duration(mixed)
            results.append(("final audio mix", mix_dur is not None, f"{mix_dur:.2f}s -> {mixed.name}" if mix_dur else "unreadable"))
        except Exception as exc:  # noqa: BLE001
            results.append(("final audio mix", False, f"{type(exc).__name__}: {exc}"[:140]))

    await client.aclose()
    if not keep:
        shutil.rmtree(store.dir, ignore_errors=True)
    else:
        print(f"\nArtifacts kept in: {store.dir}")
    return results


def main() -> int:
    keep = "--keep" in sys.argv
    results = asyncio.run(run_selfcheck(keep=keep))
    print("\nOiiOii pipeline self-check\n")
    print(_fmt(results))
    failed = [name for name, ok, _ in results if not ok]
    print()
    if failed:
        print(f"{len(failed)} check(s) failed: {', '.join(failed)}")
        # A missing video route is expected today and must not fail the toolchain gate.
        blocking = [f for f in failed if f not in {"omniroute video"}]
        return 1 if blocking else 0
    print("all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
