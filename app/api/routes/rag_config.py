"""
RAG Configuration API Routes for GeoVision Lab

Provides endpoints to get and update RAG feature configuration at runtime.
"""

from fastapi import APIRouter, HTTPException
from app.models.rag_config import RAGConfig, RAGConfigUpdate
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/rag", tags=["rag"])


@router.get("/config", response_model=RAGConfig)
async def get_rag_config():
    """
    Get current RAG configuration.

    Returns the current state of RAG features (grader, re-ranker).
    """
    config = settings.get_rag_config()
    return RAGConfig(**config)


@router.post("/config", response_model=RAGConfig)
async def update_rag_config(update: RAGConfigUpdate):
    """
    Update RAG configuration at runtime.

    Allows enabling/disabling individual RAG features without restart.
    Changes are applied in-memory and persist until service restart.

    **Note:** Changes affect all users/sessions.
    """
    try:
        if update.grader_enabled is not None:
            settings.set_rag_grader_enabled(update.grader_enabled)
            logger.info(
                f"[RAG_CONFIG] Grader {'enabled' if update.grader_enabled else 'disabled'}"
            )

        if update.reranker_enabled is not None:
            settings.set_rag_reranker_enabled(update.reranker_enabled)
            logger.info(
                f"[RAG_CONFIG] Re-ranker {'enabled' if update.reranker_enabled else 'disabled'}"
            )

        # Return updated config
        config = settings.get_rag_config()
        return RAGConfig(**config)

    except Exception as e:
        logger.error(f"[RAG_CONFIG] Failed to update config: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to update configuration: {str(e)}"
        )
