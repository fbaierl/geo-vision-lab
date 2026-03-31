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
from langchain_groq import ChatGroq
from langchain_core.language_models.chat_models import BaseChatModel
from typing import TYPE_CHECKING
import logging

from app.core.config import settings
from app.core.langfuse_config import get_callback_manager as get_langfuse_callback_manager
from app.core.langsmith_config import get_callback_manager as get_langsmith_callback_manager

if TYPE_CHECKING:
    from langchain_core.callbacks import CallbackManager

logger = logging.getLogger(__name__)


def _get_container():
    """Lazy import to avoid circular dependency."""
    from app.core.di import container

    return container


def _get_callback_manager() -> "CallbackManager":
    """Get callback manager for tracing.
    
    Priority: Langfuse > LangSmith > None
    Only one tracing backend is active at a time.
    """
    from langchain_core.callbacks import CallbackManager
    
    # Try Langfuse first (if enabled)
    if settings.LANGFUSE_ENABLED:
        logger.info("[DI] Using Langfuse for tracing")
        return get_langfuse_callback_manager()
    
    # Fallback to LangSmith
    if settings.LANGSMITH_TRACING:
        logger.info("[DI] Using LangSmith for tracing")
        return get_langsmith_callback_manager()
    
    # No tracing enabled
    logger.info("[DI] No tracing enabled")
    return CallbackManager(handlers=[])


def _create_llm() -> BaseChatModel:
    """Factory function to create LLM.

    Supports both local (Ollama) and online (Groq) LLMs:
    - Local: Qwen 3.5 family (4B default, 9B optional) via Ollama
    - Online: Llama 4 Scout 17B via Groq (when USE_ONLINE_LLM is True)

    Single LLM instance used for all tasks:
    - Agent reasoning
    - QA validation
    - Ontology extraction
    - Location prioritization

    Timeout set to 120 seconds for long responses.
    """
    callback_manager = _get_callback_manager()

    if settings.USE_ONLINE_LLM:
        if not settings.GROQ_API_KEY:
            logger.warning(
                "[DI] Online LLM requested but GROQ_API_KEY not configured. Falling back to local LLM."
            )
            return ChatOllama(
                model=settings.REASONING_LLM_MODEL_NAME,
                base_url=settings.OLLAMA_URL,
                callback_manager=callback_manager,
                timeout=120,
            )

        logger.info(
            f"[DI] Creating online LLM (Groq): {settings.ONLINE_LLM_MODEL_NAME}"
        )
        llm = ChatGroq(
            model=settings.ONLINE_LLM_MODEL_NAME,
            api_key=settings.GROQ_API_KEY,
        )
        # Configure callbacks for Groq (callback_manager not supported as direct parameter)
        if callback_manager:
            llm = llm.with_config(callback_manager=callback_manager)
        return llm
    else:
        logger.info(
            f"[DI] Creating local LLM (Ollama): {settings.REASONING_LLM_MODEL_NAME}"
        )
        return ChatOllama(
            model=settings.REASONING_LLM_MODEL_NAME,
            base_url=settings.OLLAMA_URL,
            callback_manager=callback_manager,
            timeout=120,  # Increased timeout for complex reasoning
        )


def get_llm() -> BaseChatModel:
    """Get LLM (managed by DI container).

    Returns local (Ollama) or online (Groq) LLM based on settings.USE_ONLINE_LLM.
    """
    return _get_container()._get_or_create(get_llm, _create_llm)
