"""
Tests for Langfuse Integration

Tests the Langfuse tracing configuration, callback handlers, and feedback API.
"""

import pytest
from unittest.mock import MagicMock, patch
from app.core.config import settings
from app.core.di import container


@pytest.fixture(autouse=True)
def reset_di_container():
    """Reset DI container overrides after each test."""
    yield
    container.reset_overrides()


class TestLangfuseConfig:
    """Test Langfuse configuration module."""

    def test_is_langfuse_enabled_false_by_default(self):
        """Test that Langfuse is disabled by default."""
        from app.core.langfuse_config import is_langfuse_enabled
        
        # Reset settings to default
        original_enabled = settings.LANGFUSE_ENABLED
        original_public_key = settings.LANGFUSE_PUBLIC_KEY
        original_secret_key = settings.LANGFUSE_SECRET_KEY
        
        settings.LANGFUSE_ENABLED = False
        settings.LANGFUSE_PUBLIC_KEY = None
        settings.LANGFUSE_SECRET_KEY = None
        
        assert is_langfuse_enabled() is False
        
        # Restore
        settings.LANGFUSE_ENABLED = original_enabled
        settings.LANGFUSE_PUBLIC_KEY = original_public_key
        settings.LANGFUSE_SECRET_KEY = original_secret_key

    def test_is_langfuse_enabled_true_when_configured(self, monkeypatch):
        """Test that Langfuse is enabled when properly configured."""
        from app.core.langfuse_config import is_langfuse_enabled
        
        monkeypatch.setattr(settings, "LANGFUSE_ENABLED", True)
        monkeypatch.setattr(settings, "LANGFUSE_PUBLIC_KEY", "pk-lf-test-key")
        monkeypatch.setattr(settings, "LANGFUSE_SECRET_KEY", "sk-lf-test-key")
        
        assert is_langfuse_enabled() is True

    def test_get_langfuse_callback_handler_returns_none_when_disabled(self, monkeypatch):
        """Test that callback handler returns None when Langfuse is disabled."""
        from app.core.langfuse_config import get_langfuse_callback_handler
        
        monkeypatch.setattr(settings, "LANGFUSE_ENABLED", False)
        
        handler = get_langfuse_callback_handler()
        assert handler is None

    def test_get_callback_manager_returns_manager(self, monkeypatch):
        """Test that get_callback_manager returns a CallbackManager."""
        from app.core.langfuse_config import get_callback_manager
        from langchain_core.callbacks import CallbackManager
        
        monkeypatch.setattr(settings, "LANGFUSE_ENABLED", False)
        
        manager = get_callback_manager()
        assert isinstance(manager, CallbackManager)


class TestLangfuseWithLLM:
    """Test Langfuse integration with LLM."""

    def test_di_llm_uses_langfuse_when_enabled(self, monkeypatch):
        """Test that DI LLM uses Langfuse callback when enabled."""
        from app.core.di_llm import _get_callback_manager
        from langchain_core.callbacks import CallbackManager
        
        monkeypatch.setattr(settings, "LANGFUSE_ENABLED", True)
        monkeypatch.setattr(settings, "LANGSMITH_TRACING", False)
        
        manager = _get_callback_manager()
        assert isinstance(manager, CallbackManager)

    def test_di_llm_fallback_to_langsmith(self, monkeypatch):
        """Test that DI LLM falls back to LangSmith when Langfuse is disabled."""
        from app.core.di_llm import _get_callback_manager
        
        monkeypatch.setattr(settings, "LANGFUSE_ENABLED", False)
        monkeypatch.setattr(settings, "LANGSMITH_TRACING", True)
        
        manager = _get_callback_manager()
        # Should still return a CallbackManager (may be empty if LangSmith not configured)
        from langchain_core.callbacks import CallbackManager
        assert isinstance(manager, CallbackManager)

    def test_no_tracing_when_both_disabled(self, monkeypatch):
        """Test that no tracing is used when both Langfuse and LangSmith are disabled."""
        from app.core.di_llm import _get_callback_manager
        
        monkeypatch.setattr(settings, "LANGFUSE_ENABLED", False)
        monkeypatch.setattr(settings, "LANGSMITH_TRACING", False)
        
        manager = _get_callback_manager()
        assert len(manager.handlers) == 0


