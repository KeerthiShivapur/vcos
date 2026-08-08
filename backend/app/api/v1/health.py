"""Health & platform metadata."""

from fastapi import APIRouter, Depends

from app.core.config import get_settings

router = APIRouter(tags=["Platform"])
platform_router = APIRouter(tags=["Platform"])


@router.get("/health", response_model=dict)
async def health():
    return {"status": "ok", "service": "vcos-backend"}


@platform_router.get("/platform", response_model=dict)
async def platform_info():
    settings = get_settings()
    return {
        "name": settings.APP_NAME,
        "version": "1.0.0",
        "environment": settings.APP_ENV,
        "api_version": "v1",
        "ai_provider": settings.AI_PROVIDER,
        "features": {
            "foundation": True,
            "ai_foundation": True,
            "redis": settings.REDIS_ENABLED,
        },
    }
