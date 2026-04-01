from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    # --- App Info ---
    APP_NAME: str = "GeoVision Lab"
    DEBUG: bool = False
    VERSION: str = "0.3.0"

    # --- Database ---
    # Support both MONGODB_URI (docker-compose) and MONGODB_SERVER (direct)
    MONGODB_URI: Optional[str] = None  # Full MongoDB URI from docker-compose
    MONGODB_SERVER: str = "localhost"  # Fallback for direct connection
    MONGODB_PORT: str = "27017"
    MONGODB_DB: str = "geovision"

    @property
    def DATABASE_URL(self) -> str:
        # Use MONGODB_URI if provided (docker-compose), otherwise build from components
        if self.MONGODB_URI:
            return self.MONGODB_URI
        return f"mongodb://{self.MONGODB_SERVER}:{self.MONGODB_PORT}/{self.MONGODB_DB}"

    # --- Graph Database (Neo4j) ---
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "geovision"

    # --- LLM & Embedding ---
    # Support both OLLAMA_HOST (docker-compose) and OLLAMA_BASE_URL (direct)
    OLLAMA_HOST: Optional[str] = None  # From docker-compose
    OLLAMA_BASE_URL: str = "http://localhost:11434"  # Fallback for direct connection

    @property
    def OLLAMA_URL(self) -> str:
        # Use OLLAMA_HOST if provided (docker-compose), otherwise use OLLAMA_BASE_URL
        if self.OLLAMA_HOST:
            return self.OLLAMA_HOST
        return self.OLLAMA_BASE_URL

    # --- LLM Models ---
    REASONING_LLM_MODEL_NAME: str = (
        "qwen3.5:4b"  # Default: qwen3.5:4b, switchable to qwen3.5:9b
    )
    EMBEDDING_MODEL_NAME: str = "all-MiniLM-L6-v2"

    # --- Online LLM (Groq) ---
    GROQ_API_KEY: Optional[str] = None
    USE_ONLINE_LLM: bool = False
    ONLINE_LLM_MODEL_NAME: str = "meta-llama/llama-4-scout-17b-16e-instruct"
    AVAILABLE_ONLINE_MODELS: list[str] = ["meta-llama/llama-4-scout-17b-16e-instruct"]

    # --- LangSmith Tracing (Cloud) ---
    # Get free API key at: https://smith.langchain.com
    LANGSMITH_TRACING: bool = False  # Set to True and add API key to enable
    LANGSMITH_API_KEY: Optional[str] = None
    LANGSMITH_PROJECT: str = "geo-vision-lab"
    LANGSMITH_ENDPOINT: str = "https://eu.api.smith.langchain.com"  # EU endpoint

    # --- Available Reasoning Models ---
    AVAILABLE_REASONING_MODELS: list[str] = ["qwen3.5:9b", "qwen3.5:4b"]

    # --- RAG Settings ---
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200
    VECTOR_COLLECTION_NAME: str = "vector_documents"
    SEARCH_K: int = 3  # Number of docs to retrieve
    VECTOR_INDEX_NAME: str = "vector_index"
    EMBEDDING_DIMENSIONS: int = 384  # all-MiniLM-L6-v2 produces 384-dim vectors

    # --- RAG Features (Runtime Toggles) ---
    RAG_GRADER_ENABLED: bool = False  # Enable/disable context grading
    RAG_RERANKER_ENABLED: bool = False  # Enable/disable BGE re-ranker
    RAG_RERANKER_MODEL: str = "BAAI/bge-reranker-v2-m3"
    RAG_RERANKER_TOP_K: int = 3  # Final results after re-ranking
    RAG_RERANKER_CANDIDATES_K: int = 20  # Candidates to retrieve for re-ranking

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

    def set_online_llm_enabled(self, enabled: bool) -> bool:
        """Enable or disable online LLM mode."""
        if enabled and not self.GROQ_API_KEY:
            return False  # Cannot enable without API key
        self.USE_ONLINE_LLM = enabled
        return True

    def set_online_llm_model(self, model_name: str) -> bool:
        """Set the online LLM model name."""
        if model_name in self.AVAILABLE_ONLINE_MODELS:
            self.ONLINE_LLM_MODEL_NAME = model_name
            return True
        return False

    def is_groq_api_key_configured(self) -> bool:
        """Check if Groq API key is configured."""
        return bool(self.GROQ_API_KEY and self.GROQ_API_KEY.strip())

    def set_rag_grader_enabled(self, enabled: bool) -> None:
        """Enable or disable RAG grader at runtime."""
        self.RAG_GRADER_ENABLED = enabled

    def set_rag_reranker_enabled(self, enabled: bool) -> None:
        """Enable or disable RAG re-ranker at runtime."""
        self.RAG_RERANKER_ENABLED = enabled

    def get_rag_config(self) -> dict:
        """Get current RAG configuration."""
        return {
            "grader_enabled": self.RAG_GRADER_ENABLED,
            "reranker_enabled": self.RAG_RERANKER_ENABLED,
            "reranker_model": self.RAG_RERANKER_MODEL,
            "reranker_top_k": self.RAG_RERANKER_TOP_K,
            "reranker_candidates_k": self.RAG_RERANKER_CANDIDATES_K,
        }


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
