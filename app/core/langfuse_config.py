"""
Langfuse Tracing Configuration for GeoVision Lab

This module configures Langfuse tracing for all LangChain/LangGraph operations.
When enabled, all LLM calls, chain executions, and tool invocations are traced
and sent to Langfuse (cloud or self-hosted).

Access the Langfuse UI at: https://cloud.langfuse.com (or your self-hosted instance)

Note: Langfuse v4.x uses OpenTelemetry internally. Configuration is done via
environment variables or explicit parameters.
"""

import os
from typing import Optional, TYPE_CHECKING
from langchain_core.callbacks import CallbackManager
import logging

from app.core.config import settings

if TYPE_CHECKING:
    from langfuse.langchain import CallbackHandler

logger = logging.getLogger(__name__)


def is_langfuse_enabled() -> bool:
    """Check if Langfuse tracing is enabled."""
    return bool(settings.LANGFUSE_ENABLED and settings.LANGFUSE_PUBLIC_KEY and settings.LANGFUSE_SECRET_KEY)


def get_langfuse_callback_handler() -> Optional["CallbackHandler"]:
    """Get Langfuse callback handler if tracing is enabled.
    
    Returns:
        CallbackHandler if Langfuse is enabled and configured, None otherwise.
    """
    if not is_langfuse_enabled():
        return None

    try:
        from langfuse.langchain import CallbackHandler
        
        # Set environment variables for Langfuse configuration
        # This is required for Langfuse v4.x
        os.environ["LANGFUSE_PUBLIC_KEY"] = settings.LANGFUSE_PUBLIC_KEY
        os.environ["LANGFUSE_SECRET_KEY"] = settings.LANGFUSE_SECRET_KEY
        os.environ["LANGFUSE_HOST"] = settings.LANGFUSE_HOST
        
        handler = CallbackHandler(
            public_key=settings.LANGFUSE_PUBLIC_KEY,
        )
        logger.info("[LANGFUSE] Callback handler initialized successfully")
        return handler
    except Exception as e:
        logger.error(f"[LANGFUSE] Failed to initialize callback handler: {e}")
        return None


def get_callback_manager() -> CallbackManager:
    """Get callback manager with Langfuse tracer if enabled.
    
    Returns:
        CallbackManager with Langfuse handler if enabled, empty manager otherwise.
    """
    callbacks = []

    if is_langfuse_enabled():
        handler = get_langfuse_callback_handler()
        if handler:
            callbacks.append(handler)

    return CallbackManager(handlers=callbacks)
