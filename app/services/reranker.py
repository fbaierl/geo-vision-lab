"""
Re-ranker Service for GeoVision Lab

Provides document re-ranking using BGE cross-encoder models.
Re-ranking improves retrieval precision by scoring query-document pairs jointly.

Usage:
    from app.services.reranker import get_reranker_service

    service = get_reranker_service()
    results = service.rerank(query, documents, top_k=3)
"""

from typing import List, Dict, Any, Optional
import logging
import numpy as np

logger = logging.getLogger(__name__)


class ReRankerService:
    """
    BGE Re-ranker service using cross-encoder models.

    Singleton pattern - model is loaded on first request and reused.
    """

    _instance: Optional["ReRankerService"] = None
    _model = None
    _model_name: str = ""

    def __new__(cls, model_name: str = "BAAI/bge-reranker-v2-m3"):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._model_name = model_name
        return cls._instance

    def _load_model(self) -> None:
        """Load the BGE re-ranker model on first request."""
        if self._model is not None:
            return

        try:
            from sentence_transformers import CrossEncoder

            logger.info(f"[RERANKER] Loading model: {self._model_name}")
            self._model = CrossEncoder(self._model_name)
            logger.info(f"[RERANKER] Model loaded successfully: {self._model_name}")

        except ImportError as e:
            logger.error(f"[RERANKER] sentence-transformers not installed: {e}")
            logger.warning(
                "[RERANKER] Re-ranking will be disabled. Install with: pip install sentence-transformers"
            )
            self._model = None

        except Exception as e:
            logger.error(f"[RERANKER] Failed to load model: {e}")
            self._model = None

    def rerank(
        self, query: str, documents: List[Dict[str, Any]], top_k: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Re-rank documents based on relevance to query.

        Args:
            query: The search query
            documents: List of document dicts with 'page_content' key
            top_k: Number of top results to return

        Returns:
            Re-ranked list of documents (top_k results)
        """
        if not documents:
            return []

        if len(documents) <= top_k:
            # No need to re-rank if we have fewer docs than top_k
            return documents

        # Load model if not already loaded
        if self._model is None:
            self._load_model()

        # If model failed to load, return original documents
        if self._model is None:
            logger.warning("[RERANKER] Model not available, returning original order")
            return documents[:top_k]

        try:
            # Prepare query-document pairs for cross-encoder
            pairs = [[query, doc.get("page_content", "")] for doc in documents]

            # Get relevance scores
            scores = self._model.predict(pairs)

            # Get indices sorted by score (descending)
            sorted_indices = np.argsort(scores)[::-1]

            # Take top_k and add scores to documents
            reranked = []
            for i, idx in enumerate(sorted_indices[:top_k]):
                doc = documents[idx].copy()
                doc["rerank_score"] = float(scores[idx])
                doc["rerank_rank"] = i + 1
                reranked.append(doc)

            logger.info(f"[RERANKER] Re-ranked {len(documents)} docs → top {top_k}")

            return reranked

        except Exception as e:
            logger.error(f"[RERANKER] Re-ranking failed: {e}")
            logger.exception("[RERANKER] Full stack trace:")
            # Fallback: return original top_k
            return documents[:top_k]

    def is_available(self) -> bool:
        """Check if re-ranker model is loaded and ready."""
        if self._model is None:
            self._load_model()
        return self._model is not None


# Singleton instance
_reranker_service: Optional[ReRankerService] = None


def get_reranker_service(
    model_name: str = "BAAI/bge-reranker-v2-m3",
) -> ReRankerService:
    """
    Get or create ReRankerService singleton.

    Args:
        model_name: Model to use (default: BAAI/bge-reranker-v2-m3)

    Returns:
        ReRankerService instance
    """
    global _reranker_service
    if _reranker_service is None:
        from app.core.config import settings

        model = model_name or settings.RAG_RERANKER_MODEL
        _reranker_service = ReRankerService(model)
    return _reranker_service


def rerank_documents(
    query: str, documents: List[Dict[str, Any]], top_k: int = 3
) -> List[Dict[str, Any]]:
    """
    Convenience function to re-rank documents.

    Args:
        query: Search query
        documents: Documents to re-rank
        top_k: Number of results to return

    Returns:
        Re-ranked documents
    """
    service = get_reranker_service()
    return service.rerank(query, documents, top_k)
