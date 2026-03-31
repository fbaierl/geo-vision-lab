"""
Database Dependencies for GeoVision Lab

This module provides MongoDB-related dependency providers.
Uses the DI container for clean, testable dependency injection.

Usage:
    from fastapi import Depends
    from app.core.di_database import get_mongo_client, get_database, get_collection

    def some_operation(client: MongoClient = Depends(get_mongo_client)):
        ...

Testing:
    from app.core.di import container
    container.override(get_mongo_client, mock_client)
    # run test
    container.reset_overrides()
"""

from typing import Any
from pymongo import MongoClient
from pymongo.operations import SearchIndexModel
import logging
import time

from app.core.config import settings

logger = logging.getLogger(__name__)


def _get_container():
    """Lazy import to avoid circular dependency."""
    from app.core.di import container

    return container


def _create_mongo_client() -> MongoClient:
    """Factory function to create MongoDB client."""
    logger.info("[DI] Creating MongoDB client...")
    client = MongoClient(settings.DATABASE_URL, directConnection=True)
    return client


def get_mongo_client() -> MongoClient:
    """Get MongoDB client (managed by DI container)."""
    return _get_container()._get_or_create(get_mongo_client, _create_mongo_client)


def get_database() -> Any:
    """Get MongoDB database instance."""
    client = get_mongo_client()
    return client[settings.MONGODB_DB]


def get_collection() -> Any:
    """Get MongoDB collection."""
    db = get_database()
    return db[settings.VECTOR_COLLECTION_NAME]


def ensure_vector_index() -> None:
    """Create vector search index if it doesn't exist."""
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
                logger.info(
                    f"[DI] Vector index '{settings.VECTOR_INDEX_NAME}' already exists"
                )
                return

        logger.info(f"[DI] Creating vector index '{settings.VECTOR_INDEX_NAME}'...")

        search_index_model = SearchIndexModel(
            definition={
                "fields": [
                    {
                        "type": "vector",
                        "numDimensions": settings.EMBEDDING_DIMENSIONS,
                        "path": "embedding",
                        "similarity": "cosine",
                    },
                    {"type": "filter", "path": "metadata.source"},
                ]
            },
            name=settings.VECTOR_INDEX_NAME,
            type="vectorSearch",
        )

        collection.create_search_index(model=search_index_model)
        logger.info(f"[DI] Vector index '{settings.VECTOR_INDEX_NAME}' created")

        # Wait for index to be ready
        for _ in range(60):
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
