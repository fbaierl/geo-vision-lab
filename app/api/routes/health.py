from fastapi import APIRouter
import httpx
from app.core.config import settings

router = APIRouter()


@router.get("/system/status")
async def system_status():
    """Return system status including GPU engagement from Ollama."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.OLLAMA_BASE_URL}/api/ps")
            data = resp.json()
            models = data.get("models", [])
            if models:
                model_info = models[0]
                vram_bytes = model_info.get("size_vram", 0)
                return {
                    "gpu_engaged": vram_bytes > 0,
                    "model": model_info.get("name", "unknown"),
                    "reasoning_model": settings.REASONING_LLM_MODEL_NAME,
                    "reviewer_model": settings.REVIEWER_LLM_MODEL_NAME,
                    "vram_bytes": vram_bytes,
                    "reason": "gpu" if vram_bytes > 0 else "cpu_only",
                }
            # No model currently loaded (idle between requests)
            return {
                "gpu_engaged": False,
                "model": None,
                "reasoning_model": settings.REASONING_LLM_MODEL_NAME,
                "reviewer_model": settings.REVIEWER_LLM_MODEL_NAME,
                "vram_bytes": 0,
                "reason": "no_model_loaded",
            }
    except Exception as e:
        return {
            "gpu_engaged": False,
            "model": None,
            "reasoning_model": settings.REASONING_LLM_MODEL_NAME,
            "reviewer_model": settings.REVIEWER_LLM_MODEL_NAME,
            "vram_bytes": 0,
            "reason": str(e),
        }
