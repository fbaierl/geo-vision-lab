"""
Tests for the location extractor service.

Tests cover:
- NER-based location extraction
- Geocoding functionality
- Boundary fetching
- Full pipeline (extract + geocode)
- Caching behavior
"""
import pytest
from unittest.mock import patch, MagicMock, call
from app.services.location_extractor import (
    extract_locations_with_ner,
    geocode_location,
    extract_and_geocode_locations,
    get_ner_pipeline,
    _geocode_cache
)


class TestExtractLocationsWithNER:
    """Tests for NER-based location extraction."""

    @patch('app.services.location_extractor.get_ner_pipeline')
    def test_extract_locations_gpe(self, mock_get_pipeline):
        """Test extraction of geopolitical entities (GPE)."""
        # Mock NER pipeline output
        mock_pipeline = MagicMock()
        mock_pipeline.return_value = [
            {"entity_group": "GPE", "word": "France"},
            {"entity_group": "GPE", "word": "Germany"},
        ]
        mock_get_pipeline.return_value = mock_pipeline

        result = extract_locations_with_ner("France and Germany are in Europe")

        assert len(result) == 2
        assert result[0]["name"] == "France"
        assert result[0]["type"] == "country"
        assert result[0]["label"] == "GPE"
        assert result[1]["name"] == "Germany"
        assert result[1]["type"] == "country"
        assert result[1]["label"] == "GPE"

    @patch('app.services.location_extractor.get_ner_pipeline')
    def test_extract_locations_loc(self, mock_get_pipeline):
        """Test extraction of locations (LOC)."""
        mock_pipeline = MagicMock()
        mock_pipeline.return_value = [
            {"entity_group": "LOC", "word": "Alps"},
            {"entity_group": "LOC", "word": "Mediterranean Sea"},
        ]
        mock_get_pipeline.return_value = mock_pipeline

        result = extract_locations_with_ner("The Alps near the Mediterranean Sea")

        assert len(result) == 2
        assert result[0]["name"] == "Alps"
        assert result[0]["type"] == "landmark"
        assert result[0]["label"] == "LOC"

    @patch('app.services.location_extractor.get_ner_pipeline')
    def test_extract_locations_fac(self, mock_get_pipeline):
        """Test extraction of facilities (FAC)."""
        mock_pipeline = MagicMock()
        mock_pipeline.return_value = [
            {"entity_group": "FAC", "word": "Eiffel Tower"},
        ]
        mock_get_pipeline.return_value = mock_pipeline

        result = extract_locations_with_ner("Visit the Eiffel Tower")

        assert len(result) == 1
        assert result[0]["name"] == "Eiffel Tower"
        assert result[0]["type"] == "landmark"
        assert result[0]["label"] == "FAC"

    @patch('app.services.location_extractor.get_ner_pipeline')
    def test_extract_locations_duplicates(self, mock_get_pipeline):
        """Test that duplicate locations are removed."""
        mock_pipeline = MagicMock()
        mock_pipeline.return_value = [
            {"entity_group": "GPE", "word": "Paris"},
            {"entity_group": "GPE", "word": "Paris"},
            {"entity_group": "GPE", "word": "Paris"},
        ]
        mock_get_pipeline.return_value = mock_pipeline

        result = extract_locations_with_ner("Paris Paris Paris")

        assert len(result) == 1
        assert result[0]["name"] == "Paris"

    @patch('app.services.location_extractor.get_ner_pipeline')
    def test_extract_locations_mixed_types(self, mock_get_pipeline):
        """Test extraction with mixed entity types."""
        mock_pipeline = MagicMock()
        mock_pipeline.return_value = [
            {"entity_group": "GPE", "word": "London"},
            {"entity_group": "LOC", "word": "Thames"},
            {"entity_group": "FAC", "word": "Big Ben"},
            {"entity_group": "PER", "word": "John Smith"},  # Should be filtered out
            {"entity_group": "ORG", "word": "BBC"},  # Should be filtered out
        ]
        mock_get_pipeline.return_value = mock_pipeline

        result = extract_locations_with_ner("John Smith from BBC visited Big Ben in London near the Thames")

        assert len(result) == 3
        names = [loc["name"] for loc in result]
        assert "London" in names
        assert "Thames" in names
        assert "Big Ben" in names
        assert "John Smith" not in names
        assert "BBC" not in names

    @patch('app.services.location_extractor.get_ner_pipeline')
    def test_extract_locations_no_results(self, mock_get_pipeline):
        """Test when no locations are found."""
        mock_pipeline = MagicMock()
        mock_pipeline.return_value = []
        mock_get_pipeline.return_value = mock_pipeline

        result = extract_locations_with_ner("This text has no locations")

        assert result == []

    @patch('app.services.location_extractor.get_ner_pipeline')
    def test_extract_locations_only_non_location_entities(self, mock_get_pipeline):
        """Test when only non-location entities are found."""
        mock_pipeline = MagicMock()
        mock_pipeline.return_value = [
            {"entity_group": "PER", "word": "Alice"},
            {"entity_group": "ORG", "word": "Google"},
        ]
        mock_get_pipeline.return_value = mock_pipeline

        result = extract_locations_with_ner("Alice works at Google")

        assert result == []


