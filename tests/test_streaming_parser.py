import pytest
from app.services.streaming import StreamingResponseParser

def test_parser_basic_tokens():
    parser = StreamingResponseParser()
    events = list(parser.process_chunk("Hello world"))
    
    types = [e["type"] for e in events]
    assert "status" in types
    assert "token" in types
    assert events[-1]["content"] == "Hello world"

def test_parser_thinking_tags():
    parser = StreamingResponseParser()
    
    # 1. Start thinking
    events = list(parser.process_chunk("<think>Searching..."))
    assert any(e["type"] == "thinking_start" for e in events)
    assert any(e["type"] == "thinking_token" and e["content"] == "Searching..." for e in events)
    
    # 2. More thinking
    events = list(parser.process_chunk(" logic"))
    assert events[0]["type"] == "thinking_token"
    assert events[0]["content"] == " logic"
    
    # 3. End thinking
    events = list(parser.process_chunk("</think>Answer"))
    assert any(e["type"] == "thinking_end" for e in events)
    assert any(e["type"] == "token" and e["content"] == "Answer" for e in events)

def test_parser_partial_tags():
    parser = StreamingResponseParser()
    
    # Split <think>
    events = list(parser.process_chunk("<thi"))
    assert not events  # Should buffer
    
    events = list(parser.process_chunk("nk>Content"))
    assert events[0]["type"] == "thinking_start"
    assert events[1]["type"] == "thinking_token"
    assert events[1]["content"] == "Content"
    
    # Split </think>
    events = list(parser.process_chunk("</thi"))
    assert not events  # Should buffer
    
    events = list(parser.process_chunk("nk>Final"))
    assert any(e["type"] == "thinking_end" for e in events)
    assert any(e["type"] == "token" and e["content"] == "Final" for e in events)

def test_parser_artifact_cleanup():
    parser = StreamingResponseParser()
    events = list(parser.process_chunk("<tool_code>import os</tool_code>Real Content"))
    
    all_content = "".join([e["content"] for e in events if e["type"] == "token"])
    assert "import os" not in all_content
    assert "Real Content" in all_content

def test_parser_multiple_think_blocks():
    parser = StreamingResponseParser()
    
    chunk = "<think>first</think>middle<think>second</think>end"
    events = list(parser.process_chunk(chunk))
    
    types = [e["type"] for e in events]
    assert types.count("thinking_start") == 2
    assert types.count("thinking_end") == 2
    assert any(e.get("content") == "middle" for e in events)
    assert any(e.get("content") == "end" for e in events)
