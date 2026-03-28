"""
Service Dependencies for GeoVision Lab

This module provides service-level dependency providers (VectorStore, LocationExtractor, etc.).
Uses the DI container for clean, testable dependency injection.

Usage:
    from app.core.di_services import get_vector_store, get_location_extractor

    def some_operation(vector_store=Depends(get_vector_store)):
        ...

Testing:
    from app.core.di import container
    container.override(get_vector_store, mock_service)
"""

import logging
from typing import Any

from app.core.di_database import get_mongo_client, get_collection
from app.core.di_nlp import get_embeddings, get_ner_pipeline, get_geocode_cache
from app.core.di_llm import get_llm

logger = logging.getLogger(__name__)


def get_vector_store() -> Any:
    """Get vector store service instance."""
    from app.services.vector_store import VectorStoreService
    return VectorStoreService(
        embeddings=get_embeddings(),
        client=get_mongo_client(),
        collection=get_collection()
    )


def get_location_extractor() -> Any:
    """Get location extractor service instance."""
    from app.services.location_extractor import LocationExtractorService
    return LocationExtractorService(
        ner_pipeline=get_ner_pipeline(),
        geocode_cache=get_geocode_cache()
    )


def get_location_prioritizer() -> Any:
    """Get location prioritizer service instance."""
    from app.services.location_prioritizer import LocationPrioritizerService
    return LocationPrioritizerService(llm=get_llm())


def ensure_vector_index() -> None:
    """Create vector search index if it doesn't exist."""
    from app.core.di_database import ensure_vector_index as di_ensure_vector_index
    di_ensure_vector_index()
