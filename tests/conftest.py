"""
Pytest fixtures and configuration for GeoVision Lab tests.

Provides dependency injection overrides for testing.
"""

import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from app.core.di import container
from app.main import app


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    with TestClient(app) as test_client:
        yield test_client


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
    """Create a mock MongoDB client for testing with in-memory storage."""

    # In-memory storage for sessions
    sessions_store = {}

    mock_client = MagicMock()
    mock_db = MagicMock()
    mock_collection = MagicMock()

    # Configure insert_one to store documents
    def insert_one(doc):
        if "thread_id" in doc:
            sessions_store[doc["thread_id"]] = doc.copy()
        return MagicMock(inserted_id=doc.get("thread_id"))

    # Configure find_one to retrieve documents
    def find_one(query):
        if "thread_id" in query:
            return sessions_store.get(query["thread_id"])
        return None

    # Configure find to return a cursor-like object
    def find(query, *args, **kwargs):
        if query == {}:
            # Return all sessions
            class MockCursor:
                def __iter__(self):
                    return iter(sessions_store.values())

                def sort(self, *args, **kwargs):
                    return self

            return MockCursor()
        elif "thread_id" in query:
            # Return matching session
            result = sessions_store.get(query["thread_id"])

            class MockCursor:
                def __iter__(self):
                    return iter([result]) if result else iter([])

                def sort(self, *args, **kwargs):
                    return self

            return MockCursor()
        return MagicMock(__iter__=lambda self: iter([]))

    # Configure update_one to update documents
    def update_one(query, update, upsert=False):
        if "thread_id" in query:
            thread_id = query["thread_id"]
            if thread_id in sessions_store:
                # Update existing
                if "$set" in update:
                    for key, value in update["$set"].items():
                        sessions_store[thread_id][key] = value
                return MagicMock(modified_count=1, upserted_id=None)
            elif upsert:
                # Create new
                sessions_store[thread_id] = {"thread_id": thread_id}
                if "$set" in update:
                    for key, value in update["$set"].items():
                        sessions_store[thread_id][key] = value
                return MagicMock(modified_count=0, upserted_id=thread_id)
        return MagicMock(modified_count=0, upserted_id=None)

    # Configure delete_one to remove documents
    def delete_one(query):
        if "thread_id" in query:
            thread_id = query["thread_id"]
            if thread_id in sessions_store:
                del sessions_store[thread_id]
                return MagicMock(deleted_count=1)
        return MagicMock(deleted_count=0)

    # Configure delete_many to remove all documents
    def delete_many(query):
        count = len(sessions_store)
        sessions_store.clear()
        return MagicMock(deleted_count=count)

    mock_collection.insert_one = insert_one
    mock_collection.find_one = find_one
    mock_collection.find = find
    mock_collection.update_one = update_one
    mock_collection.delete_one = delete_one
    mock_collection.delete_many = delete_many

    # Use attribute access (db.sessions) AND item access (db['sessions'])
    mock_client.__getitem__.return_value = mock_db
    mock_db.__getitem__.return_value = mock_collection
    mock_db.sessions = mock_collection  # For attribute access like db.sessions
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
    """Create a mock LLM for testing (single LLM for all tasks)."""
    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = "Mock response"
    mock_response.tool_calls = []
    mock_llm.invoke.return_value = mock_response
    mock_llm.bind_tools.return_value = mock_llm
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
    from app.core.di import container, get_mongo_client

    # Reset instances cache to ensure fresh mock is used
    container._instances.clear()
    container.override(get_mongo_client, lambda: mock_mongo_client)
    return mock_mongo_client


@pytest.fixture
def client_with_mongo_mock(override_mongo):
    """Create a test client with MongoDB mocked.

    This fixture ensures the MongoDB mock is set up BEFORE the client is created.
    Use this for tests that need MongoDB operations.
    """
    from app.main import app
    from fastapi.testclient import TestClient

    # override_mongo runs first due to dependency，ensuring mock is ready
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def override_embeddings(mock_embeddings):
    """Override embeddings with mock."""
    from app.core.di import get_embeddings

    container.override(get_embeddings, lambda: mock_embeddings)
    return mock_embeddings


@pytest.fixture
def override_reasoning_llm(mock_reasoning_llm):
    """Override LLM with mock (single LLM for all tasks)."""
    from app.core.di import get_llm

    container.override(get_llm, lambda: mock_reasoning_llm)
    return mock_reasoning_llm


@pytest.fixture
def override_ner_pipeline(mock_ner_pipeline):
    """Override NER pipeline with mock."""
    from app.core.di import get_ner_pipeline

    container.override(get_ner_pipeline, lambda: mock_ner_pipeline)
    return mock_ner_pipeline
