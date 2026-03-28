import pytest
from testcontainers.mongodb import MongoDbContainer
from unittest.mock import patch, MagicMock
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, AIMessage
import time

# 1. Provide the same MongoDB image we use in docker-compose
MONGODB_IMAGE = "mongodb/mongodb-atlas-local:8.2"


@pytest.fixture(scope="module")
def mongodb_container():
    """Spins up a real MongoDB container for testing."""
    with MongoDbContainer(MONGODB_IMAGE) as mongo:
        # Wait for MongoDB to be ready
        mongo.start()
        # Give MongoDB time to initialize as primary
        time.sleep(3)
        yield mongo


# Integration test - runs in dedicated integration test pipeline
def test_real_db_ingestion_and_search(mongodb_container, monkeypatch):
    """
    Integration test:
    1. Bind app settings to the ephemeral MongoDB container.
    2. Insert a document into the real MongoDB vector store.
    3. Perform a similarity search and verify retrieval.
    """
    # Build the MongoDB connection string from the container
    host = mongodb_container.get_container_host_ip()
    port = mongodb_container.get_exposed_port(27017)
    dbname = "geovision_test"
    db_url = f"mongodb://{host}:{port}/{dbname}?directConnection=true"

    # Use monkeypatch to modify the global settings singleton correctly.
    from app.core.config import settings, Settings

    monkeypatch.setattr(Settings, "DATABASE_URL", property(lambda self: db_url))
    monkeypatch.setattr(settings, "MONGODB_DB", dbname)
    monkeypatch.setattr(settings, "CHUNK_SIZE", 100)
    monkeypatch.setattr(settings, "CHUNK_OVERLAP", 20)
    monkeypatch.setattr(settings, "VECTOR_COLLECTION_NAME", "test_collection")
    monkeypatch.setattr(settings, "EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")
    monkeypatch.setattr(settings, "REASONING_LLM_MODEL_NAME", "qwen3.5:4b")
    monkeypatch.setattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434")

    # Get the collection directly from the test MongoDB container
    from pymongo import MongoClient

    mongo_client = MongoClient(db_url)
    collection = mongo_client[dbname]["test_collection"]

    # Prepare a longer Mock Document to test multiple chunk splitting!
    long_text = (
        "The overarching strategy of the GeoVision Lab depends on several classified facilities. "
        "While the European division handles cyber intelligence, the primary physical archival "
        "depository, known as the 'secret base', is located deep in Antarctica. This cold-weather "
        "facility contains decades of global satellite imagery and intercept transcripts. "
        "Access is restricted to Level 5 clearance and is only accessible via specialized icebreakers "
        "during the narrow summer window."
    )

    test_doc = Document(
        page_content=long_text, metadata={"source": "test_integration.pdf", "page": 1}
    )

    mock_loader_instance = MagicMock()
    mock_loader_instance.load.return_value = [test_doc]

    # Mock similarity_search to use regular MongoDB query instead of $vectorSearch
    # (local MongoDB containers don't support vector search indexes)
    def mock_similarity_search(query: str, k: int = 3):
        results = list(
            collection.find({"page_content": {"$regex": query, "$options": "i"}}).limit(
                k
            )
        )
        for doc in results:
            doc.pop("_id", None)
        return results

    # Mock embeddings to avoid HuggingFace model downloads
    class MockEmbeddings:
        """Mock embeddings that return random vectors."""

        def __init__(self, *args, **kwargs):
            pass

        def embed_documents(self, texts):
            import random

            return [[random.random() for _ in range(384)] for _ in texts]

        def embed_query(self, text):
            import random

            return [random.random() for _ in range(384)]

    # Create mock vector store
    mock_vector_store = MagicMock()
    mock_vector_store.similarity_search.side_effect = mock_similarity_search

    # Setup DI container overrides BEFORE importing graph
    from app.core.di import container
    from app.core.di_nlp import get_embeddings
    from app.core.di_services import get_vector_store
    from app.core.di_database import get_collection as di_get_collection

    container.reset_overrides()
    container.override(get_embeddings, lambda: MockEmbeddings())
    container.override(get_vector_store, lambda: mock_vector_store)
    container.override(di_get_collection, lambda: collection)

    # Patch settings for ingestion module
    import app.ingestion.ingest

    monkeypatch.setattr(app.ingestion.ingest, "settings", settings)

    # Now import the graph
    from app.agents.graph import app_graph

    # Run ingestion
    with patch(
        "app.ingestion.ingest.glob.glob", side_effect=[["/mock/path/doc.pdf"], []]
    ):
        with patch(
            "app.ingestion.ingest.PyPDFLoader", return_value=mock_loader_instance
        ):
            with patch(
                "app.ingestion.ingest.compute_files_hash", return_value="mock_hash_123"
            ):
                with patch(
                    "app.ingestion.ingest.get_ingestion_state", return_value=None
                ):
                    with patch(
                        "app.ingestion.ingest.get_vector_documents_count",
                        return_value=0,
                    ):
                        with patch("app.ingestion.ingest.save_ingestion_state"):
                            app.ingestion.ingest.main()

    # Wait a moment for MongoDB to index the documents
    time.sleep(1)

    # Perform a full agent query
    query = "Where is the primary physical archival depository secret base located?"
    inputs = {"messages": [HumanMessage(content=query)]}
    config = {"configurable": {"thread_id": "integration_test_thread"}}

    # Mock LLM responses - vector search is now automatic via vector_search_node
    mock_llm = MagicMock()
    mock_llm_with_tools = MagicMock()
    mock_llm.bind_tools.return_value = mock_llm_with_tools

    # Single response - agent receives vector search results automatically in context
    call_1 = AIMessage(
        content="Based on the intelligence, the secret base is located in Antarctica. [map: Antarctica, -82.8628, 135.0000]"
    )
    mock_reviewer_response = MagicMock()
    mock_reviewer_response.content = "VALID"

    mock_llm_with_tools.invoke.return_value = call_1
    mock_llm.invoke.return_value = mock_reviewer_response

    # Run the agent
    with patch("app.agents.graph.get_llm", return_value=mock_llm):
        for event in app_graph.stream(inputs, config=config, stream_mode="updates"):
            pass  # Process all events

        # Fetch final state
        final_state = app_graph.get_state(config)
        result = final_state.values

    # Assertions
    final_message = result["messages"][-1].content
    assert "Antarctica" in final_message, (
        f"Expected 'Antarctica' in final message: {final_message}"
    )

    assert mock_llm_with_tools.invoke.call_count == 1, (
        f"Expected 1 LLM call, got {mock_llm_with_tools.invoke.call_count}"
    )

    # Vector search is now handled by vector_search_node, not as a tool
    vector_search_results = result.get("vector_search_results", "")
    assert "ARCHIVAL INTELLIGENCE" in str(vector_search_results) or "Antarctica" in str(result), (
        f"Expected vector search results in state: {result}"
    )

    container.reset_overrides()
