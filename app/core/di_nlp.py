"""
NLP Dependencies for GeoVision Lab

This module provides NLP-related dependency providers (NER, embeddings).
Uses the DI container for clean, testable dependency injection.

Usage:
    from app.core.di_nlp import get_ner_pipeline, get_embeddings

    def some_operation(ner_pipeline=Depends(get_ner_pipeline)):
        ...

Testing:
    from app.core.di import container
    container.override(get_ner_pipeline, mock_pipeline)
"""

from typing import Any, Dict, Optional
from langchain_huggingface import HuggingFaceEmbeddings
from transformers import pipeline, AutoTokenizer, AutoModelForTokenClassification
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


def _get_container():
    """Lazy import to avoid circular dependency."""
    from app.core.di import container
    return container


def _create_embeddings() -> HuggingFaceEmbeddings:
    """Factory function to create embedding model."""
    logger.info(f"[DI] Loading embedding model: {settings.EMBEDDING_MODEL_NAME}")
    return HuggingFaceEmbeddings(model_name=settings.EMBEDDING_MODEL_NAME)


def get_embeddings() -> HuggingFaceEmbeddings:
    """Get embedding model (managed by DI container)."""
    return _get_container()._get_or_create(get_embeddings, _create_embeddings)


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
    return _get_container()._get_or_create(get_ner_pipeline, _create_ner_pipeline)


def get_geocode_cache() -> Dict[str, Optional[list]]:
    """
    Get geocoding cache.

    Note: This returns a new dict per call for request isolation.
    For production, consider using Redis or request-scoped caching.
    """
    return {}
