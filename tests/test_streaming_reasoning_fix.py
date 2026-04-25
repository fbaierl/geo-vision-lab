"""
Test to verify that tool_result events for 'reasoning' don't include content field.

This prevents the bug where reasoning/thinking content was displayed in the chat window.
"""

import pytest
from app.services.streaming import StreamingResponseParser


def test_thinking_block_does_not_include_content_in_tool_result():
    """Test that when a thinking block ends, the tool_result event doesn't have content."""
    parser = StreamingResponseParser()
    
    # Simulate streaming a thinking block
    events = list(parser.process_chunk("<think>This is my reasoning about the problem.</think>"))
    
    # Find the tool_result event for reasoning
    tool_result_events = [e for e in events if e.get("type") == "tool_result" and e.get("tool") == "reasoning"]
    
    assert len(tool_result_events) == 1, f"Expected 1 tool_result event, got {len(tool_result_events)}"
    
    tool_result = tool_result_events[0]
    
    # Verify that 'content' field is NOT present
    assert "content" not in tool_result, \
        f"tool_result event should NOT have 'content' field, but got: {tool_result}"
    
    # Verify that 'summary' field IS present
    assert "summary" in tool_result, "tool_result event should have 'summary' field"
    assert tool_result["summary"] == "Reasoning steps completed"


def test_flush_does_not_include_content_in_tool_result():
    """Test that when flushing remaining content, tool_result doesn't have content."""
    parser = StreamingResponseParser()
    
    # Set up parser state as if it was in a thinking block
    parser.in_think = True
    parser.think_buffer = "Some thinking content"
    parser.buffer = "remaining thinking"
    
    # Flush the parser
    events = list(parser.flush())
    
    # Find the tool_result event for reasoning
    tool_result_events = [e for e in events if e.get("type") == "tool_result" and e.get("tool") == "reasoning"]
    
    assert len(tool_result_events) == 1, f"Expected 1 tool_result event, got {len(tool_result_events)}"
    
    tool_result = tool_result_events[0]
    
    # Verify that 'content' field is NOT present
    assert "content" not in tool_result, \
        f"tool_result event should NOT have 'content' field, but got: {tool_result}"


def test_thinking_tokens_are_still_sent():
    """Test that thinking tokens are still properly sent via thinking_* events."""
    parser = StreamingResponseParser()
    
    # Simulate streaming a thinking block
    events = list(parser.process_chunk("<think>Let me think about this.</think>"))
    
    # Verify thinking_start is sent
    assert any(e.get("type") == "thinking_start" for e in events), \
        "thinking_start event should be sent"
    
    # Verify thinking_token is sent with content
    thinking_tokens = [e for e in events if e.get("type") == "thinking_token"]
    assert len(thinking_tokens) > 0, "thinking_token events should be sent"
    
    # Verify the thinking content is in the tokens
    all_thinking_content = "".join(e.get("content", "") for e in thinking_tokens)
    assert "Let me think about this." in all_thinking_content, \
        "Thinking content should be sent via thinking_token events"


def test_regular_tokens_still_work():
    """Test that regular (non-thinking) tokens are still sent as token events."""
    parser = StreamingResponseParser()
    
    # Simulate streaming regular content
    events = list(parser.process_chunk("This is a regular response."))
    
    # Verify token event is sent
    token_events = [e for e in events if e.get("type") == "token"]
    assert len(token_events) == 1, f"Expected 1 token event, got {len(token_events)}"
    assert token_events[0]["content"] == "This is a regular response."


def test_mixed_thinking_and_regular_content():
    """Test that both thinking and regular content are properly handled."""
    parser = StreamingResponseParser()
    
    # Simulate streaming mixed content
    all_events = []
    chunks = [
        "<think>Thinking about",
        " the problem.</think>This is the ",
        "actual response."
    ]
    
    for chunk in chunks:
        events = list(parser.process_chunk(chunk))
        all_events.extend(events)
    
    # Verify thinking events are sent
    assert any(e.get("type") == "thinking_start" for e in all_events)
    assert any(e.get("type") == "thinking_end" for e in all_events)
    
    # Verify tool_result doesn't have content
    tool_result_events = [e for e in all_events if e.get("type") == "tool_result" and e.get("tool") == "reasoning"]
    assert len(tool_result_events) == 1
    assert "content" not in tool_result_events[0]
    
    # Verify response tokens are sent
    response_tokens = [e for e in all_events if e.get("type") == "token"]
    response_text = "".join(e.get("content", "") for e in response_tokens)
    assert "This is the actual response." in response_text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
