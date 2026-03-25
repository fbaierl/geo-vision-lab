"""
Pytest fixtures and configuration for GeoVision Lab tests.

Provides dependency injection overrides for testing.
"""

import pytest
from unittest.mock import MagicMock
from app.core.di import container


@pytest.fixture(autouse=True)
def disable_langsmith_tracing(monkeypatch):
    """Disable LangSmith tracing for all tests to avoid cluttering the dashboard."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "LANGSMITH_TRACING", False)
    yield


@pytest.fixture(autouse=True)
def reset_di_container():
    """Reset DI container overrides after each test."""
    yield
    container.reset_overrides()


@pytest.fixture
def mock_mongo_client():
    """Create a mock MongoDB client for testing."""
    mock_client = MagicMock()
    mock_db = MagicMock()
    mock_collection = MagicMock()
    
    mock_client.__getitem__.return_value = mock_db
    mock_db.__getitem__.return_value = mock_collection
    mock_db.list_collection_names.return_value = []
    
    return mock_client


@pytest.fixture
def mock_embeddings():
    """Create a mock embeddings model for testing."""
    mock_emb = MagicMock()
    mock_emb.embed_documents.return_value = [[0.1] * 384]
    mock_emb.embed_query.return_value = [0.1] * 384
    return mock_emb


@pytest.fixture
def mock_reasoning_llm():
    """Create a mock reasoning LLM for testing."""
    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = "Mock reasoning response"
    mock_response.tool_calls = []
    mock_llm.invoke.return_value = mock_response
    mock_llm.bind_tools.return_value = mock_llm
    return mock_llm


@pytest.fixture
def mock_reviewer_llm():
    """Create a mock reviewer LLM for testing."""
    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = '[{"name": "Test", "relevance": 1.0}]'
    mock_llm.invoke.return_value = mock_response
    return mock_llm


@pytest.fixture
def mock_ner_pipeline():
    """Create a mock NER pipeline for testing."""
    mock_pipeline = MagicMock()
    mock_pipeline.return_value = [
        {"entity_group": "GPE", "word": "Test Location", "entity_text": "Test Location"}
    ]
    return mock_pipeline


@pytest.fixture
def override_mongo(mock_mongo_client):
    """Override MongoDB client with mock."""
    from app.core.di import get_mongo_client
    container.override(get_mongo_client, lambda: mock_mongo_client)
    return mock_mongo_client


@pytest.fixture
def override_embeddings(mock_embeddings):
    """Override embeddings with mock."""
    from app.core.di import get_embeddings
    container.override(get_embeddings, lambda: mock_embeddings)
    return mock_embeddings


@pytest.fixture
def override_reasoning_llm(mock_reasoning_llm):
    """Override reasoning LLM with mock."""
    from app.core.di import get_llm
    container.override(get_llm, lambda: mock_reasoning_llm)
    return mock_reasoning_llm


@pytest.fixture
def override_reviewer_llm(mock_reviewer_llm):
    """Override reviewer LLM with mock."""
    from app.core.di import get_llm
    container.override(get_llm, lambda: mock_reviewer_llm)
    return mock_reviewer_llm


@pytest.fixture
def override_ner_pipeline(mock_ner_pipeline):
    """Override NER pipeline with mock."""
    from app.core.di import get_ner_pipeline
    container.override(get_ner_pipeline, lambda: mock_ner_pipeline)
    return mock_ner_pipeline
