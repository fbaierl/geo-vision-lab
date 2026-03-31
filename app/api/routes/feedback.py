"""
Feedback API for GeoVision Lab

This module provides endpoints for submitting user feedback on AI responses.
Feedback is used to improve response quality and can be tracked in Langfuse/LangSmith.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Literal
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


class FeedbackRequest(BaseModel):
    """Request model for feedback submission."""
    
    thread_id: str = Field(..., description="Session/thread ID")
    message_id: Optional[str] = Field(None, description="Specific message ID (optional)")
    rating: Literal["thumbs_up", "thumbs_down"] = Field(
        ..., description="User rating: thumbs_up or thumbs_down"
    )
    comment: Optional[str] = Field(None, description="Optional feedback comment")


class FeedbackResponse(BaseModel):
    """Response model for feedback submission."""
    
    success: bool
    message: str
    trace_id: Optional[str] = None


@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(request: FeedbackRequest):
    """Submit user feedback on an AI response.
    
    This endpoint accepts thumbs up/down feedback with optional comments.
    When Langfuse is enabled, feedback is sent to Langfuse for tracking.
    
    Args:
        request: FeedbackRequest containing thread_id, rating, and optional comment
        
    Returns:
        FeedbackResponse with success status and trace_id if available
    """
    logger.info(f"[FEEDBACK] Received {request.rating} for thread {request.thread_id}")
    
    try:
        # If Langfuse is enabled, send feedback to Langfuse
        trace_id = None
        if settings.LANGFUSE_ENABLED:
            try:
                import os
                from langfuse import Langfuse
                
                # Set environment variables for Langfuse configuration
                os.environ["LANGFUSE_PUBLIC_KEY"] = settings.LANGFUSE_PUBLIC_KEY
                os.environ["LANGFUSE_SECRET_KEY"] = settings.LANGFUSE_SECRET_KEY
                os.environ["LANGFUSE_HOST"] = settings.LANGFUSE_HOST
                
                langfuse_client = Langfuse(
                    public_key=settings.LANGFUSE_PUBLIC_KEY,
                )
                
                # Create a trace ID for this feedback
                trace_id = langfuse_client.create_trace_id(seed=request.thread_id)
                
                # Score the trace (1 = positive, 0 = negative)
                score_value = 1 if request.rating == "thumbs_up" else 0
                langfuse_client.score_current_trace(
                    name="user_feedback",
                    value=score_value,
                    comment=request.comment or "",
                    trace_id=trace_id,
                )
                
                langfuse_client.flush()
                
                logger.info(f"[FEEDBACK] Feedback sent to Langfuse (trace_id={trace_id})")
                
            except Exception as e:
                logger.error(f"[FEEDBACK] Failed to send to Langfuse: {e}")
                # Don't fail the request - just log the error
        else:
            logger.info("[FEEDBACK] Langfuse not enabled - feedback logged only")
        
        return FeedbackResponse(
            success=True,
            message=f"Feedback '{request.rating}' recorded successfully",
            trace_id=trace_id,
        )
        
    except Exception as e:
        logger.error(f"[FEEDBACK] Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to record feedback: {str(e)}")


@router.get("/feedback/stats")
async def get_feedback_stats():
    """Get feedback statistics (placeholder for future implementation).
    
    Returns:
        Basic feedback statistics
    """
    # This is a placeholder - in production, you'd query Langfuse API
    # or your own database for aggregated stats
    return {
        "total_feedback": 0,
        "thumbs_up": 0,
        "thumbs_down": 0,
        "note": "Statistics available when Langfuse is configured",
    }
