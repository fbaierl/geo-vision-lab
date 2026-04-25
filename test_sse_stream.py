"""
Test to verify that reasoning content doesn't appear in chat output.

This test:
1. Sends a query to the streaming endpoint
2. Parses the SSE events
3. Verifies that tool_result events for "reasoning" don't have content
4. Verifies that thinking content is properly sent via thinking_* events
"""

import asyncio
import httpx
import json
import pytest


@pytest.mark.asyncio
@pytest.mark.skip(reason="Requires running server on localhost:8000")
async def test_sse_stream_does_not_include_reasoning_content():
    """Test that the SSE stream doesn't include reasoning content in tool_result."""
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Send a query
        query = "What happened in Iran this week?"
        
        # POST to the chat stream endpoint
        # The endpoint is /chat/stream (POST with form data)
        try:
            # Use a timeout for the entire request
            try:
                async with client.stream(
                    "POST",
                    "http://localhost:8000/chat/stream",
                    data={"query": query, "thread_id": "test-thread-123"},
                    timeout=httpx.Timeout(timeout=5.0, connect=5.0)
                ) as response:
                    if response.status_code != 200:
                        print(f"Warning: /chat/stream returned {response.status_code}")
                        body = await response.aread()
                        print(f"Response: {body[:500]}")
                        return False
                    
                    # Parse SSE events with a timeout
                    events = []
                    reasoning_tool_results = []
                    
                    # Read for max 15 seconds
                    try:
                        async for line in response.aiter_lines():
                            line = line.strip()
                            if line.startswith('data: '):
                                data_str = line[6:]  # Remove 'data: ' prefix
                                try:
                                    event = json.loads(data_str)
                                    events.append(event)
                                    
                                    # Collect tool_result events for reasoning
                                    if event.get('type') == 'tool_result' and event.get('tool') == 'reasoning':
                                        reasoning_tool_results.append(event)
                                    
                                    # Stop when we get 'done' event
                                    if event.get('type') == 'done':
                                        break
                                        
                                except json.JSONDecodeError:
                                    pass
                    except httpx.ReadTimeout:
                        print("Timeout reading stream (this is OK if we got some events)")
                    
                    print(f"Total events: {len(events)}")
                    print(f"Reasoning tool_result events: {len(reasoning_tool_results)}")
                    
                    if not events:
                        print("❌ FAIL: No events received!")
                        return False
                    
                    # Verify that reasoning tool_result events don't have 'content'
                    for i, event in enumerate(reasoning_tool_results):
                        if 'content' in event:
                            print(f"❌ FAIL: Reasoning tool_result event {i} has 'content' field!")
                            print(f"   Event: {event}")
                            return False
                        else:
                            print(f"✅ Reasoning tool_result event {i} correctly has no 'content' field")
                    
                    # Verify that thinking_* events exist
                    thinking_events = [e for e in events if e.get('type') in ('thinking_start', 'thinking_token', 'thinking_end')]
                    if thinking_events:
                        print(f"✅ Found {len(thinking_events)} thinking events (thinking is properly sent separately)")
                    else:
                        print("⚠️  Warning: No thinking events found (might be using a model without thinking)")
                    
                    print("✅ Test passed: Reasoning content is not in tool_result events!")
                    return True
                    
            except httpx.ReadTimeout:
                print("Timeout on stream (might be OK if server is slow)")
                return False
                
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
            # Try to check if server is running
            try:
                health = await client.get("http://localhost:8000/system/status", timeout=3.0)
                print(f"Server is running, status: {health.status_code}")
            except Exception:
                print("Server doesn't seem to be running on port 8000")
                print("Please start the server and try again")
            return False


if __name__ == "__main__":
    result = asyncio.run(test_sse_stream_does_not_include_reasoning_content())
    if not result:
        exit(1)
