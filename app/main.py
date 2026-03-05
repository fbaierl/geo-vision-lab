import os
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.api.routes import chat, health

app = FastAPI(title=settings.APP_NAME, version=settings.VERSION)

# Enable CORS or other middlewares if needed in the future

# Include API routes
app.include_router(chat.router, tags=["chat"])
app.include_router(health.router, tags=["health"])

# Ensure static directories exist
os.makedirs("static", exist_ok=True)

# Mount static files to serve the frontend
app.mount("/ui", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def read_root():
    """Serve the main tactical interface on root."""
    try:
        with open("static/index.html", "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return "<h1>GeoVision Lab UI not found.</h1><p>Please ensure static/index.html exists.</p>"
