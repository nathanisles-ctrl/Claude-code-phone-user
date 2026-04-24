import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from config import settings
import database as db
from routes import projects, characters, scenes, videos, notion

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

_SW_PATH = Path("static/service-worker.js")


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.ensure_dirs()
    db.init_db()
    missing = settings.validate()
    if missing:
        logger.warning("Missing config keys: %s — some features will be disabled", missing)
    else:
        logger.info("All API keys configured")
    logger.info("Creative Video Studio ready on http://%s:%s", settings.HOST, settings.PORT)
    yield


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Creative Video Studio",
    description=(
        "Professional video generation studio — Notion integration, "
        "multi-model AI video (Higgsfield), ElevenLabs voiceover, auto-captions."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Allow all origins so the studio is accessible from a phone on the same network
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Security + cache-control middleware ───────────────────────────────────────
@app.middleware("http")
async def add_headers(request: Request, call_next):
    response: Response = await call_next(request)
    path = request.url.path

    # Security headers (safe for all responses)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

    # Cache-control per resource type
    if path == "/service-worker.js":
        # Service worker must never be cached by the browser — it manages its own cache
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Service-Worker-Allowed"] = "/"

    elif path.startswith("/static/icons/") or path.startswith("/static/screenshots/"):
        # Icons change rarely — cache for 30 days
        response.headers["Cache-Control"] = "public, max-age=2592000, immutable"

    elif path.startswith("/static/"):
        # Other static assets — cache 1 hour, revalidate
        response.headers["Cache-Control"] = "public, max-age=3600, stale-while-revalidate=86400"

    elif path.startswith("/api/"):
        # API responses — always fresh
        response.headers["Cache-Control"] = "no-store"

    elif path.startswith("/output/"):
        # Generated videos — cache for 7 days (content-addressed filenames)
        response.headers["Cache-Control"] = "public, max-age=604800"

    return response


# ── Global error handler ──────────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception on %s: %s", request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error": str(exc)},
    )


# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(projects.router)
app.include_router(characters.router)
app.include_router(scenes.router)
app.include_router(videos.router)
app.include_router(notion.router)


# ── PWA: serve service worker from root scope ─────────────────────────────────
@app.get("/service-worker.js", include_in_schema=False)
async def serve_service_worker():
    """
    The service worker MUST be served from the root path so it can control
    the full origin scope ("/"). The file lives in static/ but is exposed here.
    """
    if not _SW_PATH.exists():
        return JSONResponse(status_code=404, content={"detail": "service-worker.js not found"})
    return FileResponse(
        path=str(_SW_PATH),
        media_type="application/javascript",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Service-Worker-Allowed": "/",
        },
    )


# ── Static files ──────────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory="static"), name="static")

# Serve generated output so videos are streamable/downloadable via URL
try:
    app.mount("/output", StaticFiles(directory=str(settings.OUTPUT_DIR)), name="output")
except Exception:
    pass


# ── Core endpoints ────────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
async def health():
    return {
        "status": "ok",
        "higgsfield_configured": bool(settings.HIGGSFIELD_API_ID and settings.HIGGSFIELD_API_SECRET),
        "elevenlabs_configured": bool(settings.ELEVENLABS_API_KEY),
        "notion_configured": bool(settings.NOTION_API_KEY),
        "database": settings.DATABASE_PATH,
        "pwa": True,
    }


@app.get("/api/models", tags=["System"])
async def list_models():
    """Return supported video models and their recommended scene types."""
    return {
        key: {
            "id": key,
            "name": info["name"],
            "scene_types": info["scene_types"],
            "provider": info["provider"],
        }
        for key, info in settings.VIDEO_MODELS.items()
    }


@app.get("/api/voices", tags=["Voices"])
async def list_voices():
    """Return available ElevenLabs voices."""
    import voiceover_generator as vo
    if not settings.ELEVENLABS_API_KEY:
        return {"error": "ElevenLabs not configured", "voices": []}
    try:
        voices = await vo.list_voices()
        return {"voices": voices}
    except Exception as exc:
        return {"error": str(exc), "voices": []}


# ── SPA fallback (must be last) ───────────────────────────────────────────────
@app.get("/{full_path:path}", include_in_schema=False)
async def spa_fallback(full_path: str):
    """Serve the SPA shell for any unmatched navigation request."""
    return FileResponse(
        "static/index.html",
        headers={"Cache-Control": "no-store"},   # ensure shell is always fresh
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="debug" if settings.DEBUG else "info",
    )
