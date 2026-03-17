"""
Dependency Injection Container for GeoVision Lab

This module provides centralized dependency providers for all services.
Uses FastAPI's Depends() pattern for clean, testable dependency injection.

Usage:
    from fastapi import Depends
    from app.core.di import get_mongo_client, get_vector_store, get_location_extractor

    @router.post("/search")
    async def search(
        client: MongoClient = Depends(get_mongo_client),
        vector_store: VectorStore = Depends(get_vector_store)
    ):
        ...

Testing:
    from app.core.di import container

    def test_something():
        container.override(get_mongo_client, mock_client)
        # run test
        container.reset_overrides()
"""

from functools import lru_cache
from typing import Optional, Dict, Any, Callable
from pymongo import MongoClient
from langchain_ollama import ChatOllama
from langchain_huggingface import HuggingFaceEmbeddings
from transformers import pipeline, AutoTokenizer, AutoModelForTokenClassification
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


class DIContainer:
    """
    Simple dependency injection container with override support for testing.
    
    Unlike singletons, this container:
    - Makes dependencies explicit
    - Allows easy mocking in tests via override()
    - Supports proper lifecycle management
    """
    
    def __init__(self):
        self._overrides: Dict[Callable, Any] = {}
        self._instances: Dict[Callable, Any] = {}
    
    def override(self, dependency: Callable, mock_or_factory: Any) -> None:
        """Override a dependency with a mock or factory (for testing)."""
        self._overrides[dependency] = mock_or_factory
        logger.debug(f"[DI] Overridden {dependency.__name__} with mock")
    
    def reset_overrides(self) -> None:
        """Remove all overrides (call after tests)."""
        self._overrides.clear()
        logger.debug("[DI] Reset all overrides")
    
    def _get_or_create(self, dependency: Callable, factory: Callable) -> Any:
        """Get overridden instance or create via factory."""
        if dependency in self._overrides:
            override = self._overrides[dependency]
            # If override is callable (factory), call it; otherwise return as-is
            if callable(override):
                return override()
            return override
        
        if dependency not in self._instances:
            self._instances[dependency] = factory()
        
        return self._instances[dependency]


# Global container instance
container = DIContainer()


# =============================================================================
# MongoDB Dependencies
# =============================================================================

def _create_mongo_client() -> MongoClient:
    """Factory function to create MongoDB client."""
    logger.info("[DI] Creating MongoDB client...")
    client = MongoClient(settings.DATABASE_URL, directConnection=True)
    return client


def get_mongo_client() -> MongoClient:
    """Get MongoDB client (managed by DI container)."""
    return container._get_or_create(get_mongo_client, _create_mongo_client)


def get_database() -> Any:
    """Get MongoDB database instance."""
    client = get_mongo_client()
    return client[settings.MONGODB_DB]


def get_collection() -> Any:
    """Get MongoDB collection."""
    db = get_database()
    return db[settings.VECTOR_COLLECTION_NAME]


# =============================================================================
# Embedding Model Dependencies
# =============================================================================

def _create_embeddings() -> HuggingFaceEmbeddings:
    """Factory function to create embedding model."""
    logger.info(f"[DI] Loading embedding model: {settings.EMBEDDING_MODEL_NAME}")
    return HuggingFaceEmbeddings(model_name=settings.EMBEDDING_MODEL_NAME)


def get_embeddings() -> HuggingFaceEmbeddings:
    """Get embedding model (managed by DI container)."""
    return container._get_or_create(get_embeddings, _create_embeddings)


# =============================================================================
# LLM Dependencies
# =============================================================================

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
    return container._get_or_create(get_reasoning_llm, _create_reasoning_llm)


def get_reviewer_llm() -> ChatOllama:
    """Get reviewer LLM (managed by DI container)."""
    return container._get_or_create(get_reviewer_llm, _create_reviewer_llm)


# =============================================================================
# NER Pipeline Dependencies
# =============================================================================

def _create_ner_pipeline() -> Any:
    """Factory function to load Hugging Face NER model."""
    logger.info("[DI] Loading NER model: dslim/bert-base-NER")
    
    model_name = "dslim/bert-base-NER"
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForTokenClassification.from_pretrained(model_name)
    
    ner_pipeline = pipeline(
        "ner",
        model=model,
        tokenizer=tokenizer,
        aggregation_strategy="simple"
    )
    
    return ner_pipeline


