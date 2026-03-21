"""
Tests for the LocationExtractorService.

Tests cover:
- NER-based location extraction (Hugging Face transformers)
- Multi-candidate geocoding (Nominatim)
- Full pipeline (NER → Geocode) - returns ALL candidates without filtering
- Caching behavior
"""
from unittest.mock import patch, MagicMock
from app.services.location_extractor import LocationExtractorService


class TestExtractLocationsWithNER:
    """Tests for NER-based location extraction."""

    def test_extract_locations_gpe(self):
        """Test extraction of geopolitical entities (GPE)."""
        mock_pipeline = MagicMock()
        mock_pipeline.return_value = [
            {"entity_group": "GPE", "word": "France"},
            {"entity_group": "GPE", "word": "Germany"},
        ]

        service = LocationExtractorService(
            ner_pipeline=mock_pipeline,
            geocode_cache={}
        )

        result = service.extract_locations_with_ner("France and Germany are in Europe")

        assert len(result) == 2
        assert result[0]["name"] == "France"
        assert result[0]["type"] == "country"
        assert result[0]["label"] == "GPE"

    def test_extract_locations_loc(self):
        """Test extraction of locations (LOC)."""
        mock_pipeline = MagicMock()
        mock_pipeline.return_value = [
            {"entity_group": "LOC", "word": "Alps"},
        ]

        service = LocationExtractorService(
            ner_pipeline=mock_pipeline,
            geocode_cache={}
        )

        result = service.extract_locations_with_ner("The Alps mountains")

        assert len(result) == 1
        assert result[0]["name"] == "Alps"
        assert result[0]["type"] == "landmark"

    def test_extract_locations_filters_non_locations(self):
        """Test that non-location entities are filtered out."""
        mock_pipeline = MagicMock()
        mock_pipeline.return_value = [
            {"entity_group": "PER", "word": "John Smith"},
            {"entity_group": "ORG", "word": "Google"},
            {"entity_group": "GPE", "word": "Paris"},
        ]

        service = LocationExtractorService(
            ner_pipeline=mock_pipeline,
            geocode_cache={}
        )

        result = service.extract_locations_with_ner("John Smith from Google visited Paris")

        assert len(result) == 1
        assert result[0]["name"] == "Paris"


class TestGeocodeLocation:
    """Tests for multi-candidate geocoding."""

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

        service = LocationExtractorService(
            ner_pipeline=MagicMock(),
            geocode_cache={}
        )

        result = service.geocode_location("Paris")

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

        service = LocationExtractorService(
            ner_pipeline=MagicMock(),
            geocode_cache={}
        )

        result = service.geocode_location("NonExistentPlace12345")

        assert result == []

    def test_geocode_cache_hit(self):
        """Test that cached results are returned."""
        # Cache format: location_name -> list of candidates
        cache = {
            "Cached City": [
                {
                    "name": "Cached City",
                    "lat": 1.0,
                    "lon": 2.0,
                    "type": "city",
                    "country": "Test Country"
                }
            ]
        }

        service = LocationExtractorService(
            ner_pipeline=MagicMock(),
            geocode_cache=cache
        )

        result = service.geocode_location("Cached City")

        assert len(result) == 1
        assert result[0]["lat"] == 1.0


class TestExtractAndGeocodeLocations:
    """Tests for the full extraction and geocoding pipeline."""

    @patch('app.services.location_extractor.LocationExtractorService.geocode_location')
    @patch('app.services.location_extractor.LocationExtractorService.extract_locations_with_ner')
    def test_full_pipeline_returns_all_candidates(self, mock_extract, mock_geocode):
        """Test that full pipeline returns ALL candidates (no filtering)."""
        mock_extract.return_value = [
            {"name": "Paris", "type": "country", "label": "GPE"},
            {"name": "London", "type": "country", "label": "GPE"},
        ]

        # Each location has multiple candidates
        mock_geocode.side_effect = [
            [
                {"name": "Paris", "lat": 48.8566, "lon": 2.3522, "country": "France", "type": "city", "display_name": "Paris, France"},
                {"name": "Paris", "lat": 33.8, "lon": -96.6, "country": "USA", "type": "city", "display_name": "Paris, Texas"}
            ],
            [
                {"name": "London", "lat": 51.5074, "lon": -0.1278, "country": "UK", "type": "city", "display_name": "London, UK"},
                {"name": "London", "lat": 42.0, "lon": -81.0, "country": "Canada", "type": "city", "display_name": "London, Ontario"}
            ]
        ]

        service = LocationExtractorService(
            ner_pipeline=MagicMock(),
            geocode_cache={}
        )

        result = service.extract_and_geocode_locations(
            "Paris and London are capital cities",
            query="european capitals",
            response_text="Paris is capital of France"
        )

        # Should return ALL 4 candidates (no filtering)
        assert len(result) == 4
        assert result[0]["name"] == "Paris"
        assert result[1]["name"] == "Paris"
        assert result[2]["name"] == "London"
        assert result[3]["name"] == "London"

    @patch('app.services.location_extractor.LocationExtractorService.geocode_location')
    @patch('app.services.location_extractor.LocationExtractorService.extract_locations_with_ner')
    def test_full_pipeline_no_locations(self, mock_extract, mock_geocode):
        """Test pipeline when no locations are extracted."""
        mock_extract.return_value = []

        service = LocationExtractorService(
            ner_pipeline=MagicMock(),
            geocode_cache={}
        )

        result = service.extract_and_geocode_locations("This text has no locations")

        assert result == []
        mock_geocode.assert_not_called()

    @patch('app.services.location_extractor.LocationExtractorService.geocode_location')
    @patch('app.services.location_extractor.LocationExtractorService.extract_locations_with_ner')
    def test_full_pipeline_skips_failed_geocoding(self, mock_extract, mock_geocode):
        """Test that locations with no geocoding results are skipped."""
        mock_extract.return_value = [
            {"name": "Paris", "type": "country", "label": "GPE"},
            {"name": "FakePlace", "type": "city", "label": "GPE"},
        ]

        # Paris has results, FakePlace has none
        mock_geocode.side_effect = [
            [
                {"name": "Paris", "lat": 48.8566, "lon": 2.3522, "country": "France", "type": "city", "display_name": "Paris, France"}
            ],
            []  # FakePlace has no results
        ]

        service = LocationExtractorService(
            ner_pipeline=MagicMock(),
            geocode_cache={}
        )

        result = service.extract_and_geocode_locations("Paris and FakePlace")

        # Only Paris candidates should be returned
        assert len(result) == 1
        assert result[0]["name"] == "Paris"
