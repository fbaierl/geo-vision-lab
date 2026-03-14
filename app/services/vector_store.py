from typing import List, Dict, Any
from pymongo import MongoClient
from pymongo.operations import SearchIndexModel
from langchain_huggingface import HuggingFaceEmbeddings
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

# Shared embedding model (loaded once at startup)
_embeddings = HuggingFaceEmbeddings(model_name=settings.EMBEDDING_MODEL_NAME)

# Shared MongoDB client (singleton pattern)
_client = None
_db = None


def get_mongo_client() -> MongoClient:
    """Get or create MongoDB client singleton."""
    global _client
    if _client is None:
        # Use directConnection for non-Docker environments
        _client = MongoClient(settings.DATABASE_URL, directConnection=True)
    return _client


def get_database():
    """Get or create database singleton."""
    global _db
    if _db is None:
        _db = get_mongo_client()[settings.MONGODB_DB]
    return _db


def get_collection():
    """Get the vector collection."""
    return get_database()[settings.VECTOR_COLLECTION_NAME]


def ensure_vector_index():
    """Create vector search index if it doesn't exist."""
    db = get_database()
    collection_name = settings.VECTOR_COLLECTION_NAME
    
    # Ensure collection exists before creating index
    if collection_name not in db.list_collection_names():
        logger.info(f"[VECTOR] Creating collection '{collection_name}'...")
        db.create_collection(collection_name)
        
    collection = get_collection()
    
    try:
        # List existing search indexes
        existing_indexes = list(collection.list_search_indexes())
        
        # Check if our vector index already exists
        for idx in existing_indexes:
            if idx.get("name") == settings.VECTOR_INDEX_NAME:
                logger.info(f"[VECTOR] Vector search index '{settings.VECTOR_INDEX_NAME}' already exists")
                return  # Index already exists
        
        logger.info(f"[VECTOR] Creating vector search index '{settings.VECTOR_INDEX_NAME}'...")
        
        # Create vector search index for MongoDB Atlas Vector Search
        # Using lucene vector index with cosine similarity
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
        logger.info(f"[VECTOR] Vector search index '{settings.VECTOR_INDEX_NAME}' created successfully")
        
        # Wait for index to reach READY status
        import time
        max_attempts = 60  # Up to 60 seconds
        for attempt in range(max_attempts):
            indexes = list(collection.list_search_indexes())
            for idx in indexes:
                if idx.get("name") == settings.VECTOR_INDEX_NAME:
                    status = idx.get("status", "UNKNOWN")
                    logger.info(f"[VECTOR] Index status: {status} (attempt {attempt + 1}/{max_attempts})")
                    if status == "READY":
                        logger.info("[VECTOR] Index is READY for use")
                        return
            time.sleep(2)
        
        logger.warning("[VECTOR] Index may still be building — search may not work immediately")
        
    except Exception as e:
        logger.error(f"[VECTOR] Error creating vector index: {e}")
        raise


def embed_documents(texts: List[str]) -> List[List[float]]:
    """Embed multiple documents using the shared embedding model."""
    return _embeddings.embed_documents(texts)


def embed_query(text: str) -> List[float]:
    """Embed a single query using the shared embedding model."""
    return _embeddings.embed_query(text)


def insert_documents(documents: List[Dict[str, Any]]) -> None:
    """Insert documents with embeddings into MongoDB collection."""
    collection = get_collection()
    
    # Clear existing documents in the collection
    collection.delete_many({})
    
    # Prepare documents with embeddings
    texts = [doc["page_content"] for doc in documents]
    embeddings = embed_documents(texts)
    
    # Add embeddings to documents
    docs_with_embeddings = []
    for doc, embedding in zip(documents, embeddings):
        doc_copy = doc.copy()
        doc_copy["embedding"] = embedding
        docs_with_embeddings.append(doc_copy)
    
    # Bulk insert
    if docs_with_embeddings:
        collection.insert_many(docs_with_embeddings)
        logger.info(f"[VECTOR] Inserted {len(docs_with_embeddings)} documents with embeddings")


def similarity_search(query: str, k: int = 3) -> List[Dict[str, Any]]:
    """Perform vector similarity search using MongoDB vector search."""
    collection = get_collection()

    # Embed the query
    query_embedding = embed_query(query)

    # Perform vector search using MongoDB's $vectorSearch aggregation
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
            "$unset": ["embedding", "_id"]  # Remove embedding and _id from results
        }
    ]

    results = list(collection.aggregate(pipeline))
    return results
