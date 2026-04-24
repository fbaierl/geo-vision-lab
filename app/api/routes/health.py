from fastapi import APIRouter
import httpx
import logging
from app.core.config import settings
from app.core.startup import get_warmup_status
from enum import Enum

router = APIRouter()
logger = logging.getLogger(__name__)


class SystemStatusEnum(str, Enum):
    """System status enum for /system/status endpoint."""

    IDLE = "idle"  # GPU available, no model loaded
    LOADING_MODEL = "loading_model"  # Model being loaded
    READY = "ready"  # Model loaded, waiting for work
    PROCESSING = "processing"  # Actively running inference
    ERROR = "error"  # Ollama unreachable or GPU unavailable


# Global state to track processing activity
_processing_state = {
    "is_processing": False,
    "current_query": None,
    "started_at": None,
}


def set_processing_state(is_processing: bool, query: str = None):
    """Set the processing state for the system."""
    _processing_state["is_processing"] = is_processing
    _processing_state["current_query"] = query
    if is_processing:
        from datetime import datetime

        _processing_state["started_at"] = datetime.utcnow().isoformat()
    else:
        _processing_state["started_at"] = None


def get_processing_state() -> dict:
    """Get the current processing state."""
    return dict(_processing_state)


@router.get("/system/status")
async def system_status():
    """Return system status including GPU engagement and model lifecycle states.

    Response includes:
    - status: System status enum (idle, loading_model, ready, processing, error)
    - gpu_available: Whether GPU is available
    - model_loaded: Currently loaded model name (if any)
    - reasoning_model: Configured reasoning model name
    - reviewer_model: Configured reviewer model name
    - vram_bytes: VRAM usage in bytes (if model loaded)
    - processing: Current processing state (is_processing, current_query, started_at)
    - error: Error message (if status is error)
    """
    # Get warmup status to determine model loading state
    warmup_status = get_warmup_status()

    # Determine base status from warmup state
    if warmup_status.get("any_error"):
        base_status = SystemStatusEnum.ERROR
        error_msg = "One or more models failed to load during startup"
    elif not warmup_status.get("completed", False) and warmup_status.get(
        "in_progress", False
    ):
        base_status = SystemStatusEnum.LOADING_MODEL
        error_msg = None
    elif warmup_status.get("ready", False):
        base_status = SystemStatusEnum.IDLE
        error_msg = None
    else:
        base_status = SystemStatusEnum.IDLE
        error_msg = None

    # Override with processing state if actively processing
    if _processing_state["is_processing"]:
        base_status = SystemStatusEnum.PROCESSING

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.OLLAMA_URL}/api/ps")
            data = resp.json()
            models = data.get("models", [])

            if models:
                # Model is currently loaded
                model_info = models[0]
                vram_bytes = model_info.get("size_vram", 0)
                # If model is loaded, GPU is available (Ollama is configured with GPU)
                gpu_available = True

                # Update status: model is loaded and ready
                base_status = SystemStatusEnum.READY

                return {
                    "status": base_status.value,
                    "gpu_available": gpu_available,
                    "model_loaded": model_info.get("name", "unknown"),
                    "reasoning_model": settings.ONLINE_LLM_MODEL_NAME if settings.USE_ONLINE_LLM else settings.REASONING_LLM_MODEL_NAME,
                    "reviewer_model": settings.ONLINE_LLM_MODEL_NAME if settings.USE_ONLINE_LLM else settings.REASONING_LLM_MODEL_NAME,
                    "vram_bytes": vram_bytes,
                    "processing": get_processing_state(),
                    "error": error_msg,
                }

            # No model currently loaded - GPU is available if Ollama responded
            # (Ollama container has GPU configured in docker-compose.yml)
            active_model = settings.ONLINE_LLM_MODEL_NAME if settings.USE_ONLINE_LLM else settings.REASONING_LLM_MODEL_NAME
            return {
                "status": SystemStatusEnum.IDLE.value,
                "gpu_available": True,
                "model_loaded": None,
                "reasoning_model": active_model,
                "reviewer_model": active_model,
                "vram_bytes": 0,
                "processing": get_processing_state(),
                "error": error_msg,
            }
    except Exception as e:
        # Ollama not reachable - GPU not available
        logger.warning(f"[OLLAMA] /api/ps call failed: {e}")
        active_model = settings.ONLINE_LLM_MODEL_NAME if settings.USE_ONLINE_LLM else settings.REASONING_LLM_MODEL_NAME
        return {
            "status": SystemStatusEnum.ERROR.value,
            "gpu_available": False,
            "model_loaded": None,
            "reasoning_model": active_model,
            "reviewer_model": active_model,
            "vram_bytes": 0,
            "processing": get_processing_state(),
            "error": str(e),
        }


@router.get("/system/models/status")
async def models_status():
    """Return model warm-up status."""
    return get_warmup_status()
