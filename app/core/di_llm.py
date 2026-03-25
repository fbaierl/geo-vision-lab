"""
LLM Dependencies for GeoVision Lab

This module provides LLM-related dependency providers.
Uses the DI container for clean, testable dependency injection.

Usage:
    from app.core.di_llm import get_llm

    def some_operation(llm=Depends(get_llm)):
        ...

Testing:
    from app.core.di import container
    container.override(get_llm, mock_llm)
"""

from langchain_ollama import ChatOllama
import logging

from app.core.config import settings
from app.core.langsmith_config import get_callback_manager

logger = logging.getLogger(__name__)


def _get_container():
    """Lazy import to avoid circular dependency."""
    from app.core.di import container
    return container


def _create_llm() -> ChatOllama:
    """Factory function to create LLM.

    Single LLM instance used for all tasks:
    - Agent reasoning
    - QA validation
    - Ontology extraction
    - Location prioritization

    The model is determined by settings.REASONING_LLM_MODEL_NAME.
    Default: qwen3.5:4b, switchable to qwen3.5:9b via UI.

    Timeout set to 120 seconds for long responses.
    """
    logger.info(f"[DI] Creating LLM: {settings.REASONING_LLM_MODEL_NAME}")
    callback_manager = get_callback_manager()
    return ChatOllama(
        model=settings.REASONING_LLM_MODEL_NAME,
        base_url=settings.OLLAMA_URL,
        callback_manager=callback_manager,
        timeout=120  # Increased timeout for complex reasoning
    )


def get_llm() -> ChatOllama:
    """Get LLM (managed by DI container).

    Single LLM for all tasks - Qwen 3.5 family (4B default, 9B optional).
    """
    return _get_container()._get_or_create(get_llm, _create_llm)
