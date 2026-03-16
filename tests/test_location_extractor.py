"""
Tests for the location extractor service.

Tests cover:
- NER-based location extraction (Hugging Face transformers)
- Multi-candidate geocoding (Nominatim)
- LLM-based location selection
- Full pipeline (NER → Geocode → LLM select)
- Caching behavior
"""
from unittest.mock import patch, MagicMock
from app.services.location_extractor import (
    extract_locations_with_ner,
    geocode_location,
    extract_and_geocode_locations,
    _geocode_cache
)


class TestExtractLocationsWithNER:
    """Tests for NER-based location extraction."""

    @patch('app.services.location_extractor.get_ner_pipeline')
    def test_extract_locations_gpe(self, mock_get_pipeline):
        """Test extraction of geopolitical entities (GPE)."""
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

    @patch('app.services.location_extractor.get_ner_pipeline')
    def test_extract_locations_loc(self, mock_get_pipeline):
        """Test extraction of locations (LOC)."""
        mock_pipeline = MagicMock()
        mock_pipeline.return_value = [
            {"entity_group": "LOC", "word": "Alps"},
        ]
        mock_get_pipeline.return_value = mock_pipeline

        result = extract_locations_with_ner("The Alps mountains")

        assert len(result) == 1
        assert result[0]["name"] == "Alps"
        assert result[0]["type"] == "landmark"

    @patch('app.services.location_extractor.get_ner_pipeline')
    def test_extract_locations_filters_non_locations(self, mock_get_pipeline):
        """Test that non-location entities are filtered out."""
        mock_pipeline = MagicMock()
        mock_pipeline.return_value = [
            {"entity_group": "PER", "word": "John Smith"},
            {"entity_group": "ORG", "word": "Google"},
            {"entity_group": "GPE", "word": "Paris"},
        ]
        mock_get_pipeline.return_value = mock_pipeline

        result = extract_locations_with_ner("John Smith from Google visited Paris")

        assert len(result) == 1
        assert result[0]["name"] == "Paris"


class TestGeocodeLocation:
    """Tests for multi-candidate geocoding."""

    def setup_method(self):
        """Clear cache before each test."""
        _geocode_cache.clear()

    @patch('app.services.location_extractor.Nominatim')
    def test_geocode_returns_multiple_candidates(self, mock_nominatim):
        """Test that geocoding returns all candidates, not just first."""
        mock_geolocator = MagicMock()
        
        # Mock multiple results
        result1 = MagicMock()
        result1.latitude = 48.8566
        result1.longitude = 2.3522
        result1.address = "Paris, France"
        result1.raw = {'address': {'city': 'Paris', 'country': 'France'}}
        
        result2 = MagicMock()
        result2.latitude = 33.8
        result2.longitude = -96.6
        result2.address = "Paris, Texas, USA"
        result2.raw = {'address': {'city': 'Paris', 'country': 'United States'}}
        
        mock_geolocator.geocode.return_value = [result1, result2]
        mock_nominatim.return_value = mock_geolocator

        result = geocode_location("Paris")

        assert len(result) == 2
        assert result[0]["name"] == "Paris"
        assert result[0]["country"] == "France"
        assert result[1]["country"] == "United States"

    @patch('app.services.location_extractor.Nominatim')
    def test_geocode_no_results(self, mock_nominatim):
        """Test when no geocoding results found."""
        mock_geolocator = MagicMock()
        mock_geolocator.geocode.return_value = []
        mock_nominatim.return_value = mock_geolocator

        result = geocode_location("NonExistentPlace12345")

        assert result == []

    @patch('app.services.location_extractor.Nominatim')
    def test_geocode_cache_hit(self, mock_nominatim):
        """Test that cached results are returned."""
        # Cache format: location_name -> list of candidates
        _geocode_cache["Cached City"] = [
            {
                "name": "Cached City",
                "lat": 1.0,
                "lon": 2.0,
                "type": "city",
                "country": "Test Country"
            }
        ]

        result = geocode_location("Cached City")

        assert len(result) == 1
        assert result[0]["lat"] == 1.0
        mock_nominatim.assert_not_called()


