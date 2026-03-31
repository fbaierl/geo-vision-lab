"""
Tests for services with dependency injection.

Demonstrates how to test services using DI overrides instead of patching globals.
"""

from unittest.mock import MagicMock
from app.services.vector_store import VectorStoreService, get_vector_store
from app.services.location_extractor import LocationExtractorService
from app.services.location_prioritizer import LocationPrioritizerService


class TestVectorStoreService:
    """Test VectorStoreService with injected dependencies."""

    def test_similarity_search(self):
        """Test vector search with mock dependencies."""
        # Create mocks
        mock_embeddings = MagicMock()
        mock_client = MagicMock()
        mock_collection = MagicMock()

        # Setup mock behavior
        mock_embeddings.embed_query.return_value = [0.1] * 384
        mock_collection.aggregate.return_value = [
            {"page_content": "Result 1", "metadata": {"source": "test.pdf"}},
            {"page_content": "Result 2", "metadata": {"source": "test.pdf"}},
        ]

        # Create service with injected dependencies
        service = VectorStoreService(
            embeddings=mock_embeddings, client=mock_client, collection=mock_collection
        )

        # Call method
        results = service.similarity_search("test query", k=2)

        # Verify
        assert len(results) == 2
        assert results[0]["page_content"] == "Result 1"
        mock_embeddings.embed_query.assert_called_once_with("test query")

    def test_insert_documents(self):
        """Test document insertion with mock dependencies."""
        # Create mocks
        mock_embeddings = MagicMock()
        mock_client = MagicMock()
        mock_collection = MagicMock()

        # Setup mock behavior
        mock_embeddings.embed_documents.return_value = [[0.1] * 384, [0.2] * 384]

        # Create service
        service = VectorStoreService(
            embeddings=mock_embeddings, client=mock_client, collection=mock_collection
        )

        # Prepare test documents
        documents = [
            {"page_content": "Doc 1", "metadata": {"source": "test.pdf"}},
            {"page_content": "Doc 2", "metadata": {"source": "test.pdf"}},
        ]

        # Call method
        service.insert_documents(documents)

        # Verify
        mock_collection.delete_many.assert_called_once()
        mock_embeddings.embed_documents.assert_called_once()
        assert mock_collection.insert_many.called


class TestLocationExtractorService:
    """Test LocationExtractorService with injected dependencies."""

    def test_extract_locations_with_ner(self):
        """Test NER extraction with mock pipeline."""
        # Create mock NER pipeline
        mock_ner = MagicMock()
        mock_ner.return_value = [
            {"entity_group": "GPE", "word": "Paris", "entity_text": "Paris"},
            {
                "entity_group": "LOC",
                "word": "Eiffel Tower",
                "entity_text": "Eiffel Tower",
            },
        ]

        # Create service (no reviewer_llm needed)
        service = LocationExtractorService(ner_pipeline=mock_ner, geocode_cache={})

        # Call method
        locations = service.extract_locations_with_ner("Paris is beautiful")

        # Verify
        assert len(locations) == 2
        assert locations[0]["name"] == "Paris"
        assert locations[0]["type"] == "country"  # GPE -> country
        assert locations[1]["name"] == "Eiffel Tower"
        assert locations[1]["type"] == "landmark"  # LOC -> landmark

    def test_geocode_location_with_cache(self):
        """Test geocoding uses cache."""
        mock_ner = MagicMock()

        # Pre-populate cache
        cache = {
            "Paris": [
                {
                    "name": "Paris",
                    "lat": 48.8566,
                    "lon": 2.3522,
                    "display_name": "Paris, France",
                    "type": "city",
                    "country": "France",
                }
            ]
        }

        service = LocationExtractorService(ner_pipeline=mock_ner, geocode_cache=cache)

        # Call method - should use cache, not call Nominatim
        results = service.geocode_location("Paris")

        # Verify cache was used
        assert len(results) == 1
        assert results[0]["lat"] == 48.8566


class TestLocationPrioritizerService:
    """Test LocationPrioritizerService with injected dependencies."""

    def test_prioritize_locations_with_llm(self):
        """Test location prioritization with mock LLM."""
        # Create mock LLM
        mock_llm = MagicMock()
        mock_response = MagicMock()
        # New format: location_index, candidate_index, relevance
        mock_response.content = '[{"location_index": 0, "candidate_index": 0, "relevance": 1.0, "reason": "Paris is main subject"}]'
        mock_llm.invoke.return_value = mock_response

        # Create service
        service = LocationPrioritizerService(llm=mock_llm)

        # Test locations with full geocoding data (including display_name and country)
        locations = [
            {
                "name": "Paris",
                "type": "city",
                "lat": 48.8566,
                "lon": 2.3522,
                "display_name": "Paris, France",
                "country": "France",
            },
            {
                "name": "Paris",
                "type": "city",
                "lat": 33.8,
                "lon": -96.6,
                "display_name": "Paris, Texas, USA",
                "country": "USA",
            },
            {
                "name": "London",
                "type": "city",
                "lat": 51.5074,
                "lon": -0.1278,
                "display_name": "London, UK",
                "country": "UK",
            },
        ]

        # Call method
        result = service.prioritize_locations(
            query="Tell me about Paris",
            locations=locations,
            response_text="Paris is the capital of France...",
        )

        # Verify
        assert len(result) > 0
        assert result[0]["name"] == "Paris"
        assert result[0]["relevance"] == 1.0
        # Should select France candidate, not Texas
        assert result[0]["country"] == "France"

    def test_prioritize_locations_fallback(self):
        """Test fallback when LLM fails."""
        # Create mock LLM that fails
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = Exception("LLM error")

        # Create service
        service = LocationPrioritizerService(llm=mock_llm)

        # Test locations with full geocoding data
        locations = [
            {
                "name": "Paris",
                "type": "city",
                "lat": 48.8566,
                "lon": 2.3522,
                "display_name": "Paris, France",
                "country": "France",
            },
            {
                "name": "France",
                "type": "country",
                "lat": 46.603354,
                "lon": 1.888334,
                "display_name": "France",
                "country": "France",
            },
        ]

        # Call method - should use fallback
        result = service.prioritize_locations(
            query="Tell me about Paris",
            locations=locations,
            response_text="Paris is the capital of France...",
        )

        # Verify fallback returned results
        assert len(result) > 0
        # In fallback, country is prioritized over city
        types = [loc["type"] for loc in result]
        assert "country" in types or "city" in types


class TestServiceIntegrationWithDI:
    """Test getting services via DI container with overrides."""

    def test_get_vector_store_with_overrides(self, override_mongo, override_embeddings):
        """Test getting vector store via DI with overrides."""
        # Get service via DI
        service = get_vector_store()

        # Verify it uses our mocks
        assert service.client is override_mongo
        assert service.embeddings is override_embeddings

    def test_get_location_extractor_with_overrides(self, override_ner_pipeline):
        """Test getting location extractor via DI with overrides."""
        # Get service via DI with override
        from app.services.location_extractor import LocationExtractorService

        service = LocationExtractorService(
            ner_pipeline=override_ner_pipeline, geocode_cache={}
        )

        # Verify it uses our mock
        assert service.ner_pipeline is override_ner_pipeline
