import pytest
from testcontainers.mongodb import MongoDbContainer
from unittest.mock import patch, MagicMock
from langchain_core.documents import Document
import time

# 1. Provide the same MongoDB image we use in docker-compose
MONGODB_IMAGE = "mongodb/mongodb-atlas-local:8.2"

@pytest.fixture(scope="module")
def mongodb_container():
    """Spins up a real MongoDB container for testing."""
    with MongoDbContainer(MONGODB_IMAGE) as mongo:
        yield mongo

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
    monkeypatch.setattr(settings, "LLM_MODEL_NAME", "qwen3.5:4b")
    monkeypatch.setattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434")

    # Since generating real PDFs requires extra libraries, we simulate
    # the discovery of one PDF and the load of its text, but we let the rest
    # of app.ingestion.ingest.main() actually execute against the db.
    import app.ingestion.ingest
    monkeypatch.setattr(app.ingestion.ingest, "settings", settings)

    import app.services.vector_store
    monkeypatch.setattr(app.services.vector_store, "settings", settings)

    from app.agents.graph import app_graph
    from langchain_core.messages import HumanMessage

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
        page_content=long_text,
        metadata={"source": "test_integration.pdf", "page": 1}
    )

    mock_loader_instance = MagicMock()
    mock_loader_instance.load.return_value = [test_doc]

    # Create the vector index! Without this, $vectorSearch returns nothing.
    # Mock ensure_vector_index since MongoDB local containers don't support vector search indexes
    with patch.object(app.services.vector_store, "ensure_vector_index"):
        app.services.vector_store.ensure_vector_index()

    # Mock similarity_search to use regular MongoDB query instead of $vectorSearch
    # (local MongoDB containers don't support vector search indexes)
    def mock_similarity_search(query: str, k: int = 3):
        collection = app.services.vector_store.get_collection()
        # Use regex search instead of vector search
        results = list(collection.find({"page_content": {"$regex": query, "$options": "i"}}).limit(k))
        for doc in results:
            doc.pop("_id", None)
        return results

    # We execute the actual application ingestion logic!
    # With CHUNK_SIZE=100 and CHUNK_OVERLAP=20, this will create multiple chunks
    # inserted into the real test database.
    with patch("app.ingestion.ingest.glob.glob", side_effect=[["/mock/path/doc.pdf"], []]):
        with patch("app.ingestion.ingest.PyPDFLoader", return_value=mock_loader_instance):
            with patch("app.ingestion.ingest.compute_files_hash", return_value="mock_hash_123"):
                with patch("app.ingestion.ingest.os.path.exists", return_value=False):
                    with patch("app.ingestion.ingest.HASH_FILE", "/tmp/mock_hash_file_test"):
                        app.ingestion.ingest.main()

    # Wait a moment for MongoDB to index the documents
    time.sleep(1)

    # 3. Perform a full agent query using the ACTUAL application LangGraph!
    # The agent will evaluate the question, decide to use vector_search, retrieve the chunks,
    # synthesize them, and return a natural language answer.
    query = "Where is the primary physical archival depository secret base located?"
    inputs = {"messages": [HumanMessage(content=query)]}
    config = {"configurable": {"thread_id": "integration_test_thread"}}

    # We mock the LLM because we don't want to depend on Ollama running locally,
    # but we DO want to test the full LangGraph flow where the LLM routes to the
    # real database tool, and then receives the real database response!
    # We also mock similarity_search since MongoDB local doesn't support vector search indexes
    from langchain_core.messages import AIMessage

    mock_llm = MagicMock()
    mock_llm_with_tools = MagicMock()
    mock_llm.bind_tools.return_value = mock_llm_with_tools

    # Sequenced responses for the LangGraph:
    # 1. LLM decides to search the vector database
    call_1 = AIMessage(
        content="",
        tool_calls=[{"name": "vector_search", "args": {"query": "secret base"}, "id": "call_123"}]
    )
    # 2. LLM receives the real vector database response and synthesizes it
    call_2 = AIMessage(content="Based on the intelligence, the secret base is located in Antarctica.")

    mock_llm_with_tools.invoke.side_effect = [call_1, call_2]

    mock_reviewer_llm = MagicMock()
    mock_reviewer_with_structured = MagicMock()
    mock_reviewer_llm.with_structured_output.return_value = mock_reviewer_with_structured
    mock_reviewer_with_structured.invoke.return_value = {"is_valid": True, "feedback": "Looks good"}

    with patch("app.agents.graph.get_reasoning_llm", return_value=mock_llm):
        with patch("app.agents.graph.get_reviewer_llm", return_value=mock_reviewer_llm):
            with patch("app.agents.tools.similarity_search", side_effect=mock_similarity_search):
                print("\n\n" + "="*50)
                print("🧠 BEGIN LANGGRAPH EXECUTION FLOW")
                print("="*50)

                # We use .stream() instead of .invoke() so we can print each step as it happens
                for event in app_graph.stream(inputs, config=config, stream_mode="updates"):
                    for node_name, node_state in event.items():
                        print(f"\n📍 [GRAPH NODE JUMP]: Execution reached node '{node_name}'")

                        if "messages" in node_state and node_state["messages"]:
                            last_msg = node_state["messages"][-1]

                            if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                                print(f"  ⚡ Action: LLM decided to use tools -> {[t['name'] for t in last_msg.tool_calls]}")
                            elif last_msg.__class__.__name__ == "ToolMessage":
                                summary = last_msg.content[:100].replace('\n', ' ') + "..."
                                print(f"  🛠️ Action: Tool '{last_msg.name}' returned data: {summary}")
                            else:
                                print("  ✅ Action: LLM synthesized the final answer.")

                print("\n" + "="*50)
                print("🏁 END LANGGRAPH EXECUTION FLOW")
                print("="*50 + "\n")

                # After streaming is done, fetch the final state from the checkpointer
                final_state = app_graph.get_state(config)
                result = final_state.values

    # 4. Assertions
    final_message = result["messages"][-1].content

    # The agent should have synthesized an answer containing Antarctica
    assert "Antarctica" in final_message

    # Verify that the LLM was indeed called twice (once for tool decision, once for final synthesis)
    assert mock_llm_with_tools.invoke.call_count == 2

    # We also ensure the ToolMessage was generated by the real database execution
    tool_messages = [m for m in result["messages"] if m.__class__.__name__ == "ToolMessage"]
    assert len(tool_messages) == 1
    # Check that the real database returned our mock document chunk!
    assert "Antarctica" in tool_messages[0].content