class TestExtractAndGeocodeLocations:
    """Tests for the full extraction and geocoding pipeline."""

    def setup_method(self):
        """Clear cache before each test."""
        _geocode_cache.clear()

    @patch('app.services.location_extractor.select_valid_locations')
    @patch('app.services.location_extractor.geocode_location')
    @patch('app.services.location_extractor.extract_locations_with_ner')
    def test_full_pipeline_success(self, mock_extract, mock_geocode, mock_select):
        """Test successful full pipeline."""
        mock_extract.return_value = [
            {"name": "Paris", "type": "country", "label": "GPE"},
            {"name": "London", "type": "country", "label": "GPE"},
        ]
        
        # Each location has multiple candidates
        mock_geocode.side_effect = [
            [
                {"name": "Paris", "lat": 48.8566, "lon": 2.3522, "country": "France", "type": "city"},
                {"name": "Paris", "lat": 33.8, "lon": -96.6, "country": "USA", "type": "city"}
            ],
            [
                {"name": "London", "lat": 51.5074, "lon": -0.1278, "country": "UK", "type": "city"}
            ]
        ]
        
        # LLM selects correct candidates
        mock_select.return_value = [
            {"name": "Paris", "lat": 48.8566, "lon": 2.3522, "country": "France"},
            {"name": "London", "lat": 51.5074, "lon": -0.1278, "country": "UK"}
        ]

        result = extract_and_geocode_locations(
            "Paris and London are capital cities",
            query="european capitals",
            response_text="Paris is capital of France"
        )

        assert len(result) == 2
        assert result[0]["name"] == "Paris"
        assert result[1]["name"] == "London"

    @patch('app.services.location_extractor.select_valid_locations')
    @patch('app.services.location_extractor.geocode_location')
    @patch('app.services.location_extractor.extract_locations_with_ner')
    def test_full_pipeline_llm_filters_wrong_matches(
        self, mock_extract, mock_geocode, mock_select
    ):
        """Test that LLM filters out wrong geocoding matches."""
        mock_extract.return_value = [
            {"name": "IRA", "type": "country", "label": "GPE"},
            {"name": "Tehran", "type": "city", "label": "GPE"},
        ]
        
        # IRA only has USA town matches (wrong)
        # Tehran has Iran match (correct)
        mock_geocode.side_effect = [
            [
                {"name": "IRA", "lat": 43.22, "lon": -76.56, "country": "USA", "type": "town"}
            ],
            [
                {"name": "Tehran", "lat": 35.69, "lon": 51.39, "country": "Iran", "type": "city"}
            ]
        ]
        
        # LLM filters out IRA, keeps Tehran
        mock_select.return_value = [
            {"name": "Tehran", "lat": 35.69, "lon": 51.39, "country": "Iran"}
        ]

        result = extract_and_geocode_locations(
            "IRA conflict",
            query="iran vs israel",
            response_text="Conflict between Iran and Israel"
        )

        # IRA should be filtered, only Tehran remains
        assert len(result) == 1
        assert result[0]["name"] == "Tehran"

    @patch('app.services.location_extractor.select_valid_locations')
    @patch('app.services.location_extractor.geocode_location')
    @patch('app.services.location_extractor.extract_locations_with_ner')
    def test_full_pipeline_no_locations(self, mock_extract, mock_geocode, mock_select):
        """Test pipeline when no locations are extracted."""
        mock_extract.return_value = []

        result = extract_and_geocode_locations("This text has no locations")

        assert result == []
        mock_geocode.assert_not_called()
        mock_select.assert_not_called()

    @patch('app.services.location_extractor.select_valid_locations')
    @patch('app.services.location_extractor.geocode_location')
    @patch('app.services.location_extractor.extract_locations_with_ner')
    def test_full_pipeline_rate_limiting(self, mock_extract, mock_geocode, mock_select):
        """Test that rate limiting delay is applied between geocoding calls."""
        mock_extract.return_value = [
            {"name": "Paris", "type": "country", "label": "GPE"},
            {"name": "London", "type": "country", "label": "GPE"},
            {"name": "Berlin", "type": "country", "label": "GPE"},
        ]
        mock_geocode.return_value = [{"name": "City", "lat": 0, "lon": 0, "country": "X"}]
        mock_select.return_value = []

        extract_and_geocode_locations("Paris, London, and Berlin")

        # Should sleep 0.1s before each geocoding call (3 calls)
        assert mock_geocode.call_count == 3


