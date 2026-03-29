import os
import logging
import logging.config
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.api.routes import chat, health, models, ontology, sessions, rag_config
from app.api.routes import settings as settings_router


class PollingFilter(logging.Filter):
    """Filter out repetitive /api/ps polling logs from httpx."""
    def filter(self, record):
        msg = record.getMessage()
        if record.levelno == logging.INFO and 'GET' in msg and '/api/ps' in msg and '200 OK' in msg:
            return False
        return True


# Configure logging for Dozzle visibility
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
httpx_logger = logging.getLogger("httpx")
httpx_logger.addFilter(PollingFilter())

logger = logging.getLogger("geovision_app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager.

    Kicks off model warm-up immediately in the background so the UI
    is available while models are still loading / being downloaded.
    """
    import asyncio
    from app.core.startup import warm_up_models

    logger.info("[APP] Starting GeoVision Lab API server…")
    logger.info("[APP] UI available immediately — models loading in background.")

    # Fire-and-forget: warmup runs concurrently with request handling
    asyncio.create_task(warm_up_models())

    yield  # app is running

    logger.info("[APP] Shutting down GeoVision Lab.")


app = FastAPI(title=settings.APP_NAME, version=settings.VERSION, lifespan=lifespan)
logger.info(f"[APP] App initialised: {settings.APP_NAME} v{settings.VERSION}")

# Include API routes
app.include_router(chat.router, tags=["chat"])
app.include_router(health.router, tags=["health"])
app.include_router(models.router, tags=["models"])
app.include_router(settings_router.router, tags=["settings"])
app.include_router(ontology.router, tags=["ontology"])
app.include_router(sessions.router, tags=["sessions"])
app.include_router(rag_config.router, tags=["rag"])

# Ensure static directories exist
os.makedirs("static", exist_ok=True)


class NoCacheStaticFiles(StaticFiles):
    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["method"] == "GET":
            async def send_with_no_cache(message):
                if message["type"] == "http.response.start":
                    headers = list(message.get("headers", []))
                    headers.extend([
                        (b"cache-control", b"no-cache, no-store, must-revalidate"),
                        (b"pragma", b"no-cache"),
                        (b"expires", b"0"),
                    ])
                    message["headers"] = headers
                await send(message)
            await super().__call__(scope, receive, send_with_no_cache)
        else:
            await super().__call__(scope, receive, send)


app.mount("/ui", NoCacheStaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def read_root():
    """Serve the main tactical interface on root."""
    try:
        return FileResponse(
            "static/index.html",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )
    except Exception:
        return HTMLResponse(
            content="<h1>GeoVision Lab UI not found.</h1><p>Please ensure static/index.html exists.</p>",
            status_code=404,
        )
