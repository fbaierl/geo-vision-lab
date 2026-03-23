from fastapi import APIRouter
import httpx
from app.core.config import settings

router = APIRouter()


@router.get("/system/status")
async def system_status():
    """Return system status including GPU engagement from Ollama."""
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
                return {
                    "gpu_engaged": vram_bytes > 0,
                    "gpu_available": gpu_available,
                    "model": model_info.get("name", "unknown"),
                    "reasoning_model": settings.REASONING_LLM_MODEL_NAME,
                    "reviewer_model": settings.REVIEWER_LLM_MODEL_NAME,
                    "vram_bytes": vram_bytes,
                    "reason": "gpu" if vram_bytes > 0 else "gpu_standby",
                }
            
            # No model currently loaded - GPU is available if Ollama responded
            # (Ollama container has GPU configured in docker-compose.yml)
            return {
                "gpu_engaged": False,
                "gpu_available": True,
                "model": None,
                "reasoning_model": settings.REASONING_LLM_MODEL_NAME,
                "reviewer_model": settings.REVIEWER_LLM_MODEL_NAME,
                "vram_bytes": 0,
                "reason": "gpu_standby",
            }
    except Exception as e:
        # Ollama not reachable - GPU not available
        return {
            "gpu_engaged": False,
            "gpu_available": False,
            "model": None,
            "reasoning_model": settings.REASONING_LLM_MODEL_NAME,
            "reviewer_model": settings.REVIEWER_LLM_MODEL_NAME,
            "vram_bytes": 0,
            "reason": str(e),
        }
