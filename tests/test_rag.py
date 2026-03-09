from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock, MagicMock

# Import the FastAPI application
from app.main import app
import json

client = TestClient(app)


def test_read_root():
    # Make sure we don't actually crash if index.html is missing during tests
    with patch("builtins.open", mock_open(read_data=b"<html>UI</html>")):
        response = client.get("/")
        assert response.status_code == 200


@patch("app.api.routes.health.httpx.AsyncClient.get", new_callable=AsyncMock)
def test_system_status_idle(mock_get):
    # Mock Ollama API response for an idle GPU
    mock_response = MagicMock()
    mock_response.json.return_value = {"models": []}
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    with TestClient(app) as client:
        response = client.get("/system/status")
        assert response.status_code == 200
        data = response.json()
        assert data["gpu_engaged"] is False
        assert data["reason"] == "no_model_loaded"


@patch("app.api.routes.health.httpx.AsyncClient.get", new_callable=AsyncMock)
def test_system_status_engaged(mock_get):
    # Mock Ollama API response for engaged GPU
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "models": [{"name": "qwen3.5:4b", "size_vram": 5000000000}]
    }
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    with TestClient(app) as client:
        response = client.get("/system/status")
        assert response.status_code == 200
        data = response.json()
        assert data["gpu_engaged"] is True
        assert data["reason"] == "gpu"
        assert data["model"] == "qwen3.5:4b"


@patch("app.api.routes.chat.process_query")
def test_chat_non_streaming(mock_process_query):
    mock_process_query.return_value = "This is a mock response from the agent."
    
    response = client.post(
        "/chat",
        data={
            "query": "What happened during the Cold War?",
            "thread_id": "test-thread",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "answer" in data
    assert data["answer"] == "This is a mock response from the agent."
    assert data["thread_id"] == "test-thread"


@patch("app.api.routes.chat.process_query_stream")
def test_chat_streaming(mock_process_query_stream):
    # Mock the async generator to yield SSE events
    async def mock_generator(*args, **kwargs):
        yield {"type": "status", "phase": "reasoning"}
        yield {"type": "token", "content": "Hello "}
        yield {"type": "token", "content": "World!"}
        yield {"type": "done"}

    mock_process_query_stream.side_effect = mock_generator

    response = client.post(
        "/chat/stream", data={"query": "Stream this", "thread_id": "test-stream"}
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"

    content = response.text
    blocks = [line for line in content.split("\n\n") if line.strip()]

    assert "data:" in blocks[0]
    first_event = json.loads(blocks[0].replace("data: ", ""))
    assert first_event["type"] == "meta"
    assert first_event["thread_id"] == "test-stream"


def mock_open(*args, **kwargs):
    from unittest.mock import mock_open

    return mock_open(*args, **kwargs)
