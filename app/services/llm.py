from langchain_ollama import ChatOllama
from app.core.config import settings


def get_llm() -> ChatOllama:
    """Get the default LLM for general tasks."""
    return ChatOllama(model=settings.LLM_MODEL_NAME, base_url=settings.OLLAMA_URL)


def get_reasoning_llm() -> ChatOllama:
    """Get the LLM for reasoning tasks (configurable: 9B/4B/0.8B)."""
    return ChatOllama(model=settings.REASONING_LLM_MODEL_NAME, base_url=settings.OLLAMA_URL)


def get_reviewer_llm() -> ChatOllama:
    """Get the LLM for QA review (with timeout to prevent hanging)."""
    return ChatOllama(
        model=settings.REVIEWER_LLM_MODEL_NAME,
        base_url=settings.OLLAMA_URL,
        num_predict=20,  # Short responses for reviewer
        timeout=60  # 60 second timeout
    )


def get_qa_llm() -> ChatOllama:
    """Get a small, fast LLM for simple QA/validation tasks.
    
    Uses Qwen 0.8B for fast responses on simple tasks like:
    - Yes/no validation
    - Simple fact checking
    - Binary classification
    """
    return ChatOllama(
        model="qwen3.5:0.8b",
        base_url=settings.OLLAMA_URL,
        num_predict=512,
        timeout=30
    )
