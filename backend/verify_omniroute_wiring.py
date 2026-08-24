"""Prove the video wiring end to end WITHOUT spending a credit.

Everything here is free: /healthz, /v1/models and /v1/videos/quote cost nothing. There is no
generate_video call in this file on purpose -- that is the one operation that spends real money.

Run:  python verify_omniroute_wiring.py
"""
import asyncio

from providers.base import VideoGenerationRequest


async def main() -> None:
    from app.core.config import settings
    from app.services.provider_service import init_registry
    from agent_pipeline import AnimationPipeline

    print("settings")
    print(f"  base_url            = {settings.OMNIROUTE_VIDEO_BASE_URL}")
    print(f"  default video model = {settings.DEFAULT_VIDEO_MODEL!r}  ('' = provider's choice)")
    print(f"  per-clip ceiling    = {settings.OMNIROUTE_VIDEO_MAX_CREDITS}")
    print(f"  per-run ceiling     = {settings.OMNIROUTE_VIDEO_MAX_CREDITS_PER_RUN}")
    print(f"  priority[0]         = {settings.PROVIDER_PRIORITY[0]}")

    registry = await init_registry()

    print("\nwho serves capability=video")
    adapter = await registry.get_adapter(capability="video")
    print(f"  registry.get_adapter('video')      -> {adapter.get_provider_name()}")

    pipeline = AnimationPipeline(registry=registry)
    padapter = await pipeline._get_video_adapter()
    print(f"  AnimationPipeline video adapter    -> {padapter.get_provider_name()}")

    print("\nrouter liveness (free)")
    print(f"  is_configured()  = {adapter.is_configured()}")
    health = await adapter.health_check()
    print(f"  health_check()   = {health.status} {health.latency_ms:.0f}ms err={health.error}")
    models = await adapter.list_models()
    print(f"  list_models()    = {len(models)} unique: {[m.id for m in models]}")

    print("\nquotes (free, nothing submitted)")
    scene = ("a slow camera pan across neon wet rooftops at night while heavy rain "
             "falls through the streetlight glow")
    for label, model in [("default ('')", settings.DEFAULT_VIDEO_MODEL or ""),
                         ("flow", "flow/veo-3.1-fast"),
                         ("rtst", "rtst/vidu")]:
        q = await adapter.quote(VideoGenerationRequest(prompt=scene, model=model))
        if q.get("error"):
            print(f"  {label:14s} ERROR {q['error'][:60]}")
        else:
            print(f"  {label:14s} provider={q.get('provider')} model={q.get('model')} "
                  f"cost={q.get('quote')} exact={q.get('exact')} balance={q.get('balance')}")

    print("\nrun-budget arithmetic (what an N-scene film would cost)")
    q = await adapter.quote(VideoGenerationRequest(prompt=scene, model=""))
    per_clip = q.get("quote") or 0
    budget = settings.OMNIROUTE_VIDEO_MAX_CREDITS_PER_RUN
    rendered = budget // per_clip if per_clip else 0
    print(f"  at {per_clip} credits/clip and a {budget}-credit run budget: "
          f"{rendered} scenes render, the rest report skipped=run_credit_budget_exhausted")

    print("\nthe short-prompt rule still refuses for free")
    q = await adapter.quote(VideoGenerationRequest(prompt="a cat", model="rtst/vidu"))
    print(f"  2-word prompt on rtst -> error={q.get('error')}")

    await adapter.aclose()
    print("\nNO CREDITS SPENT (no generate_video call in this file)")


if __name__ == "__main__":
    asyncio.run(main())
