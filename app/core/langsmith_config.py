"""
LangSmith Tracing Configuration for GeoVision Lab

This module configures LangSmith tracing for all LangChain/LangGraph operations.
When enabled, all LLM calls, chain executions, and tool invocations are traced
and sent to the self-hosted LangSmith instance.

Access the LangSmith UI at: http://localhost:3030
"""

import os
from typing import Optional
from langchain_core.callbacks import CallbackManager
from langchain_core.tracers.langchain import LangChainTracer
from langsmith import Client

from app.core.config import settings


def is_langsmith_enabled() -> bool:
    """Check if LangSmith tracing is enabled."""
    return settings.LANGSMITH_TRACING and settings.LANGSMITH_ENDPOINT


def get_langsmith_client() -> Optional[Client]:
    """Get LangSmith client if tracing is enabled."""
    if not is_langsmith_enabled():
        return None
    
    try:
        client = Client(
            api_url=settings.LANGSMITH_ENDPOINT,
            api_key=settings.LANGSMITH_API_KEY,
        )
        return client
    except Exception as e:
        print(f"[LANGSMITH] Failed to initialize client: {e}")
        return None


def get_langchain_tracer() -> Optional[LangChainTracer]:
    """Get LangChain tracer if tracing is enabled."""
    if not is_langsmith_enabled():
        return None
    
    client = get_langsmith_client()
    if not client:
        return None
    
    try:
        tracer = LangChainTracer(
            client=client,
            project_name=settings.LANGSMITH_PROJECT,
        )
        return tracer
    except Exception as e:
        print(f"[LANGSMITH] Failed to initialize tracer: {e}")
        return None


def get_callback_manager() -> CallbackManager:
    """Get callback manager with LangSmith tracer if enabled."""
    callbacks = []
    
    if is_langsmith_enabled():
        tracer = get_langchain_tracer()
        if tracer:
            callbacks.append(tracer)
    
    return CallbackManager(callbacks=callbacks)
