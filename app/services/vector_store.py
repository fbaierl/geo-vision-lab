"""
Vector Store Service

Provides vector search, embedding, and document management using MongoDB.
All dependencies are injected via the DI container - no global state.
"""

from typing import List, Dict, Any
from pymongo import MongoClient
from langchain_huggingface import HuggingFaceEmbeddings
import logging

from app.core.di_services import get_vector_store_service

logger = logging.getLogger(__name__)


class VectorStoreService:
    """
    Vector store service with explicit dependencies.

    Usage:
        # With DI (recommended)
        from app.core.di_services import get_vector_store_service
        service = VectorStoreService(**get_vector_store_service())

        # Or with explicit dependencies
        service = VectorStoreService(embeddings=emb, client=client, collection=coll)
    """

    def __init__(
        self,
        embeddings: HuggingFaceEmbeddings,
        client: MongoClient,
        collection: Any
    ):
        self.embeddings = embeddings
        self.client = client
        self.collection = collection

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed multiple documents."""
        return self.embeddings.embed_documents(texts)

    def embed_query(self, text: str) -> List[float]:
        """Embed a single query."""
        return self.embeddings.embed_query(text)

    def insert_documents(self, documents: List[Dict[str, Any]]) -> None:
        """Insert documents with embeddings into MongoDB collection."""
        # Clear existing documents
        self.collection.delete_many({})

        # Prepare documents with embeddings
        texts = [doc["page_content"] for doc in documents]
        embeddings = self.embed_documents(texts)

        # Add embeddings to documents
        docs_with_embeddings = []
        for doc, embedding in zip(documents, embeddings):
            doc_copy = doc.copy()
            doc_copy["embedding"] = embedding
            docs_with_embeddings.append(doc_copy)

        # Bulk insert
        if docs_with_embeddings:
            self.collection.insert_many(docs_with_embeddings)
            logger.info(f"[VECTOR] Inserted {len(docs_with_embeddings)} documents")

    def similarity_search(self, query: str, k: int = 3) -> List[Dict[str, Any]]:
        """Perform vector similarity search."""
        from app.core.config import settings
        
        query_embedding = self.embed_query(query)

        pipeline = [
            {
                "$vectorSearch": {
                    "index": settings.VECTOR_INDEX_NAME,
                    "path": "embedding",
                    "queryVector": query_embedding,
                    "numCandidates": 100,
                    "limit": k
                }
            },
            {
                "$unset": ["embedding", "_id"]
            }
        ]

        results = list(self.collection.aggregate(pipeline))
        return results


# =============================================================================
# Backward-compatible functions (using DI internally)
# =============================================================================

def ensure_vector_index() -> None:
    """Create vector search index if it doesn't exist."""
    from app.core.di_services import ensure_vector_index as di_ensure_vector_index
    di_ensure_vector_index()


def get_vector_store() -> VectorStoreService:
    """
    Get vector store service with dependencies from DI container.

    This is the recommended way to get a VectorStoreService instance.
    """
    return VectorStoreService(**get_vector_store_service())


# Legacy function wrappers for backward compatibility
# These will be deprecated in future versions

def embed_documents(texts: List[str]) -> List[List[float]]:
    """Embed multiple documents (legacy wrapper)."""
    return get_vector_store().embed_documents(texts)


def embed_query(text: str) -> List[float]:
    """Embed a single query (legacy wrapper)."""
    return get_vector_store().embed_query(text)


def insert_documents(documents: List[Dict[str, Any]]) -> None:
    """Insert documents with embeddings (legacy wrapper)."""
    get_vector_store().insert_documents(documents)


def similarity_search(query: str, k: int = 3) -> List[Dict[str, Any]]:
    """Perform vector similarity search (legacy wrapper)."""
    return get_vector_store().similarity_search(query, k)
