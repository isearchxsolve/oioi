"""Prove Flow end to end through TODAY's router, via the app's own HTTP endpoint.

SPENDS REAL CREDITS: one Flow clip, quoted at 20 from a balance of 930.

This deliberately goes through the FastAPI route rather than calling the adapter directly, so what
it proves is the whole chain the film app actually uses:

    POST /api/v1/videos/generations
      -> provider_service.init_registry()      (registers omniroute_video at priority 0)
      -> ProviderRegistry.get_adapter("video")  (must resolve to omniroute_video, not gemini)
      -> OmniRouteVideoAdapter.generate_video   (quote, ceiling check, ONE submit, no retry)
      -> video_router :8189 -> Google Flow      (real signed-in browser session)
      -> a real .mp4 on disk

No mock is registered, on purpose. Exactly one submit happens: the adapter quotes first and
never retries, so this cannot double-charge.
"""
import json
import logging
import os

logging.disable(logging.INFO)

PROMPT = (
    "a slow cinematic camera pan across rain-slicked neon rooftops at night, "
    "steam rising from vents, distant city lights flickering through the downpour"
)


def main() -> None:
    from fastapi.testclient import TestClient
    from app.main import app
    from providers.registry import reset_registry

    reset_registry()  # no mock: the real registry, the real provider
    client = TestClient(app)

    print("MARK before: checking who serves video and what it would cost (free)")
    r = client.get("/api/v1/videos/providers")
    for p in r.json().get("providers", []):
        print(f"MARK   {p['name']} priority={p.get('priority')} "
              f"reachable={p.get('reachable')} health={(p.get('health') or {}).get('status')}")

    print(f"MARK submitting ONE Flow clip -- this spends real credits")
    r = client.post("/api/v1/videos/generations", json={"prompt": PROMPT})
    print(f"MARK HTTP {r.status_code}")
    body = r.json()
    if r.status_code != 200:
        print("MARK FAILED: " + json.dumps(body)[:500])
        return

    print(f"MARK status          = {body.get('status')}")
    print(f"MARK provider        = {body.get('provider')}")
    print(f"MARK job_id          = {body.get('job_id')}")
    print(f"MARK credits_charged = {body.get('credits_charged')}")
    print(f"MARK video_url       = {body.get('video_url')}")
    path = body.get("local_path")
    print(f"MARK local_path      = {path}")
    if path and os.path.exists(path):
        print(f"MARK FILE EXISTS     = {os.path.getsize(path)} bytes")
    else:
        print("MARK FILE MISSING    <-- the clip was charged but no file landed")
    first = (body.get("data") or [{}])[0]
    print(f"MARK duration        = {first.get('duration')}  bytes={first.get('bytes')}")


if __name__ == "__main__":
    main()
