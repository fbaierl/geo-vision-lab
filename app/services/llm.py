from langchain_ollama import ChatOllama
from app.core.config import settings


def get_llm() -> ChatOllama:
    return ChatOllama(model=settings.LLM_MODEL_NAME, base_url=settings.OLLAMA_BASE_URL)