class TestGeocodeLocation:
    """Tests for geocoding functionality."""

    def setup_method(self):
        """Clear cache before each test."""
        _geocode_cache.clear()

    @patch('app.services.location_extractor.Nominatim')
    def test_geocode_city(self, mock_nominatim):
        """Test geocoding a city."""
        mock_geolocator = MagicMock()
        mock_location = MagicMock()
        mock_location.latitude = 48.8566
        mock_location.longitude = 2.3522
        mock_location.address = "Paris, France"
        mock_location.raw = {'address': {'city': 'Paris', 'country': 'France'}}
        mock_geolocator.geocode.return_value = mock_location
        mock_nominatim.return_value = mock_geolocator

        result = geocode_location("Paris")

        assert result is not None
        assert result["lat"] == 48.8566
        assert result["lon"] == 2.3522
        assert result["type"] == "city"
        assert result["found"] is True
        assert result["display_name"] == "Paris, France"

    @patch('app.services.location_extractor.Nominatim')
    def test_geocode_country(self, mock_nominatim):
        """Test geocoding a country."""
        mock_geolocator = MagicMock()
        mock_location = MagicMock()
        mock_location.latitude = 46.603354
        mock_location.longitude = 1.8883335
        mock_location.address = "France"
        mock_location.raw = {'address': {'country': 'France'}}
        mock_geolocator.geocode.return_value = mock_location
        mock_nominatim.return_value = mock_geolocator

        result = geocode_location("France")

        assert result is not None
        assert result["type"] == "country"

    @patch('app.services.location_extractor.Nominatim')
    def test_geocode_region(self, mock_nominatim):
        """Test geocoding a region/state."""
        mock_geolocator = MagicMock()
        mock_location = MagicMock()
        mock_location.latitude = 36.7783
        mock_location.longitude = -119.4179
        mock_location.address = "California, USA"
        mock_location.raw = {'address': {'state': 'California', 'country': 'United States'}}
        mock_geolocator.geocode.return_value = mock_location
        mock_nominatim.return_value = mock_geolocator

        result = geocode_location("California")

        assert result is not None
        assert result["type"] == "region"

    @patch('app.services.location_extractor.Nominatim')
    def test_geocode_not_found(self, mock_nominatim):
        """Test when location is not found."""
        mock_geolocator = MagicMock()
        mock_geolocator.geocode.return_value = None
        mock_nominatim.return_value = mock_geolocator

        result = geocode_location("NonExistentPlace12345")

        assert result is None

    @patch('app.services.location_extractor.Nominatim')
    def test_geocode_timeout(self, mock_nominatim):
        """Test geocoding timeout handling."""
        from geopy.exc import GeocoderTimedOut
        mock_geolocator = MagicMock()
        mock_geolocator.geocode.side_effect = GeocoderTimedOut("Timeout")
        mock_nominatim.return_value = mock_geolocator

        result = geocode_location("SlowPlace")

        assert result is None

    @patch('app.services.location_extractor.Nominatim')
    def test_geocode_service_error(self, mock_nominatim):
        """Test geocoding service error handling."""
        from geopy.exc import GeocoderServiceError
        mock_geolocator = MagicMock()
        mock_geolocator.geocode.side_effect = GeocoderServiceError("Error")
        mock_nominatim.return_value = mock_geolocator

        result = geocode_location("ErrorPlace")

        assert result is None

    @patch('app.services.location_extractor.Nominatim')
    def test_geocode_cache_hit(self, mock_nominatim):
        """Test that cached results are returned."""
        _geocode_cache["Cached City"] = {
            "lat": 1.0,
            "lon": 2.0,
            "type": "city",
            "found": True
        }

        result = geocode_location("Cached City")

        assert result is not None
        assert result["lat"] == 1.0
        assert result["lon"] == 2.0
        mock_nominatim.assert_not_called()


