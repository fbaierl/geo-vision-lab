import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
from langchain_core.messages import AIMessageChunk
from app.services.streaming import process_query_stream

@pytest.mark.asyncio
async def test_process_query_stream_thinking_tags_no_hang():
    """
    Test that process_query_stream correctly handles <think> tags without hanging.
    This is a regression test for the while...else indentation bug.
    """
    user_query = "Who are Stalin's children?"
    
    # Mock the graph
    mock_graph = MagicMock()
    
    # Define a sequence of events mimicking a real stream with <think> tags
    async def mock_astream_events(*args, **kwargs):
        # 1. Start event
        yield {"event": "on_chain_start", "name": "LangGraph", "data": {}, "tags": []}
        
        # 2. Model start
        yield {"event": "on_chat_model_start", "name": "ChatGroq", "data": {}, "tags": ["seq:step:1"]}
        
        # 3. Model stream chunks
        chunks = [
            "<think>", "Stalin", " had", " several", " children.", "</think>", 
            "Joseph", " Stalin", " had", "..."
        ]
        
        for i, chunk_text in enumerate(chunks):
            yield {
                "event": "on_chat_model_stream",
                "name": "ChatGroq",
                "tags": ["seq:step:1"],
                "data": {
                    "chunk": AIMessageChunk(content=chunk_text)
                }
            }
        
        # 4. Model end
        yield {"event": "on_chat_model_end", "name": "ChatGroq", "data": {"output": AIMessageChunk(content="".join(chunks))}, "tags": ["seq:step:1"]}
        
        # 5. End event
        yield {"event": "on_chain_end", "name": "LangGraph", "data": {"output": {}}, "tags": []}

    mock_graph.astream_events = mock_astream_events
    
    # Use a timeout to detect hangs
    try:
        events = []
        async with asyncio.timeout(2.0):  # 2 seconds is plenty for this mock
            async for event in process_query_stream(user_query, thread_id="test", graph_override=mock_graph):
                events.append(event)
    except asyncio.TimeoutError:
        pytest.fail("process_query_stream hung (likely infinite loop in buffer processing)")

    # Verify we got the expected thinking events
    event_types = [e["type"] for e in events]
    assert "thinking_start" in event_types
    assert "thinking_token" in event_types
    assert "thinking_end" in event_types
    
    # Verify we got the final tokens
    tokens = [e["content"] for e in events if e["type"] == "token"]
    assert any("Joseph" in t for t in tokens)

@pytest.mark.asyncio
async def test_process_query_stream_partial_tags():
    """
    Test that process_query_stream handles tags split across chunks correctly.
    """
    user_query = "test"
    mock_graph = MagicMock()
    
    async def mock_astream_events(*args, **kwargs):
        # Split tags across chunks
        chunks = ["<thi", "nk>", "content", "</thi", "nk>", " final"]
        for chunk in chunks:
            yield {
                "event": "on_chat_model_stream",
                "name": "ChatGroq",
                "tags": [],
                "data": {"chunk": AIMessageChunk(content=chunk)}
            }

    mock_graph.astream_events = mock_astream_events
    
    events = []
    async for event in process_query_stream(user_query, thread_id="test", graph_override=mock_graph):
        events.append(event)
        
    event_types = [e["type"] for e in events]
    assert "thinking_start" in event_types
    assert "thinking_end" in event_types
    
    # Final token check
    tokens = "".join([e["content"] for e in events if e["type"] == "token"])
    assert "final" in tokens