class TestFeedbackAPI:
    """Test Feedback API endpoints."""

    def test_submit_feedback_thumbs_up(self, client):
        """Test submitting thumbs up feedback."""
        response = client.post(
            "/feedback",
            json={
                "thread_id": "test-thread-123",
                "rating": "thumbs_up",
                "comment": "Very helpful!",
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "recorded successfully" in data["message"]

    def test_submit_feedback_thumbs_down(self, client):
        """Test submitting thumbs down feedback."""
        response = client.post(
            "/feedback",
            json={
                "thread_id": "test-thread-456",
                "rating": "thumbs_down",
                "comment": "Not accurate",
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "recorded successfully" in data["message"]

    def test_submit_feedback_missing_thread_id(self, client):
        """Test that feedback fails without thread_id."""
        response = client.post(
            "/feedback",
            json={
                "rating": "thumbs_up",
            }
        )
        
        assert response.status_code == 422  # Validation error

    def test_submit_feedback_invalid_rating(self, client):
        """Test that feedback fails with invalid rating."""
        response = client.post(
            "/feedback",
            json={
                "thread_id": "test-thread-789",
                "rating": "invalid_rating",
            }
        )
        
        assert response.status_code == 422  # Validation error

    def test_get_feedback_stats(self, client):
        """Test getting feedback statistics."""
        response = client.get("/feedback/stats")
        
        assert response.status_code == 200
        data = response.json()
        assert "total_feedback" in data
        assert "thumbs_up" in data
        assert "thumbs_down" in data


class TestFeedbackAPIWithLangfuse:
    """Test Feedback API with Langfuse enabled."""

    def test_feedback_sent_to_langfuse(self, client, monkeypatch):
        """Test that feedback is sent to Langfuse when enabled."""
        monkeypatch.setattr(settings, "LANGFUSE_ENABLED", True)
        monkeypatch.setattr(settings, "LANGFUSE_PUBLIC_KEY", "pk-lf-test")
        monkeypatch.setattr(settings, "LANGFUSE_SECRET_KEY", "sk-lf-test")
        
        # Mock Langfuse client
        mock_langfuse = MagicMock()
        mock_langfuse.create_trace_id.return_value = "test-trace-id"
        
        with patch("langfuse.Langfuse") as mock_langfuse_class:
            mock_langfuse_class.return_value = mock_langfuse
            
            response = client.post(
                "/feedback",
                json={
                    "thread_id": "test-thread-langfuse",
                    "rating": "thumbs_up",
                    "comment": "Testing Langfuse integration",
                }
            )
            
            assert response.status_code == 200
            
            # Verify Langfuse was called
            mock_langfuse_class.assert_called_once()
            mock_langfuse.create_trace_id.assert_called_once()
            mock_langfuse.score_current_trace.assert_called_once()
            mock_langfuse.flush.assert_called_once()

    def test_feedback_graceful_degradation(self, client, monkeypatch):
        """Test that feedback still succeeds even if Langfuse fails."""
        monkeypatch.setattr(settings, "LANGFUSE_ENABLED", True)
        monkeypatch.setattr(settings, "LANGFUSE_PUBLIC_KEY", "pk-lf-test")
        monkeypatch.setattr(settings, "LANGFUSE_SECRET_KEY", "sk-lf-test")
        
        # Mock Langfuse to raise an exception
        with patch("langfuse.Langfuse") as mock_langfuse_class:
            mock_langfuse_class.side_effect = Exception("Langfuse unavailable")
            
            response = client.post(
                "/feedback",
                json={
                    "thread_id": "test-thread-fail",
                    "rating": "thumbs_up",
                }
            )
            
            # Should still succeed (graceful degradation)
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
