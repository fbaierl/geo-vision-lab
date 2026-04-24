"""
Unified Settings API for GeoVision Lab

Provides endpoints for managing runtime configuration including:
- LLM model selection (local and online)
- Online LLM toggle (Groq)
- API key status
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List
import httpx

from app.core.config import settings

router = APIRouter()


async def get_pulled_ollama_models() -> List[str]:
    """Get list of models that are already pulled in Ollama."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{settings.OLLAMA_URL}/api/tags")
            r.raise_for_status()
            tags_data = r.json()
            return [m.get("name", "") for m in tags_data.get("models", [])]
    except Exception:
        return []


class SettingsResponse(BaseModel):
    """Response model for GET /settings."""

    # Local LLM settings
    local_llm_enabled: bool
    current_local_model: str
    available_local_models: list[str]

    # Online LLM settings
    online_llm_enabled: bool
    current_online_model: str
    available_online_models: list[str]
    groq_api_key_configured: bool

    # Combined model list for UI
    all_models: list[dict]

    # Actual active model name (for display purposes)
    active_model_name: str
    active_model_type: str  # "local" or "online"


class SettingsUpdateRequest(BaseModel):
    """Request model for POST /settings."""

    # Model selection
    model: Optional[str] = None

    # Online LLM toggle
    use_online_llm: Optional[bool] = None

    # Online LLM model selection
    online_model: Optional[str] = None


async def build_settings_response():
    """Build the settings response with current configuration."""
    # Build combined model list with type indicators
    all_models = []

    # Get pulled models from Ollama
    pulled_models = await get_pulled_ollama_models()

    # Add local models
    for model in settings.AVAILABLE_REASONING_MODELS:
        is_ready = any(model in m for m in pulled_models)
        all_models.append(
            {
                "id": model,
                "name": model,
                "type": "local",
                "provider": "Ollama",
                "current": model == settings.REASONING_LLM_MODEL_NAME
                and not settings.USE_ONLINE_LLM,
                "ready": is_ready,
            }
        )

    # Add online models
    for model in settings.AVAILABLE_ONLINE_MODELS:
        all_models.append(
            {
                "id": model,
                "name": model,
                "type": "online",
                "provider": "Groq",
                "current": model == settings.ONLINE_LLM_MODEL_NAME
                and settings.USE_ONLINE_LLM,
            }
        )

    # Determine active model name and type
    active_model_name = (
        settings.ONLINE_LLM_MODEL_NAME
        if settings.USE_ONLINE_LLM
        else settings.REASONING_LLM_MODEL_NAME
    )
    active_model_type = "online" if settings.USE_ONLINE_LLM else "local"

    return SettingsResponse(
        local_llm_enabled=not settings.USE_ONLINE_LLM,
        current_local_model=settings.REASONING_LLM_MODEL_NAME,
        available_local_models=settings.AVAILABLE_REASONING_MODELS,
        online_llm_enabled=settings.USE_ONLINE_LLM,
        current_online_model=settings.ONLINE_LLM_MODEL_NAME,
        available_online_models=settings.AVAILABLE_ONLINE_MODELS,
        groq_api_key_configured=settings.is_groq_api_key_configured(),
        all_models=all_models,
        active_model_name=active_model_name,
        active_model_type=active_model_type,
    )


@router.get("/settings")
async def get_settings():
    """Get all runtime settings.

    Returns current configuration for:
    - Local LLM (Ollama) models
    - Online LLM (Groq) models
    - API key status
    - Current selections
    """
    return await build_settings_response()


@router.post("/settings")
async def update_settings(request: SettingsUpdateRequest):
    """Update runtime settings.

    Accepts:
    - model: Switch to a specific model (local or online)
    - use_online_llm: Toggle online LLM mode (true/false)
    - online_model: Set the online LLM model name

    Returns updated settings or error if configuration is invalid.
    """
    # Handle online LLM toggle
    if request.use_online_llm is not None:
        if request.use_online_llm and not settings.is_groq_api_key_configured():
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "groq_api_key_missing",
                    "message": "Groq API key is required to enable online LLM. Please add GROQ_API_KEY to your .env file.",
                },
            )
        settings.set_online_llm_enabled(request.use_online_llm)

    # Handle online model selection
    if request.online_model is not None:
        if not settings.set_online_llm_model(request.online_model):
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "invalid_online_model",
                    "message": f"Invalid online model. Available: {settings.AVAILABLE_ONLINE_MODELS}",
                },
            )

    # Handle generic model selection (for backward compatibility)
    if request.model is not None:
        # Try local models first
        if request.model in settings.AVAILABLE_REASONING_MODELS:
            # Check if model is pulled in Ollama
            pulled_models = await get_pulled_ollama_models()
            is_ready = any(request.model in m for m in pulled_models)
            if not is_ready:
                return JSONResponse(
                    status_code=400,
                    content={
                        "success": False,
                        "error": "model_not_ready",
                        "message": f"Model '{request.model}' is still downloading. Please wait for it to finish.",
                    },
                )
            settings.set_reasoning_model(request.model)
            settings.set_online_llm_enabled(False)
        # Then try online models
        elif request.model in settings.AVAILABLE_ONLINE_MODELS:
            if not settings.is_groq_api_key_configured():
                return JSONResponse(
                    status_code=400,
                    content={
                        "success": False,
                        "error": "groq_api_key_missing",
                        "message": "Groq API key is required to use online models.",
                    },
                )
            settings.set_online_llm_model(request.model)
            settings.set_online_llm_enabled(True)
        else:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "invalid_model",
                    "message": f"Invalid model. Available: {settings.AVAILABLE_REASONING_MODELS + settings.AVAILABLE_ONLINE_MODELS}",
                },
            )

    # Clear DI container cache so new model is picked up
    from app.core.di import container

    container._instances.clear()

    # Return updated settings
    return await build_settings_response()
