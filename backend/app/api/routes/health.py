"""Health check endpoints."""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    """Basic health check — always returns ok if the app is running."""
    settings = get_settings()
    return {
        "status": "ok",
        "supabase_configured": settings.is_supabase_configured(),
        "apify_configured": settings.is_apify_configured(),
        "rocketreach_configured": bool(settings.rocketreach_email and settings.rocketreach_password),
    }


@router.get("/health/db")
def health_db() -> JSONResponse:
    """Deep health check — tests the Supabase database connection."""
    try:
        from app.repositories.supabase_client import get_supabase
        # Try a minimal query
        get_supabase().table("companies").select("id").limit(1).execute()
        return JSONResponse(content={"status": "ok", "database": "connected"})
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "database": "disconnected", "detail": str(e)},
        )
