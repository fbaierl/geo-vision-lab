"""
Tests for Dependency Injection container.

Verifies that the DI container properly manages dependencies and supports overrides.
"""

from unittest.mock import MagicMock
from app.core.di import (
    container,
    get_mongo_client,
    get_embeddings,
    get_reasoning_llm,
    get_reviewer_llm,
    get_ner_pipeline,
    get_vector_store,
    get_location_extractor,
    get_location_prioritizer,
)


class TestDIContainer:
    """Test DI container functionality."""
    
    def test_container_override_and_reset(self):
        """Test that container can override and reset dependencies."""
        mock_service = MagicMock()
        
        # Override
        container.override(get_mongo_client, lambda: mock_service)
        
        # Verify override works
        assert get_mongo_client() is mock_service
        
        # Reset
        container.reset_overrides()
        
        # Verify reset (should not be the mock anymore)
        # Note: This might fail if get_mongo_client creates a real client,
        # so we just verify the override was removed
        assert get_mongo_client() is not mock_service
    
    def test_container_caches_instances(self):
        """Test that container caches instances (singleton behavior)."""
        # First call creates instance
        instance1 = get_reasoning_llm()
        
        # Second call returns same instance
        instance2 = get_reasoning_llm()
        
        assert instance1 is instance2
        
        # Reset for other tests
        container.reset_overrides()
    
    def test_override_affects_subsequent_calls(self):
        """Test that overrides affect all subsequent calls."""
        mock1 = MagicMock()
        mock2 = MagicMock()
        
        container.override(get_reasoning_llm, lambda: mock1)
        assert get_reasoning_llm() is mock1
        
        container.override(get_reasoning_llm, lambda: mock2)
        assert get_reasoning_llm() is mock2
        
        container.reset_overrides()


class TestVectorStoreService:
    """Test VectorStoreService with DI."""
    
    def test_get_vector_store_uses_di(self):
        """Test that get_vector_store uses DI container."""
        mock_client = MagicMock()
        mock_embeddings = MagicMock()
        mock_collection = MagicMock()
        
        # Override dependencies
        container.override(get_mongo_client, lambda: mock_client)
        container.override(get_embeddings, lambda: mock_embeddings)
        
        # Mock the collection retrieval
        mock_client.__getitem__.return_value = MagicMock()
        mock_client.__getitem__.return_value.__getitem__.return_value = mock_collection
        
        # Get service
        service = get_vector_store()
        
        # Verify service was created
        assert service is not None
        assert service.embeddings is mock_embeddings
        assert service.client is mock_client
        
        container.reset_overrides()


class TestLocationExtractorService:
    """Test LocationExtractorService with DI."""
    
    def test_get_location_extractor_uses_di(self):
        """Test that get_location_extractor uses DI container."""
        mock_ner = MagicMock()
        mock_llm = MagicMock()
        
        # Override dependencies
        container.override(get_ner_pipeline, lambda: mock_ner)
        container.override(get_reviewer_llm, lambda: mock_llm)
        
        # Get service
        service = get_location_extractor()
        
        # Verify service was created with correct dependencies
        assert service is not None
        assert service.ner_pipeline is mock_ner
        assert service.reviewer_llm is mock_llm
        
        container.reset_overrides()


class TestLocationPrioritizerService:
    """Test LocationPrioritizerService with DI."""
    
    def test_get_location_prioritizer_uses_di(self):
        """Test that get_location_prioritizer uses DI container."""
        mock_llm = MagicMock()
        
        # Override dependency
        container.override(get_reviewer_llm, lambda: mock_llm)
        
        # Get service
        service = get_location_prioritizer()
        
        # Verify service was created with correct dependency
        assert service is not None
        assert service.reviewer_llm is mock_llm
        
        container.reset_overrides()
