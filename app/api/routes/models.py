from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse
from app.core.config import settings
from pydantic import BaseModel


class ModelSwitchRequest(BaseModel):
    model: str


router = APIRouter()


@router.get("/models/reasoning")
async def get_reasoning_models():
    """Get available reasoning models and current selection."""
    return {
        "available_models": settings.AVAILABLE_REASONING_MODELS,
        "current_model": settings.REASONING_LLM_MODEL_NAME,
    }


@router.post("/models/reasoning")
async def set_reasoning_model(request: ModelSwitchRequest):
    """Switch to a different reasoning model."""
    if settings.set_reasoning_model(request.model):
        return {
            "success": True,
            "model": settings.REASONING_LLM_MODEL_NAME,
            "message": f"Reasoning model switched to {request.model}",
        }
    else:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": f"Invalid model. Available: {settings.AVAILABLE_REASONING_MODELS}",
            },
        )
