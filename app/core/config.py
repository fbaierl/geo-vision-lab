from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
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
    LLM_MODEL_NAME: str = "qwen3.5:9b"
    REVIEWER_LLM_MODEL_NAME: str = "qwen2.5:0.5b"
    EMBEDDING_MODEL_NAME: str = "all-MiniLM-L6-v2"

    # --- RAG Settings ---
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200
    VECTOR_COLLECTION_NAME: str = "historical_reports"
    SEARCH_K: int = 3  # Number of docs to retrieve

    # --- Security ---
    SECRET_KEY: str = "changeme_in_production"
    API_KEY: Optional[str] = None

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
