"""
LLM Service

Provides LLM clients for reasoning and review tasks.
All dependencies are managed by the DI container.

Note: This module now delegates to app.core.di for consistency.
"""

from langchain_ollama import ChatOllama
from app.core.config import settings
from app.core.di import get_reasoning_llm as di_get_reasoning_llm, get_reviewer_llm as di_get_reviewer_llm


def get_reasoning_llm() -> ChatOllama:
    """
    Get the LLM for reasoning tasks (switchable between 9B, 4B, 0.8B).
    
    Uses DI container for managed lifecycle and test overrides.
    """
    return di_get_reasoning_llm()


def get_reviewer_llm() -> ChatOllama:
    """
    Get the LLM for QA review (with timeout to prevent hanging).
    
    Uses DI container for managed lifecycle and test overrides.
    """
    return di_get_reviewer_llm()
