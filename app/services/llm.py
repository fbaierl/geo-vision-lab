from langchain_ollama import ChatOllama
from app.core.config import settings


def get_llm() -> ChatOllama:
    return ChatOllama(model=settings.LLM_MODEL_NAME, base_url=settings.OLLAMA_URL)


def get_reasoning_llm() -> ChatOllama:
    """Get the LLM for reasoning tasks (switchable between 9B, 4B, 0.8B)."""
    return ChatOllama(model=settings.REASONING_LLM_MODEL_NAME, base_url=settings.OLLAMA_URL)


def get_reviewer_llm() -> ChatOllama:
    """Get the LLM for QA review (with timeout to prevent hanging)."""
    return ChatOllama(
        model=settings.REVIEWER_LLM_MODEL_NAME,
        base_url=settings.OLLAMA_URL,
        num_predict=50,  # Limit response length for reviewer
        timeout=30  # 30 second timeout
    )
