from langchain_postgres import PGVector
from langchain_community.embeddings import HuggingFaceEmbeddings
from app.core.config import settings

# Shared embedding model (loaded once at startup)
_embeddings = HuggingFaceEmbeddings(model_name=settings.EMBEDDING_MODEL_NAME)

def get_vector_store() -> PGVector:
    return PGVector(
        embeddings=_embeddings,
        connection=settings.DATABASE_URL,
        collection_name=settings.VECTOR_COLLECTION_NAME,
    )
