from fastapi import APIRouter, Depends

from app.api.v1.dependencies.auth import get_current_user

from app.api.v1.endpoints import (
    auth,
    chat,
    images,
    videos,
    audio,
    projects,
    pipeline,
    models,
    styles,
    providers,
    assets,
    jobs,
    agency,
    films,
)

# AC-10: NVIDIA NIM router removed. Multi-provider free-tier endpoints connected.
api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
_protected = [Depends(get_current_user)]
api_router.include_router(chat.router, prefix="/chat", tags=["Chat"], dependencies=_protected)
api_router.include_router(images.router, prefix="/images", tags=["Images"], dependencies=_protected)
api_router.include_router(videos.router, prefix="/videos", tags=["Videos"], dependencies=_protected)
api_router.include_router(audio.router, prefix="/audio", tags=["Audio"], dependencies=_protected)
api_router.include_router(projects.router, prefix="/projects", tags=["Projects"], dependencies=_protected)
api_router.include_router(pipeline.router, prefix="/projects", tags=["Pipeline"], dependencies=_protected)
api_router.include_router(assets.router, prefix="/assets", tags=["Assets"], dependencies=_protected)
api_router.include_router(jobs.router, prefix="/jobs", tags=["Jobs"], dependencies=_protected)
api_router.include_router(films.router, prefix="/films", tags=["Films"], dependencies=_protected)
api_router.include_router(models.router, prefix="/models", tags=["Models"], dependencies=_protected)
api_router.include_router(styles.router, prefix="/styles", tags=["Styles"], dependencies=_protected)
api_router.include_router(providers.router, prefix="/providers", tags=["Providers"], dependencies=_protected)
api_router.include_router(agency.router, prefix="/agency", tags=["Agency"], dependencies=_protected)
