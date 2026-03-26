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
from typing import Optional

from app.core.config import settings

router = APIRouter()


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


class SettingsUpdateRequest(BaseModel):
    """Request model for POST /settings."""
    # Model selection
    model: Optional[str] = None
    
    # Online LLM toggle
    use_online_llm: Optional[bool] = None
    
    # Online LLM model selection
    online_model: Optional[str] = None


@router.get("/settings")
async def get_settings():
    """Get all runtime settings.
    
    Returns current configuration for:
    - Local LLM (Ollama) models
    - Online LLM (Groq) models
    - API key status
    - Current selections
    """
    # Build combined model list with type indicators
    all_models = []
    
    # Add local models
    for model in settings.AVAILABLE_REASONING_MODELS:
        all_models.append({
            "id": model,
            "name": model,
            "type": "local",
            "provider": "Ollama",
            "current": model == settings.REASONING_LLM_MODEL_NAME and not settings.USE_ONLINE_LLM
        })
    
    # Add online models
    for model in settings.AVAILABLE_ONLINE_MODELS:
        all_models.append({
            "id": model,
            "name": model,
            "type": "online",
            "provider": "Groq",
            "current": model == settings.ONLINE_LLM_MODEL_NAME and settings.USE_ONLINE_LLM
        })
    
    return SettingsResponse(
        local_llm_enabled=not settings.USE_ONLINE_LLM,
        current_local_model=settings.REASONING_LLM_MODEL_NAME,
        available_local_models=settings.AVAILABLE_REASONING_MODELS,
        online_llm_enabled=settings.USE_ONLINE_LLM,
        current_online_model=settings.ONLINE_LLM_MODEL_NAME,
        available_online_models=settings.AVAILABLE_ONLINE_MODELS,
        groq_api_key_configured=settings.is_groq_api_key_configured(),
        all_models=all_models
    )


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
                    "message": "Groq API key is required to enable online LLM. Please add GROQ_API_KEY to your .env file."
                }
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
                    "message": f"Invalid online model. Available: {settings.AVAILABLE_ONLINE_MODELS}"
                }
            )
    
    # Handle generic model selection (for backward compatibility)
    if request.model is not None:
        # Try local models first
        if request.model in settings.AVAILABLE_REASONING_MODELS:
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
                        "message": "Groq API key is required to use online models."
                    }
                )
            settings.set_online_llm_model(request.model)
            settings.set_online_llm_enabled(True)
        else:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "invalid_model",
                    "message": f"Invalid model. Available: {settings.AVAILABLE_REASONING_MODELS + settings.AVAILABLE_ONLINE_MODELS}"
                }
            )
    
    # Clear DI container cache so new model is picked up
    from app.core.di import container
    container._instances.clear()
    
    # Return updated settings
    return await get_settings()
