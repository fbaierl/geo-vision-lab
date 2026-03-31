from unittest.mock import MagicMock
from langchain_core.messages import HumanMessage
from app.agents.graph import should_continue, call_model, vector_search_node


# --- should_continue node tests ---


def test_should_continue_with_tools():
    # When the last message has tool calls, we should go to 'tools'
    mock_message = MagicMock()
    mock_message.tool_calls = [{"name": "web_search", "args": {"query": "NATO"}}]
    state = {"messages": [mock_message]}

    result = should_continue(state)
    assert result == "tools"


def test_should_continue_without_tools():
    # When the last message has no tool calls, we should go to reviewer
    mock_message = MagicMock()
    mock_message.tool_calls = []
    state = {"messages": [mock_message]}

    result = should_continue(state)
    assert result == "reviewer"


# --- call_model node tests ---


def test_call_model(override_reasoning_llm):
    """Test call_model with DI override for reasoning LLM."""
    # Setup mock response
    mock_response = MagicMock()
    mock_response.content = "I have the answer."
    override_reasoning_llm.invoke.return_value = mock_response

    state = {"messages": [HumanMessage(content="Hello")]}
    result = call_model(state)

    assert "messages" in result
    assert result["messages"][0].content == "I have the answer."
    override_reasoning_llm.bind_tools.assert_called_once()


# --- vector_search_node tests ---


def test_vector_search_node_no_query():
    """Test vector_search_node with no query."""
    state = {"messages": []}
    result = vector_search_node(state)
    assert result["vector_search_results"] == "No query provided."
