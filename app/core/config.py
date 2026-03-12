from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    # --- App Info ---
    APP_NAME: str = "GeoVision Lab"
    DEBUG: bool = False
    VERSION: str = "0.3.0"

    # --- Database ---
    MONGODB_SERVER: str = "geovision-mongodb"  # Docker service name
    MONGODB_PORT: str = "27017"
    MONGODB_DB: str = "geovision"

    @property
    def DATABASE_URL(self) -> str:
        return f"mongodb://{self.MONGODB_SERVER}:{self.MONGODB_PORT}/{self.MONGODB_DB}"

    # --- LLM & Embedding ---
    OLLAMA_BASE_URL: str = "http://geovision-ollama:11434"
    LLM_MODEL_NAME: str = "qwen3.5:4b"
    REASONING_LLM_MODEL_NAME: str = "qwen3.5:4b"  # Switchable: qwen3.5:9b, qwen3.5:4b, qwen3.5:0.8b
    REVIEWER_LLM_MODEL_NAME: str = "qwen2.5:0.5b"  # Fixed for QA
    EMBEDDING_MODEL_NAME: str = "all-MiniLM-L6-v2"

    # --- Available Reasoning Models ---
    AVAILABLE_REASONING_MODELS: list[str] = ["qwen3.5:9b", "qwen3.5:4b", "qwen3.5:0.8b"]

    # --- RAG Settings ---
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200
    VECTOR_COLLECTION_NAME: str = "historical_reports"
    SEARCH_K: int = 3  # Number of docs to retrieve
    VECTOR_INDEX_NAME: str = "vector_index"
    EMBEDDING_DIMENSIONS: int = 384  # all-MiniLM-L6-v2 produces 384-dim vectors

    # --- Security ---
    SECRET_KEY: str = "changeme_in_production"
    API_KEY: Optional[str] = None

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"

    def set_reasoning_model(self, model_name: str) -> bool:
        """Update the reasoning model name at runtime."""
        if model_name in self.AVAILABLE_REASONING_MODELS:
            self.REASONING_LLM_MODEL_NAME = model_name
            return True
        return False


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
