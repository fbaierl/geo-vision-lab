import os
import logging
import logging.config
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.api.routes import chat, health, models


class PollingFilter(logging.Filter):
    """Filter out repetitive /api/ps polling logs from httpx."""
    def filter(self, record):
        msg = record.getMessage()
        # Allow all logs except successful GET /api/ps calls
        if record.levelno == logging.INFO and 'GET' in msg and '/api/ps' in msg and '200 OK' in msg:
            return False
        return True


# Configure logging for Dozzle visibility
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
# Apply filter to httpx logger to suppress repetitive /api/ps polling logs
httpx_logger = logging.getLogger("httpx")
httpx_logger.addFilter(PollingFilter())

logger = logging.getLogger("geovision_app")
logger.info("[APP] Starting GeoVision Lab API server...")

app = FastAPI(title=settings.APP_NAME, version=settings.VERSION)
logger.info(f"[APP] App initialized: {settings.APP_NAME} v{settings.VERSION}")

# Enable CORS or other middlewares if needed in the future

# Include API routes
app.include_router(chat.router, tags=["chat"])
app.include_router(health.router, tags=["health"])
app.include_router(models.router, tags=["models"])

# Ensure static directories exist
os.makedirs("static", exist_ok=True)

# Mount static files to serve the frontend with no caching


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
