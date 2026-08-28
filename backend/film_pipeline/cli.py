"""Operator CLI.  Mock is the default; live video has two explicit safety gates."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import httpx

from .assembly import HttpClipMaterializer, KenBurnsFallbackMaterializer, SyntheticClipMaterializer, SyntheticFallbackClipMaterializer
from .clients import ChatPoolClient, VideoRouterClient
from .mock import DeterministicMockChatClient, MockSeat, MockVideoBackend, MockVideoConfig
from .orchestrator import FilmOrchestrator, FilmRequest
from .store import FilmJobStore


def _arguments() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Durable long-form film consumer")
    parser.add_argument("--script", help="Screenplay or generation brief")
    parser.add_argument("--script-file", help="UTF-8 screenplay file; avoids shell quoting limits for full scripts.")
    parser.add_argument("--target-seconds", type=int, default=180, help="Target runtime in seconds; production default is 180 (three minutes).")
    parser.add_argument("--aspect-ratio", default="16:9")
    parser.add_argument("--admission-mode", choices=("refuse", "waves"), default="refuse")
    parser.add_argument("--backend", choices=("mock", "fallback", "live"), default="mock")
    parser.add_argument(
        "--planner", choices=("mock", "pool"), default="mock",
        help="Use deterministic zero-network planning, or the live :8190 session-pool chat consumer.",
    )
    parser.add_argument("--live", action="store_true", help="Required with --backend live")
    parser.add_argument("--max-clips", type=int, default=0, help="Positive hard cap required in live mode")
    parser.add_argument(
        "--allow-slates", action="store_true",
        help="Explicitly approve finalization even when slate coverage exceeds the quality threshold.",
    )
    parser.add_argument(
        "--slate-fraction-limit", type=float, default=0.05,
        help="Block finalization above this logical-shot slate fraction unless --allow-slates is given (default: 0.05).",
    )
    parser.add_argument("--ticks", type=int, default=12, help="Bounded scheduler ticks to run after admission")
    parser.add_argument("--tick-sleep", type=float, default=0.0)
    parser.add_argument(
        "--plan-only", action="store_true",
        help="Persist and print the durable plan without making any video submission; useful for approving a live pool plan.",
    )
    parser.add_argument("--storage", default="./storage/film_pipeline")
    parser.add_argument(
        "--owner-id",
        help="Optional existing SaaS user ID. When supplied, the completed final is archived into the managed artifact database.",
    )
    parser.add_argument("--mock-capacity", type=int, default=4)
    parser.add_argument("--chat-base-url", default=os.getenv("FILM_PIPELINE_CONSUMER_BASE_URL", "http://127.0.0.1:8190"))
    parser.add_argument("--video-base-url", default=os.getenv("FILM_PIPELINE_CONSUMER_BASE_URL", "http://127.0.0.1:8190"))
    parser.add_argument(
        "--video-model", default=os.getenv("FILM_PIPELINE_VIDEO_MODEL", "video/auto"),
        help="Consumer video route: video/auto, or a pinned video/<host>/auto route.",
    )
    parser.add_argument(
        "--per-provider-cap", type=int, default=4,
        help="Concurrent dispatches per advertised video host (default: 4 seats).",
    )
    parser.add_argument("--per-seat-cap", type=int, default=1)
    parser.add_argument("--submit-concurrency", type=int, default=24, help="Maximum parallel live dispatches; bounded by max-clips.")
    parser.add_argument("--fallback-concurrency", type=int, default=4)
    parser.add_argument(
        "--still-request-gap", type=float, default=1.0,
        help="Minimum seconds between cold still-image requests; still fetches are always serialized.",
    )
    return parser


async def _run(args: argparse.Namespace) -> int:
    if bool(args.script) == bool(args.script_file):
        print("REFUSED: provide exactly one of --script or --script-file.", file=sys.stderr)
        return 2
    try:
        screenplay = Path(args.script_file).read_text(encoding="utf-8") if args.script_file else str(args.script)
    except OSError as exc:
        print(f"REFUSED: cannot read --script-file: {exc}", file=sys.stderr)
        return 2
    if args.backend == "live" and (not args.live or args.max_clips <= 0):
        print("REFUSED: live generation requires both --live and --max-clips N (N > 0).", file=sys.stderr)
        return 2
    root = Path(args.storage).resolve()
    store = FilmJobStore(root / "film_jobs.sqlite3")
    owned_mock_http = None
    if args.backend in {"mock", "fallback"}:
        # ``fallback`` deliberately exposes no router seats.  It is the fully local,
        # zero-credit delivery mode: deterministic planning + Pollinations stills +
        # FFmpeg Ken Burns + an AAC Sound Director score.
        fallback_only = args.backend == "fallback"
        backend = MockVideoBackend(MockVideoConfig(seats=[MockSeat("mock-seat-1", clips_remaining=args.mock_capacity)]))
        if fallback_only:
            backend = MockVideoBackend(MockVideoConfig(seats=[]))
        owned_mock_http = httpx.AsyncClient(transport=httpx.ASGITransport(app=backend.app), base_url="http://mock-video")
        chat = (
            ChatPoolClient(args.chat_base_url)
            if args.planner == "pool" else DeterministicMockChatClient()
        )
        video = VideoRouterClient(client=owned_mock_http)
        materializer = SyntheticClipMaterializer()
        fallback_materializer = (
            KenBurnsFallbackMaterializer(still_request_gap_seconds=args.still_request_gap)
            if fallback_only else SyntheticFallbackClipMaterializer()
        )
    else:
        # Live motion and live planning are independent controls. A strict pool
        # planning preflight can fail loudly without preventing an explicitly
        # authorized render from using the deterministic, provider-free planner.
        # Do not silently turn `--planner mock` into a consumer chat request.
        chat = ChatPoolClient(args.chat_base_url) if args.planner == "pool" else DeterministicMockChatClient()
        video = VideoRouterClient(
            args.video_base_url, video_model=args.video_model,
            mode="live", live=True, max_clips=args.max_clips,
        )
        materializer = HttpClipMaterializer()
        fallback_materializer = KenBurnsFallbackMaterializer(still_request_gap_seconds=args.still_request_gap)
    pipeline = FilmOrchestrator(
        store=store, chat=chat, video=video, artifact_root=root / "artifacts", materializer=materializer,
        fallback_materializer=fallback_materializer,
        segment_size=2 if args.backend == "mock" else 60,
        per_provider_cap=args.per_provider_cap,
        per_seat_cap=args.per_seat_cap,
        submit_concurrency=args.submit_concurrency,
        fallback_concurrency=args.fallback_concurrency,
        execution_backend="live" if args.backend == "live" else "mock",
        live=args.live, max_clips=args.max_clips if args.backend == "live" else None,
    )
    try:
        result = await pipeline.request_film(FilmRequest(
            script=screenplay, target_seconds=args.target_seconds, aspect_ratio=args.aspect_ratio,
            admission_mode=args.admission_mode,
            max_clips=args.max_clips if args.backend == "live" else None,
            allow_slates=args.allow_slates,
            slate_fraction_limit=args.slate_fraction_limit,
        ))
        if args.backend == "live":
            capacity = await video.capacity()
            provider = capacity.seats[0].provider if capacity.seats else "no provider available"
            cost = result["film"]["cost"]["projected_total"]
            # Required safety receipt, deliberately printed before the first scheduler tick/submit.
            print(f"LIVE PLAN: provider={provider}; clips={result.get('required_unique_clips', 0)}; projected_credits={cost}")
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        if not result.get("accepted", False):
            return 1
        if args.plan_only:
            return 0
        film_id = result["film"]["id"]
        if args.owner_id and not store.claim_film_owner(film_id, args.owner_id):
            print("REFUSED: durable film already belongs to a different SaaS user.", file=sys.stderr)
            return 2
        latest = await pipeline.run_until_idle(film_id, max_ticks=max(1, args.ticks), sleep_seconds=max(0.0, args.tick_sleep))
        print(json.dumps(latest, indent=2, ensure_ascii=False, default=str))
        return 0 if latest["film"]["status"] == "completed" else 1
    finally:
        await pipeline.aclose()


def main() -> int:
    return asyncio.run(_run(_arguments().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
