from unittest.mock import patch, MagicMock
from langchain_core.messages import HumanMessage
from app.agents.graph import should_continue, call_model

# --- should_continue node tests ---

def test_should_continue_with_tools():
    # When the last message has tool calls, we should go to 'tools'
    mock_message = MagicMock()
    mock_message.tool_calls = [{"name": "web_search", "args": {"query": "NATO"}}]
    state = {"messages": [mock_message]}
    
    result = should_continue(state)
    assert result == "tools"

def test_should_continue_without_tools():
    # When the last message has no tool calls, we should end
    mock_message = MagicMock()
    mock_message.tool_calls = []
    state = {"messages": [mock_message]}
    
    result = should_continue(state)
    assert result == "reviewer"


# --- call_model node tests ---

@patch("app.agents.graph.get_reasoning_llm")
def test_call_model(mock_get_reasoning_llm):
    # Mock LLM and its response
    mock_llm = MagicMock()
    mock_llm_with_tools = MagicMock()
    
    # Setup chain
    mock_get_reasoning_llm.return_value = mock_llm
    mock_llm.bind_tools.return_value = mock_llm_with_tools
    
    # Mock response
    mock_response = MagicMock()
    mock_response.content = "I have the answer."
    mock_llm_with_tools.invoke.return_value = mock_response

    state = {"messages": [HumanMessage(content="Hello")]}
    
    result = call_model(state)
    
    assert "messages" in result
    assert result["messages"][0].content == "I have the answer."
    mock_llm.bind_tools.assert_called_once()
    mock_llm_with_tools.invoke.assert_called_once()
