"""
Core package for GeoVision Lab

Provides configuration and dependency injection infrastructure.
"""

from app.core.config import settings, get_settings, Settings
from app.core.di import (
    container,
    get_mongo_client,
    get_database,
    get_collection,
    get_embeddings,
    get_reasoning_llm,
    get_reviewer_llm,
    get_ner_pipeline,
    get_geocode_cache,
    get_vector_store_service,
    get_location_extractor_service,
    ensure_vector_index,
)

__all__ = [
    "settings",
    "get_settings",
    "Settings",
    "container",
    "get_mongo_client",
    "get_database",
    "get_collection",
    "get_embeddings",
    "get_reasoning_llm",
    "get_reviewer_llm",
    "get_ner_pipeline",
    "get_geocode_cache",
    "get_vector_store_service",
    "get_location_extractor_service",
    "ensure_vector_index",
]
