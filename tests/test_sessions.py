"""
Tests for Session Persistence API

Tests the /api/sessions endpoints for CRUD operations.
"""

import asyncio
from uuid import uuid4


class TestSessionsAPI:
    """Test suite for session management API endpoints."""

    def test_create_session(self, client):
        """Test creating a new session."""
        response = client.post("/api/sessions", json={"title": "Test Session"})
        
        assert response.status_code == 200
        data = response.json()
        assert "thread_id" in data
        assert "created_at" in data

    def test_create_session_auto_title(self, client):
        """Test creating a session without title (auto-generated)."""
        response = client.post("/api/sessions", json={})
        
        assert response.status_code == 200
        data = response.json()
        assert "thread_id" in data

    def test_list_sessions_empty(self, client):
        """Test listing sessions when none exist."""
        response = client.get("/api/sessions")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_list_sessions(self, client):
        """Test listing sessions after creating some."""
        # Create a session
        create_response = client.post("/api/sessions", json={"title": "Test Session"})
        thread_id = create_response.json()["thread_id"]
        
        # List sessions
        list_response = client.get("/api/sessions")
        
        assert list_response.status_code == 200
        sessions = list_response.json()
        assert len(sessions) >= 1
        
        # Find our session
        session = next((s for s in sessions if s["thread_id"] == thread_id), None)
        assert session is not None
        assert session["title"] == "Test Session"

    def test_get_session(self, client):
        """Test getting a specific session."""
        # Create a session
        create_response = client.post("/api/sessions", json={"title": "Test Session"})
        thread_id = create_response.json()["thread_id"]
        
        # Get the session
        get_response = client.get(f"/api/sessions/{thread_id}")
        
        assert get_response.status_code == 200
        data = get_response.json()
        assert data["thread_id"] == thread_id
        assert data["title"] == "Test Session"
        assert "messages" in data
        assert "ontology" in data

    def test_get_session_not_found(self, client):
        """Test getting a non-existent session returns empty structure."""
        fake_id = str(uuid4())
        response = client.get(f"/api/sessions/{fake_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["thread_id"] == fake_id
        assert data["messages"] == []
        assert data["ontology"] == {"entities": {}, "links": {}}

    def test_update_session_title(self, client):
        """Test updating session title."""
        # Create a session
        create_response = client.post("/api/sessions", json={"title": "Old Title"})
        thread_id = create_response.json()["thread_id"]
        
        # Update title
        update_response = client.put(
            f"/api/sessions/{thread_id}",
            json={"title": "New Title"}
        )
        
        assert update_response.status_code == 200
        
        # Verify update
        get_response = client.get(f"/api/sessions/{thread_id}")
        data = get_response.json()
        assert data["title"] == "New Title"

    def test_update_session_ontology(self, client):
        """Test updating session ontology."""
        # Create a session
        create_response = client.post("/api/sessions", json={"title": "Test"})
        thread_id = create_response.json()["thread_id"]
        
        # Update ontology
        ontology = {
            "entities": {
                "ent-1": {"uuid": "ent-1", "name": "Germany", "type": "Location"}
            },
            "links": {}
        }
        update_response = client.put(
            f"/api/sessions/{thread_id}",
            json={"ontology": ontology}
        )
        
        assert update_response.status_code == 200
        
        # Verify update
        get_response = client.get(f"/api/sessions/{thread_id}")
        data = get_response.json()
        assert len(data["ontology"]["entities"]) == 1
        assert data["ontology"]["entities"]["ent-1"]["name"] == "Germany"

    def test_save_session_auto_save(self, client):
        """Test auto-save endpoint (called after each query)."""
        thread_id = str(uuid4())
        
        save_data = {
            "messages": [
                {"role": "user", "content": "What is the capital of France?"},
                {"role": "assistant", "content": "The capital of France is Paris."}
            ],
            "ontology": {
                "entities": {
                    "ent-1": {"uuid": "ent-1", "name": "France", "type": "Location"},
                    "ent-2": {"uuid": "ent-2", "name": "Paris", "type": "Location"}
                },
                "links": {
                    "link-1": {"uuid": "link-1", "source_uuid": "ent-2", "target_uuid": "ent-1", "type": "CAPITAL_OF"}
                }
            }
        }
        
        response = client.post(f"/api/sessions/{thread_id}/save", json=save_data)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["message_count"] == 2
        assert data["entity_count"] == 2
        assert data["link_count"] == 1
        
        # Verify session was created
        get_response = client.get(f"/api/sessions/{thread_id}")
        session_data = get_response.json()
        assert len(session_data["messages"]) == 2
        assert len(session_data["ontology"]["entities"]) == 2

    def test_save_session_updates_title(self, client):
        """Test that auto-save extracts title from first user message."""
        thread_id = str(uuid4())
        
        save_data = {
            "messages": [
                {"role": "user", "content": "Tell me about the history of ancient Rome and its emperors"}
            ],
            "ontology": {"entities": {}, "links": {}}
        }
        
        client.post(f"/api/sessions/{thread_id}/save", json=save_data)
        
        # Verify title was extracted
        get_response = client.get(f"/api/sessions/{thread_id}")
        data = get_response.json()
        assert data["title"] == "Tell me about the history of ancient..."

    def test_save_session_update_existing(self, client):
        """Test that auto-save updates existing session."""
        # Create initial session
        create_response = client.post("/api/sessions", json={"title": "Initial"})
        thread_id = create_response.json()["thread_id"]
        
        # Auto-save with new data
        save_data = {
            "messages": [{"role": "user", "content": "Test message"}],
            "ontology": {"entities": {"e1": {"name": "Test"}}, "links": {}}
        }
        client.post(f"/api/sessions/{thread_id}/save", json=save_data)
        
        # Verify update
        get_response = client.get(f"/api/sessions/{thread_id}")
        data = get_response.json()
        assert len(data["messages"]) == 1
        assert len(data["ontology"]["entities"]) == 1

    def test_delete_session(self, client):
        """Test deleting a session."""
        # Create a session
        create_response = client.post("/api/sessions", json={"title": "To Delete"})
        thread_id = create_response.json()["thread_id"]
        
        # Delete it
        delete_response = client.delete(f"/api/sessions/{thread_id}")
        
        assert delete_response.status_code == 200
        assert delete_response.json()["deleted"] is True
        
        # Verify it's gone
        get_response = client.get(f"/api/sessions/{thread_id}")
        # Should return empty structure, not 404
        assert get_response.status_code == 200
        assert get_response.json()["messages"] == []

    def test_delete_session_not_found(self, client):
        """Test deleting non-existent session returns 404."""
        fake_id = str(uuid4())
        response = client.delete(f"/api/sessions/{fake_id}")
        
        assert response.status_code == 404

    def test_save_session_empty_messages(self, client):
        """Test auto-save with empty messages."""
        thread_id = str(uuid4())
        
        save_data = {
            "messages": [],
            "ontology": {"entities": {}, "links": {}}
        }
        
        response = client.post(f"/api/sessions/{thread_id}/save", json=save_data)
        
        assert response.status_code == 200

    def test_sessions_sorted_by_updated_at(self, client):
        """Test that sessions are sorted by updated_at (most recent first)."""
        # Create two sessions
        response1 = client.post("/api/sessions", json={"title": "First"})
        thread1 = response1.json()["thread_id"]
        
        asyncio.sleep(0.1)  # Small delay to ensure different timestamps
        
        client.post("/api/sessions", json={"title": "Second"})
        
        # Update first session to make it more recent
        client.post(f"/api/sessions/{thread1}/save", json={
            "messages": [{"role": "user", "content": "Update"}],
            "ontology": {"entities": {}, "links": {}}
        })
        
        # List sessions
        list_response = client.get("/api/sessions")
        sessions = list_response.json()
        
        # First session should be first (most recently updated)
        assert sessions[0]["thread_id"] == thread1
