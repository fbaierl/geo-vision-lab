from pydantic_settings import BaseSettings
from pydantic import ConfigDict
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    model_config = ConfigDict(extra='ignore')
    
    # --- App Info ---
    APP_NAME: str = "GeoVision Lab"
    DEBUG: bool = False
    VERSION: str = "0.2.0"

    # --- Database ---
    POSTGRES_USER: str = "geovision"
    POSTGRES_PASSWORD: str = "geovision"
    POSTGRES_SERVER: str = "geovision-postgres"  # Docker service name
    POSTGRES_PORT: str = "5432"
    POSTGRES_DB: str = "geovision"

    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    # --- LLM & Embedding ---
    OLLAMA_BASE_URL: str = "http://geovision-ollama:11434"
    LLM_MODEL_NAME: str = "qwen3.5:4b"
    REASONING_LLM_MODEL_NAME: str = "qwen3.5:4b"  # Switchable: qwen3.5:9b, qwen3.5:4b, qwen3.5:0.8b
    REVIEWER_LLM_MODEL_NAME: str = "qwen3.5:0.8b"  # Fixed for QA/Review
    EMBEDDING_MODEL_NAME: str = "all-MiniLM-L6-v2"

    # --- Available Reasoning Models ---
    AVAILABLE_REASONING_MODELS: list = ["qwen3.5:9b", "qwen3.5:4b", "qwen3.5:0.8b"]

    # --- RAG Settings ---
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200
    VECTOR_COLLECTION_NAME: str = "historical_reports"
    SEARCH_K: int = 3  # Number of docs to retrieve

    # --- Security ---
    SECRET_KEY: str = "changeme_in_production"
    API_KEY: Optional[str] = None

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
