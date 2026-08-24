"""Non-volatile RAM for the pipeline.

The mandate this module exists to satisfy: **a 3-hour film does not fit in a context
window, and it must not sit in process memory either.** Every artifact is written to
disk the moment it is produced, and every consumer reads it back lazily.

Layout of one run under ``<STORAGE>/runs/<run_id>/``::

    state.json            small manifest: stage, counters, approval decision, paths
    journal.jsonl         append-only event log — the source of truth for replay/resume
    WORKLOG.md            human-readable incremental log for this run
    bible.json            compact story bible (the ONLY thing re-sent to the LLM)
    script/act_001.json   one file per act: sequences + scene beats
    scenes/scene_00001.json  one file per scene: storyboard, prompts, timing
    characters/*.json     character sheets
    clips/scene_00001.mp4 one rendered clip per scene
    audio/*.mp3|wav       voiceover + music beds
    final/film.mp4        the stitched feature
    final/concat_*.txt    ffmpeg concat manifests (kept for forensics)

Nothing in this module is async: these are small, fast, local filesystem writes, and
keeping them synchronous means a crash can never interleave a half-written state file
with a journal append. Callers that care run them via ``asyncio.to_thread``.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional


def _backend_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def storage_root() -> Path:
    """Root for all generated media/state. Honours ``STORAGE_PATH`` like the app does."""
    env = os.getenv("STORAGE_PATH")
    root = Path(env) if env else _backend_dir() / "storage"
    return root.resolve()


def master_worklog_path() -> Path:
    """Location of the repo-level MASTER_WORKLOG.md.

    Defaults to the git-root copy (``<repo>/MASTER_WORKLOG.md``) so that every run in
    every working tree appends to a single recoverable log, as mandated.
    """
    env = os.getenv("MASTER_WORKLOG_PATH")
    if env:
        return Path(env).resolve()
    # backend/studio_pipeline/store.py -> backend -> oioi/oioi -> oioi (git root)
    return _backend_dir().parents[1] / "MASTER_WORKLOG.md"


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _atomic_write_text(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` atomically (tmp file + ``os.replace``).

    ``os.replace`` is atomic on NTFS for same-volume renames, so a reader either sees
    the whole previous file or the whole new one — never a truncated state.json.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class RunStore:
    """Durable, resumable state for a single production run."""

    def __init__(self, run_id: str, *, root: Optional[Path] = None) -> None:
        self.run_id = run_id
        base = Path(root).resolve() if root else storage_root()
        self.dir = base / "runs" / run_id
        self.script_dir = self.dir / "script"
        self.scenes_dir = self.dir / "scenes"
        self.characters_dir = self.dir / "characters"
        self.clips_dir = self.dir / "clips"
        self.audio_dir = self.dir / "audio"
        self.final_dir = self.dir / "final"
        for d in (
            self.dir,
            self.script_dir,
            self.scenes_dir,
            self.characters_dir,
            self.clips_dir,
            self.audio_dir,
            self.final_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)
        # Journal appends come from the event bus, which may be driven from worker
        # threads during ffmpeg stages; serialise them.
        self._journal_lock = threading.Lock()
        self._worklog_lock = threading.Lock()

    # ------------------------------------------------------------------ paths
    @property
    def state_path(self) -> Path:
        return self.dir / "state.json"

    @property
    def journal_path(self) -> Path:
        return self.dir / "journal.jsonl"

    @property
    def worklog_path(self) -> Path:
        return self.dir / "WORKLOG.md"

    @property
    def bible_path(self) -> Path:
        return self.dir / "bible.json"

    @property
    def final_film_path(self) -> Path:
        return self.final_dir / "film.mp4"

    def act_path(self, act_number: int) -> Path:
        return self.script_dir / f"act_{act_number:03d}.json"

    def scene_path(self, scene_id: int) -> Path:
        return self.scenes_dir / f"scene_{scene_id:05d}.json"

    def clip_path(self, scene_id: int) -> Path:
        return self.clips_dir / f"scene_{scene_id:05d}.mp4"

    def still_path(self, scene_id: int) -> Path:
        return self.clips_dir / f"scene_{scene_id:05d}.jpg"

    def narration_path(self, scene_id: int) -> Path:
        return self.audio_dir / f"vo_{scene_id:05d}.mp3"

    def character_path(self, slug: str) -> Path:
        safe = "".join(c if (c.isalnum() or c in "-_") else "_" for c in slug)[:64] or "character"
        return self.characters_dir / f"{safe}.json"

    def media_url(self, path: Path) -> str:
        """Map an on-disk artifact to the URL served by the app's ``/runs`` mount.

        ``main.py`` mounts ``<STORAGE_PATH>/runs`` at ``/runs``, so a clip at
        ``storage/runs/<id>/clips/scene_00001.mp4`` is reachable at
        ``/runs/<id>/clips/scene_00001.mp4``. Falls back to a ``file://`` URI for
        artifacts written outside the storage root (tests, custom roots).
        """
        try:
            rel = path.resolve().relative_to(self.dir.parent)
        except (ValueError, OSError):
            return path.resolve().as_uri()
        return "/runs/" + rel.as_posix()

    # ------------------------------------------------------------------ state
    def save_state(self, state: Dict[str, Any]) -> None:
        state = dict(state)
        state["updated_at"] = _utc_iso()
        _atomic_write_text(self.state_path, json.dumps(state, indent=2, ensure_ascii=False, default=str))

    def load_state(self) -> Optional[Dict[str, Any]]:
        if not self.state_path.exists():
            return None
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def patch_state(self, **changes: Any) -> Dict[str, Any]:
        state = self.load_state() or {"run_id": self.run_id}
        state.update(changes)
        self.save_state(state)
        return state

    # ---------------------------------------------------------------- journal
    def journal_append(self, event_dict: Dict[str, Any]) -> None:
        line = json.dumps(event_dict, ensure_ascii=False, default=str)
        with self._journal_lock:
            self.journal_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.journal_path, "a", encoding="utf-8", newline="\n") as fh:
                fh.write(line + "\n")
                fh.flush()
                os.fsync(fh.fileno())

    def journal_read(self, *, after_seq: int = 0) -> List[Dict[str, Any]]:
        """All journalled events with ``seq > after_seq``.

        A crash mid-append can leave one torn trailing line; it is skipped rather than
        failing the whole replay.
        """
        if not self.journal_path.exists():
            return []
        out: List[Dict[str, Any]] = []
        with open(self.journal_path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if int(rec.get("seq", 0)) > after_seq:
                    out.append(rec)
        return out

    def journal_last_seq(self) -> int:
        seq = 0
        for rec in self.journal_read():
            seq = max(seq, int(rec.get("seq", 0)))
        return seq

    # ----------------------------------------------------------------- worklog
    def worklog(
        self,
        stage: str,
        status: str,
        *,
        facts: Optional[List[str]] = None,
        next_action: str = "",
        files: Optional[List[str]] = None,
        mirror_master: bool = True,
    ) -> None:
        """Append one entry to the run worklog and (by default) MASTER_WORKLOG.md.

        Written synchronously and flushed on every call — never batched — so a crash
        leaves the log pointing at the exact stage that was in flight.
        """
        lines = [
            "",
            f"## [{_utc_iso()}] {stage}",
            f"STATUS: {status}",
        ]
        if files:
            lines.append("FILES: " + ", ".join(files))
        for fact in facts or []:
            lines.append(f"- {fact}")
        if next_action:
            lines.append(f"NEXT: {next_action}")
        run_entry = "\n".join(lines) + "\n"
        # The master log interleaves many runs, so its heading carries the run id.
        master_entry = run_entry.replace(f"] {stage}", f"] [{self.run_id}] {stage}", 1)

        targets = [(self.worklog_path, run_entry)]
        if mirror_master:
            targets.append((master_worklog_path(), master_entry))

        with self._worklog_lock:
            for target, text in targets:
                try:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with open(target, "a", encoding="utf-8", newline="\n") as fh:
                        fh.write(text)
                        fh.flush()
                        os.fsync(fh.fileno())
                except OSError:
                    # A read-only or missing master log must not abort a render.
                    continue

    # ------------------------------------------------------------------- bible
    def save_bible(self, bible: Dict[str, Any]) -> None:
        _atomic_write_text(self.bible_path, json.dumps(bible, indent=2, ensure_ascii=False))

    def load_bible(self) -> Dict[str, Any]:
        if not self.bible_path.exists():
            return {}
        try:
            return json.loads(self.bible_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    # -------------------------------------------------------------------- acts
    def save_act(self, act_number: int, act: Dict[str, Any]) -> Path:
        p = self.act_path(act_number)
        _atomic_write_text(p, json.dumps(act, indent=2, ensure_ascii=False))
        return p

    def load_act(self, act_number: int) -> Optional[Dict[str, Any]]:
        p = self.act_path(act_number)
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def act_numbers(self) -> List[int]:
        out = []
        for p in sorted(self.script_dir.glob("act_*.json")):
            try:
                out.append(int(p.stem.split("_")[1]))
            except (IndexError, ValueError):
                continue
        return out

    def iter_acts(self) -> Iterator[Dict[str, Any]]:
        for n in self.act_numbers():
            act = self.load_act(n)
            if act is not None:
                yield act

    # ------------------------------------------------------------------ scenes
    def save_scene(self, scene: Dict[str, Any]) -> Path:
        scene_id = int(scene["id"])
        p = self.scene_path(scene_id)
        _atomic_write_text(p, json.dumps(scene, indent=2, ensure_ascii=False))
        return p

    def load_scene(self, scene_id: int) -> Optional[Dict[str, Any]]:
        p = self.scene_path(scene_id)
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def scene_ids(self) -> List[int]:
        out = []
        for p in sorted(self.scenes_dir.glob("scene_*.json")):
            try:
                out.append(int(p.stem.split("_")[1]))
            except (IndexError, ValueError):
                continue
        return sorted(out)

    def iter_scenes(self) -> Iterator[Dict[str, Any]]:
        """Lazily stream scenes off disk.

        This is the context-window guard for the Animator: a 3-hour film is ~500-1000
        scenes, and it walks them one at a time instead of materialising a list.
        """
        for sid in self.scene_ids():
            scene = self.load_scene(sid)
            if scene is not None:
                yield scene

    def scene_count(self) -> int:
        return len(self.scene_ids())

    # ------------------------------------------------------------------- clips
    def has_clip(self, scene_id: int) -> bool:
        p = self.clip_path(scene_id)
        try:
            return p.exists() and p.stat().st_size > 1024
        except OSError:
            return False

    def clip_paths(self) -> List[Path]:
        return sorted(self.clips_dir.glob("scene_*.mp4"))

    # -------------------------------------------------------------- lifecycle
    def destroy(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)


def list_run_ids(*, root: Optional[Path] = None) -> List[str]:
    """Run ids present on disk, newest first — used to resume after a restart."""
    base = (Path(root).resolve() if root else storage_root()) / "runs"
    if not base.is_dir():
        return []
    entries = [p for p in base.iterdir() if p.is_dir()]
    entries.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0.0, reverse=True)
    return [p.name for p in entries]


def new_run_id(*, seed: Optional[str] = None) -> str:
    """Sortable, filesystem-safe run id: ``run_<utc-compact>_<suffix>``."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    suffix = (seed or os.urandom(3).hex())[:8]
    safe = "".join(c if (c.isalnum() or c in "-_") else "" for c in suffix) or "run"
    return f"run_{stamp}_{safe}"


__all__ = [
    "RunStore",
    "list_run_ids",
    "master_worklog_path",
    "new_run_id",
    "storage_root",
]
