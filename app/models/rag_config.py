"""
RAG Configuration Models for GeoVision Lab
"""

from pydantic import BaseModel, Field
from typing import Optional


class RAGConfig(BaseModel):
    """RAG configuration response model."""
    grader_enabled: bool = Field(..., description="Whether context grading is enabled")
    reranker_enabled: bool = Field(..., description="Whether BGE re-ranker is enabled")
    reranker_model: str = Field(..., description="Re-ranker model name")
    reranker_top_k: int = Field(..., description="Number of results after re-ranking")
    reranker_candidates_k: int = Field(..., description="Number of candidates for re-ranking")


class RAGConfigUpdate(BaseModel):
    """RAG configuration update request model."""
    grader_enabled: Optional[bool] = Field(None, description="Enable/disable context grading")
    reranker_enabled: Optional[bool] = Field(None, description="Enable/disable BGE re-ranker")
