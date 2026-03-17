"""
LLM Dependencies for GeoVision Lab

This module provides LLM-related dependency providers.
Uses the DI container for clean, testable dependency injection.

Usage:
    from app.core.di_llm import get_reasoning_llm, get_reviewer_llm

    def some_operation(reasoning_llm=Depends(get_reasoning_llm)):
        ...

Testing:
    from app.core.di import container
    container.override(get_reasoning_llm, mock_llm)
"""

from langchain_ollama import ChatOllama
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


def _get_container():
    """Lazy import to avoid circular dependency."""
    from app.core.di import container
    return container


def _create_reasoning_llm() -> ChatOllama:
    """Factory function to create reasoning LLM."""
    logger.info(f"[DI] Creating reasoning LLM: {settings.REASONING_LLM_MODEL_NAME}")
    return ChatOllama(
        model=settings.REASONING_LLM_MODEL_NAME,
        base_url=settings.OLLAMA_URL
    )


def _create_reviewer_llm() -> ChatOllama:
    """Factory function to create reviewer LLM."""
    logger.info(f"[DI] Creating reviewer LLM: {settings.REVIEWER_LLM_MODEL_NAME}")
    return ChatOllama(
        model=settings.REVIEWER_LLM_MODEL_NAME,
        base_url=settings.OLLAMA_URL,
        num_predict=20,
        timeout=60
    )


def get_reasoning_llm() -> ChatOllama:
    """Get reasoning LLM (managed by DI container)."""
    return _get_container()._get_or_create(get_reasoning_llm, _create_reasoning_llm)


def get_reviewer_llm() -> ChatOllama:
    """Get reviewer LLM (managed by DI container)."""
    return _get_container()._get_or_create(get_reviewer_llm, _create_reviewer_llm)
