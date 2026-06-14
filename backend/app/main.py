"""Lead Generation API — FastAPI application entry point."""
import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import companies, health, jobs, leads, stats
from app.config import get_settings

# Force UTF-8 output on Windows to avoid UnicodeEncodeError for special characters
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup logic runs before yield, shutdown after."""
    settings = get_settings()
    sep = "=" * 60
    logger.info(sep)
    logger.info("Lead Gen API v2.0.0 starting up")
    logger.info("Supabase URL    : %s", settings.supabase_url or "NOT SET")
    logger.info("Apify MCP URL   : %s", settings.apify_mcp_url)
    logger.info("Concurrency     : %d", settings.concurrency)
    logger.info("Batch size      : %d", settings.batch_size)

    if not settings.is_supabase_configured():
        key_status = "publishable key (WRONG)" if "publishable" in settings.supabase_service_role_key.lower() \
            else ("MISSING" if not settings.supabase_service_role_key else "too short")
        logger.error(
            "[!] Supabase NOT properly configured! "
            "SUPABASE_URL=%s | KEY=%s | "
            "Database operations will fail. "
            "Use the service_role JWT from Supabase Dashboard -> Settings -> API.",
            "set" if settings.supabase_url else "MISSING",
            key_status,
        )
    else:
        logger.info("[OK] Supabase configured")

    if not settings.is_apify_configured():
        logger.warning("[!] Apify token not set -- MCP browser automation will fail")
    else:
        logger.info("[OK] Apify token configured")

    if not settings.rocketreach_email:
        logger.warning("[!] RocketReach credentials not set")
    else:
        logger.info("[OK] RocketReach: %s", settings.rocketreach_email)

    logger.info(sep)
    yield  # Application runs here
    # Shutdown logic (if any) goes here


app = FastAPI(
    title="Lead Generation API",
    version="2.0.0",
    description="AI-powered lead generation from company domains via RocketReach + Playwright MCP",
    lifespan=lifespan,
)


def _origins() -> list[str]:
    try:
        origins = [o.strip() for o in get_settings().cors_origins.split(",") if o.strip()]
        return origins or ["http://localhost:5173", "http://localhost:3000"]
    except Exception:
        return ["http://localhost:5173", "http://localhost:3000"]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------------------------------------------------ #
# Global exception handlers
# ------------------------------------------------------------------ #

@app.exception_handler(RuntimeError)
async def runtime_error_handler(_: Request, exc: RuntimeError) -> JSONResponse:
    logger.error("RuntimeError: %s", exc)
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(ValueError)
async def value_error_handler(_: Request, exc: ValueError) -> JSONResponse:
    logger.warning("ValueError: %s", exc)
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(Exception)
async def generic_error_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {type(exc).__name__}: {exc}"},
    )


# ------------------------------------------------------------------ #
# Routers
# ------------------------------------------------------------------ #

app.include_router(health.router, prefix="/api")
app.include_router(stats.router, prefix="/api")
app.include_router(companies.router, prefix="/api")
app.include_router(leads.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")


@app.get("/", tags=["root"])
def root() -> dict[str, str]:
    return {"service": "lead-gen-api", "version": "2.0.0", "docs": "/docs"}