class TestSelectValidLocations:
    """Tests for LLM-based location selection."""

    @patch('app.services.llm.get_reviewer_llm')
    def test_llm_selects_correct_candidates(self, mock_get_llm):
        """Test that LLM selects correct candidates based on context."""
        from app.services.location_extractor import select_valid_locations
        
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(
            content='[{"location_index": 0, "candidate_index": 0, "reason": "Iran country matches"}]'
        )
        mock_get_llm.return_value = mock_llm

        location_candidates = [
            [
                {
                    "name": "Iran",
                    "lat": 32.65,
                    "lon": 54.56,
                    "country": "Iran",
                    "type": "country",
                    "display_name": "ایران (country)",
                    "state": "",
                    "city": ""
                },
                {
                    "name": "Iran",
                    "lat": 33.0,
                    "lon": -96.0,
                    "country": "USA",
                    "type": "town",
                    "display_name": "Iran, Texas, USA",
                    "state": "Texas",
                    "city": ""
                }
            ]
        ]

        result = select_valid_locations(
            location_candidates,
            query="iran vs israel",
            response_text="Conflict involving Iran"
        )

        assert len(result) == 1
        assert result[0]["country"] == "Iran"

    @patch('app.services.llm.get_reviewer_llm')
    def test_llm_handles_parse_error_gracefully(self, mock_get_llm):
        """Test graceful handling of LLM parse errors."""
        from app.services.location_extractor import select_valid_locations
        
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content='Invalid JSON response')
        mock_get_llm.return_value = mock_llm

        location_candidates = [
            [{
                "name": "Paris",
                "lat": 48.8,
                "lon": 2.3,
                "country": "France",
                "type": "city",
                "display_name": "Paris, France",
                "state": "",
                "city": "Paris"
            }]
        ]

        # Should fallback to first candidate
        result = select_valid_locations(
            location_candidates,
            query="test",
            response_text=""
        )

        assert len(result) == 1
        assert result[0]["name"] == "Paris"

    @patch('app.services.llm.get_reviewer_llm')
    def test_llm_empty_selection(self, mock_get_llm):
        """Test when LLM selects no locations."""
        from app.services.location_extractor import select_valid_locations
        
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content='[]')
        mock_get_llm.return_value = mock_llm

        location_candidates = [
            [{
                "name": "IRA",
                "lat": 43.2,
                "lon": -76.5,
                "country": "USA",
                "type": "town",
                "display_name": "Town of Ira, New York, USA",
                "state": "New York",
                "city": ""
            }]
        ]

        result = select_valid_locations(
            location_candidates,
            query="iran vs israel",
            response_text=""
        )

        assert result == []


class TestExtractLocationsWithNERIntegration:
    """Integration tests using the real NER model."""

    def test_extract_locations_real_model_simple(self):
        """Test NER extraction with real model on simple text."""
        result = extract_locations_with_ner("Paris is the capital of France")

        # Assert we get reasonable results
        assert len(result) >= 1
        names = [loc["name"] for loc in result]
        assert "France" in names or "Paris" in names

    def test_extract_locations_real_model_multiple_countries(self):
        """Test NER extraction with real model on multiple countries."""
        result = extract_locations_with_ner(
            "Germany and France are neighboring countries in Europe."
        )

        assert len(result) >= 2
        names = [loc["name"] for loc in result]
        assert "Germany" in names
        assert "France" in names

    def test_extract_locations_real_model_no_locations(self):
        """Test NER extraction with text containing no locations."""
        result = extract_locations_with_ner(
            "The quick brown fox jumps over the lazy dog."
        )

        # This sentence has no named entities
        assert result == []
