import os
from functools import lru_cache
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # App
    APP_NAME: str = "Film Kit Studio"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    APP_ENV: str = os.getenv("APP_ENV", "development")
    API_V1_PREFIX: str = "/api/v1"
    # The original demo routes submit directly to legacy providers and are not part
    # of the durable FilmJobStore safety model. They stay retired unless a local
    # developer deliberately enables mock/demo compatibility.
    ENABLE_LEGACY_DEMO_ROUTES: bool = os.getenv("ENABLE_LEGACY_DEMO_ROUTES", "false").lower() == "true"
    # A product server must never enumerate a sibling provider/router's filesystem.
    # Local app-owned media remains available through its own controlled routes.
    ENABLE_LEGACY_HARVEST_ASSETS: bool = os.getenv("ENABLE_LEGACY_HARVEST_ASSETS", "false").lower() == "true"
    
    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    JWT_SECRET_KEY: str = "default_secret"
    JWT_SECRET: str = "default_secret"

    # Closed SaaS access model.  OiiOii has no public registration flow: the
    # operator creates each paid customer's credentials.  The initial owner is
    # bootstrapped once from environment variables and is deliberately the only
    # account that can administer users.
    CLOSED_SAAS_MODE: bool = os.getenv("OIOI_CLOSED_SAAS_MODE", "true").lower() == "true"
    OWNER_EMAIL: str = os.getenv("OIOI_OWNER_EMAIL", "").strip().lower()
    OWNER_INITIAL_PASSWORD: str = os.getenv("OIOI_OWNER_INITIAL_PASSWORD", "")
    AUTH_SESSION_TTL_HOURS: int = int(os.getenv("OIOI_AUTH_SESSION_TTL_HOURS", "168"))
    # Final deliverables are compressed then retained as database BLOBs. Intermediate
    # clips remain short-lived FFmpeg work files and are removed after commit.
    FILM_ARTIFACT_QUOTA_BYTES: int = int(os.getenv("FILM_ARTIFACT_QUOTA_BYTES", str(10 * 1024 * 1024 * 1024)))
    
    # CORS
    # The UI runs on :3011 (see .claude/launch.json and the dev script), which was NOT in this list
    # -- only :3000 and :5173 were. Requests are normally same-origin through the Next rewrite so it
    # never showed, but MEASURED 2026-08-24: a stale cached 308 in the browser sent the Library,
    # Models, Styles and Projects fetches cross-origin to :8010 and every one died with
    # "No 'Access-Control-Allow-Origin' header is present", which the UI reported as "HTTP 500".
    # Listing the real dev origins means that failure mode degrades to "works" instead of a dead tab.
    CORS_ORIGINS: list[str] = [
        "http://localhost:3011", "http://127.0.0.1:3011",
        "http://localhost:3000", "http://127.0.0.1:3000",
        "http://localhost:5173",
    ]
    
    # OpenRouter (free-tier LLM/image/video — NVIDIA NIM is a TOTAL NO-GO)
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_API_BASE_URL: str = "https://openrouter.ai/api/v1"

    # Groq (free-tier LLM)
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_API_BASE_URL: str = "https://api.groq.com/openai/v1"

    # Cerebras (free-tier LLM, ultra-fast inference)
    CEREBRAS_API_KEY: str = os.getenv("CEREBRAS_API_KEY", "")
    CEREBRAS_API_BASE_URL: str = "https://api.cerebras.ai/v1"

    # Cohere (free-tier LLM + embeddings)
    COHERE_API_KEY: str = os.getenv("COHERE_API_KEY", "")
    COHERE_API_BASE_URL: str = "https://api.cohere.ai/v1"

    # Cloudflare Workers AI (free-tier LLM/image/embeddings)
    CLOUDFLARE_API_KEY: str = os.getenv("CLOUDFLARE_API_KEY", "")
    CLOUDFLARE_ACCOUNT_ID: str = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
    # Google Gemini (free-tier multimodal chat/image/video/audio)
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_API_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta"

    # Pollinations (free keyless text-to-image fallback)
    POLLINATIONS_API_BASE_URL: str = "https://image.pollinations.ai"

    # OmniRoute video router — a LOCAL process that drives real signed-in Google Flow and rtst.ai
    # sessions. There is no API key for Flow, which is the whole reason this exists. Loopback only:
    # the router refuses a non-loopback bind unless a token is set, because it spends real credits.
    # Leave the token empty to match a router started without one.
    #
    # NOT named OMNIROUTE_BASE_URL, and that is deliberate. studio_pipeline/omniroute.py already
    # reads os.getenv("OMNIROUTE_BASE_URL") for the *LLM gateway* on :20128, and its probe_video()
    # discovers routes by POSTing a real generation request. Point that name at this router and
    # every capability probe would submit a genuine 20-credit Flow job and then abandon it after
    # an 8s timeout. Separate names, no collision, no accidental spend.
    OMNIROUTE_VIDEO_BASE_URL: str = os.getenv("OMNIROUTE_VIDEO_BASE_URL", "http://127.0.0.1:8189")
    OMNIROUTE_VIDEO_TOKEN: str = os.getenv("OMNIROUTE_VIDEO_TOKEN", "")
    # Hard per-clip ceiling in credits. MEASURED 2026-08-24: a Flow 8s/720p clip quotes 20, an
    # rtst 3s/540p clip quotes 6. 25 admits both and blocks a surprise.
    OMNIROUTE_VIDEO_MAX_CREDITS: int = int(os.getenv("OMNIROUTE_VIDEO_MAX_CREDITS", "25"))
    # Hard ceiling for ONE pipeline run, which is a different and larger risk than one clip.
    # agent_pipeline.run_animator loops over every scene the Animator invented and submits a clip
    # for each, so an 8-scene film is 8 x 20 = 160 credits from a single button press, and nothing
    # in the per-clip ceiling above notices. MEASURED 2026-08-24: the whole rtst balance is 18
    # credits and Flow's is 930, so one careless run can spend a fifth of everything.
    # 60 admits three Flow clips or ten rtst clips per run; scenes past the ceiling are reported as
    # skipped, never silently dropped and never faked.
    OMNIROUTE_VIDEO_MAX_CREDITS_PER_RUN: int = int(
        os.getenv("OMNIROUTE_VIDEO_MAX_CREDITS_PER_RUN", "200")
    )

    # Provider priority (lower = higher priority). Only providers with keys
    # configured are actually registered at runtime. Pollinations is keyless and always available.
    # omniroute_video is first because it is the only provider here that returns a video file that
    # exists: GeminiAdapter.generate_video is a bare NotImplementedError. It only registers when the
    # local router is actually up and signed in, so listing it first costs nothing when it is not.
    PROVIDER_PRIORITY: list[str] = ["omniroute_video", "gemini", "groq", "openrouter", "cerebras", "cohere", "cloudflare", "pollinations"]

    # Default models per capability (free-tier friendly).
    # MEASURED 2026-08-24: "gemini-2.5-flash" is NOT a name the local OmniRoute gateway resolves.
    # Unnamespaced, it maps to a cookie-auth provider and every agent call dies on
    # `[401]: No cookie auth credentials found` (or 503 ALL_ACCOUNTS_INACTIVE via a combo alias).
    # Namespaced names work: gemini/gemini-3.6-flash (3.8s), morph/morph-v3-fast (1.9s, but it is a
    # code-apply model and writes poor prose), auto/best-reasoning (5.9s). Override per-run with the
    # DEFAULT_CHAT_MODEL env var -- pydantic BaseSettings reads it, and env beats backend/.env.
    #
    # Why a COMBO and not a single model: a 7-agent run makes 8 sequential completion calls, so any
    # single upstream is a single point of failure for the whole film. MEASURED 2026-08-24: with
    # gemini-3.6-flash-high the Scriptwriter succeeded (38s, 1088 tokens) and the Art Director then
    # died on `All antigravity accounts have exhausted their quota (reset after 2h 34m 38s)` -- one
    # route, no alternative, run lost. `auto/best-coding` is a priority combo with five distinct
    # providers behind it (codestral-2508 -> gemini-flash-latest -> qwen-max -> gpt-oss-20b ->
    # command-a) and fails over automatically, which is what an 8-call pipeline needs. Measured at
    # 4.9s through the gateway the same day, and it leads with a code model, which suits agents that
    # must return strict JSON.
    DEFAULT_CHAT_MODEL: str = "auto/best-coding"

    # Output ceiling for ONE agent call. Was hardcoded to 1024 at all 8 orchestrator call sites,
    # which is below what this job needs: a multi-scene screenplay JSON does not fit, so the reply
    # arrives truncated and _parse_json dies on `Unterminated string`. Worse, the models that route
    # today are THINKING models -- reasoning_content is drawn from the same budget, so part of 1024
    # was never available to the JSON at all. 4096 held every one of the 7 agents in testing.
    AGENT_MAX_TOKENS: int = int(os.getenv("AGENT_MAX_TOKENS", "4096"))
    DEFAULT_IMAGE_MODEL: str = "pollinations/flux"
    # MEASURED 2026-08-24: the old value here was "gemini-2.5-veo", a name no registered provider
    # accepts. The video router answers `unknown model 'gemini-2.5-veo'` on the free quote, so every
    # request that fell back to this default failed before spending -- safe, but never a video.
    # "" means "let the provider choose", which the router answers with veo_3_1_t2v_fast at 20
    # credits. Set OMNIROUTE_VIDEO_DEFAULT_MODEL to pin a cheaper one: rtst/vidu quotes 6, exact.
    DEFAULT_VIDEO_MODEL: str = os.getenv("OMNIROUTE_VIDEO_DEFAULT_MODEL", "")
    DEFAULT_EMBEDDING_MODEL: str = "cohere/embed-english-v3.0"

    # Model-to-provider mapping (model id prefix -> provider name).
    MODEL_PROVIDER_MAP: dict[str, str] = {
        "llama": "groq",
        "mixtral": "groq",
        "gemma": "groq",
        "openai": "openrouter",
        "anthropic": "openrouter",
        "mistral": "openrouter",
        "command": "cohere",
        "embed-": "cohere",
        "@cf/": "cloudflare",
    }

    # Database (optional - for future use)
    DATABASE_URL: Optional[str] = None
    
    # Redis (optional - for caching/queue)
    REDIS_URL: Optional[str] = None
    
    # Storage (optional - for video storage)
    STORAGE_TYPE: str = "local"  # local, s3, gcs
    STORAGE_PATH: str = "./storage"
    
    # Celery (optional - for background tasks)
    CELERY_BROKER_URL: Optional[str] = None
    CELERY_RESULT_BACKEND: Optional[str] = None
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "allow"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
# We'll read the existing file and update it. Let's first read it.