class TestExtractAndGeocodeLocations:
    """Tests for the full extraction and geocoding pipeline."""

    def setup_method(self):
        """Clear cache before each test."""
        _geocode_cache.clear()

    @patch('app.services.location_extractor.geocode_location')
    @patch('app.services.location_extractor.extract_locations_with_ner')
    def test_full_pipeline_success(self, mock_extract, mock_geocode):
        """Test successful full pipeline."""
        mock_extract.return_value = [
            {"name": "Paris", "type": "country", "label": "GPE"},
            {"name": "London", "type": "country", "label": "GPE"},
        ]
        mock_geocode.side_effect = [
            {"lat": 48.8566, "lon": 2.3522, "type": "city", "found": True, "display_name": "Paris, France"},
            {"lat": 51.5074, "lon": -0.1278, "type": "city", "found": True, "display_name": "London, UK"},
        ]

        result = extract_and_geocode_locations("Paris and London are capital cities")

        assert len(result) == 2
        assert result[0]["name"] == "Paris"
        assert result[0]["lat"] == 48.8566
        assert result[1]["name"] == "London"
        assert result[1]["lat"] == 51.5074

    @patch('app.services.location_extractor.geocode_location')
    @patch('app.services.location_extractor.extract_locations_with_ner')
    def test_full_pipeline_partial_success(self, mock_extract, mock_geocode):
        """Test pipeline when some locations fail to geocode."""
        mock_extract.return_value = [
            {"name": "Paris", "type": "country", "label": "GPE"},
            {"name": "FakePlace", "type": "landmark", "label": "LOC"},
        ]
        mock_geocode.side_effect = [
            {"lat": 48.8566, "lon": 2.3522, "type": "city", "found": True, "display_name": "Paris, France"},
            None,  # FakePlace not found
        ]

        result = extract_and_geocode_locations("Paris and FakePlace")

        assert len(result) == 1
        assert result[0]["name"] == "Paris"

    @patch('app.services.location_extractor.geocode_location')
    @patch('app.services.location_extractor.extract_locations_with_ner')
    def test_full_pipeline_no_locations(self, mock_extract, mock_geocode):
        """Test pipeline when no locations are extracted."""
        mock_extract.return_value = []

        result = extract_and_geocode_locations("This text has no locations")

        assert result == []
        mock_geocode.assert_not_called()

    @patch('app.services.location_extractor.geocode_location')
    @patch('app.services.location_extractor.extract_locations_with_ner')
    def test_full_pipeline_all_fail(self, mock_extract, mock_geocode):
        """Test pipeline when all geocoding fails."""
        mock_extract.return_value = [
            {"name": "FakePlace1", "type": "landmark", "label": "LOC"},
            {"name": "FakePlace2", "type": "landmark", "label": "LOC"},
        ]
        mock_geocode.return_value = None

        result = extract_and_geocode_locations("FakePlace1 and FakePlace2")

        assert result == []

    @patch('app.services.location_extractor.geocode_location')
    @patch('app.services.location_extractor.extract_locations_with_ner')
    @patch('time.sleep')
    def test_full_pipeline_rate_limiting(self, mock_sleep, mock_extract, mock_geocode):
        """Test that rate limiting delay is applied between geocoding calls."""
        mock_extract.return_value = [
            {"name": "Paris", "type": "country", "label": "GPE"},
            {"name": "London", "type": "country", "label": "GPE"},
            {"name": "Berlin", "type": "country", "label": "GPE"},
        ]
        mock_geocode.return_value = {"lat": 0, "lon": 0, "type": "city", "found": True, "display_name": "City"}

        extract_and_geocode_locations("Paris, London, and Berlin")

        # Should sleep before each geocoding call (3 sleeps for 3 locations)
        assert mock_sleep.call_count == 3
        mock_sleep.assert_called_with(0.1)


class TestExtractLocationsWithNERIntegration:
    """Integration tests using the real NER model."""

    def test_extract_locations_real_model_simple(self):
        """Test NER extraction with real model on simple text."""
        # This will download/load the real model on first run
        result = extract_locations_with_ner("Paris is the capital of France")

        # Assert we get reasonable results (may vary by model)
        assert len(result) >= 1
        names = [loc["name"] for loc in result]
        # At least one of these should be detected
        assert "France" in names or "Paris" in names
        
        # Note: extract_locations_with_ner() returns preliminary types based on NER labels only
        # For accurate types (country vs city), use extract_and_geocode_locations() which geocodes via Nominatim
        # LOC entities are labeled as "landmark" as a fallback, even for countries

    def test_extract_locations_real_model_multiple_countries(self):
        """Test NER extraction with real model on multiple countries."""
        result = extract_locations_with_ner(
            "Germany and France are neighboring countries in Europe. "
            "Berlin is the capital of Germany."
        )

        assert len(result) >= 2
        names = [loc["name"] for loc in result]
        # Should detect at least Germany and France
        assert "Germany" in names
        assert "France" in names

    def test_extract_locations_real_model_mixed_types(self):
        """Test NER extraction with real model on mixed entity types."""
        result = extract_locations_with_ner(
            "The Eiffel Tower is located in Paris, France."
        )

        # Should detect at least Paris and/or France
        names = [loc["name"] for loc in result]
        assert len(result) >= 1
        assert "Paris" in names or "France" in names or "Eiffel Tower" in names

    def test_extract_locations_real_model_no_locations(self):
        """Test NER extraction with text containing no locations."""
        result = extract_locations_with_ner(
            "The quick brown fox jumps over the lazy dog."
        )

        # This sentence has no named entities
        assert result == []