def get_ner_pipeline() -> Any:
    """Get NER pipeline (managed by DI container)."""
    return container._get_or_create(get_ner_pipeline, _create_ner_pipeline)


# =============================================================================
# Geocoding Cache (request-scoped)
# =============================================================================

def get_geocode_cache() -> Dict[str, Optional[list]]:
    """
    Get geocoding cache.
    
    Note: This returns a new dict per call for request isolation.
    For production, consider using Redis or request-scoped caching.
    """
    return {}


# =============================================================================
# Vector Store Service Dependencies
# =============================================================================

def get_vector_store() -> Any:
    """
    Get vector store service.
    
    Returns:
        VectorStoreService instance
    """
    from app.services.vector_store import VectorStoreService
    return VectorStoreService(
        embeddings=get_embeddings(),
        client=get_mongo_client(),
        collection=get_collection()
    )


def get_vector_store_service() -> Dict[str, Any]:
    """
    Get vector store service dependencies as a dict.
    
    Returns:
        Dict with 'embeddings', 'client', 'collection' keys
    """
    return {
        "embeddings": get_embeddings(),
        "client": get_mongo_client(),
        "collection": get_collection()
    }


# =============================================================================
# Location Extractor Service Dependencies
# =============================================================================

def get_location_extractor() -> Any:
    """
    Get location extractor service.
    
    Returns:
        LocationExtractorService instance
    """
    from app.services.location_extractor import LocationExtractorService
    return LocationExtractorService(
        ner_pipeline=get_ner_pipeline(),
        reviewer_llm=get_reviewer_llm(),
        geocode_cache=get_geocode_cache()
    )


def get_location_extractor_service() -> Dict[str, Any]:
    """
    Get location extractor service dependencies as a dict.
    
    Returns:
        Dict with 'ner_pipeline', 'geocode_cache', 'reviewer_llm' keys
    """
    return {
        "ner_pipeline": get_ner_pipeline(),
        "geocode_cache": get_geocode_cache(),
        "reviewer_llm": get_reviewer_llm()
    }


# =============================================================================
# Location Prioritizer Service Dependencies
# =============================================================================

def get_location_prioritizer() -> Any:
    """
    Get location prioritizer service.
    
    Returns:
        LocationPrioritizerService instance
    """
    from app.services.location_prioritizer import LocationPrioritizerService
    return LocationPrioritizerService(reviewer_llm=get_reviewer_llm())


# =============================================================================
# Helper for ensuring vector index exists at startup
# =============================================================================

def ensure_vector_index() -> None:
    """Create vector search index if it doesn't exist."""
    from pymongo.operations import SearchIndexModel
    
    db = get_database()
    collection = get_collection()
    
    # Ensure collection exists
    if settings.VECTOR_COLLECTION_NAME not in db.list_collection_names():
        logger.info(f"[DI] Creating collection '{settings.VECTOR_COLLECTION_NAME}'...")
        db.create_collection(settings.VECTOR_COLLECTION_NAME)
    
    try:
        existing_indexes = list(collection.list_search_indexes())
        
        for idx in existing_indexes:
            if idx.get("name") == settings.VECTOR_INDEX_NAME:
                logger.info(f"[DI] Vector index '{settings.VECTOR_INDEX_NAME}' already exists")
                return
        
        logger.info(f"[DI] Creating vector index '{settings.VECTOR_INDEX_NAME}'...")
        
        search_index_model = SearchIndexModel(
            definition={
                "fields": [
                    {
                        "type": "vector",
                        "numDimensions": settings.EMBEDDING_DIMENSIONS,
                        "path": "embedding",
                        "similarity": "cosine"
                    },
                    {
                        "type": "filter",
                        "path": "metadata.source"
                    }
                ]
            },
            name=settings.VECTOR_INDEX_NAME,
            type="vectorSearch",
        )
        
        collection.create_search_index(model=search_index_model)
        logger.info(f"[DI] Vector index '{settings.VECTOR_INDEX_NAME}' created")
        
        # Wait for index to be ready
        import time
        for attempt in range(60):
            indexes = list(collection.list_search_indexes())
            for idx in indexes:
                if idx.get("name") == settings.VECTOR_INDEX_NAME:
                    if idx.get("status") == "READY":
                        logger.info("[DI] Vector index is READY")
                        return
            time.sleep(2)
        
        logger.warning("[DI] Vector index may still be building")
        
    except Exception as e:
        logger.error(f"[DI] Error creating vector index: {e}")
        raise
