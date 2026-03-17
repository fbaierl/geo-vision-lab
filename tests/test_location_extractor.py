"""
Tests for the LocationExtractorService.

Tests cover:
- NER-based location extraction (Hugging Face transformers)
- Multi-candidate geocoding (Nominatim)
- LLM-based location selection
- Full pipeline (NER → Geocode → LLM select)
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
            reviewer_llm=MagicMock(),
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
            reviewer_llm=MagicMock(),
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
            reviewer_llm=MagicMock(),
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
            reviewer_llm=MagicMock(),
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
            reviewer_llm=MagicMock(),
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
            reviewer_llm=MagicMock(),
            geocode_cache=cache
        )

        result = service.geocode_location("Cached City")

        assert len(result) == 1
        assert result[0]["lat"] == 1.0


class TestExtractAndGeocodeLocations:
    """Tests for the full extraction and geocoding pipeline."""

    @patch('app.services.location_extractor.LocationExtractorService.select_valid_locations')
    @patch('app.services.location_extractor.LocationExtractorService.geocode_location')
    @patch('app.services.location_extractor.LocationExtractorService.extract_locations_with_ner')
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
        
        service = LocationExtractorService(
            ner_pipeline=MagicMock(),
            reviewer_llm=MagicMock(),
            geocode_cache={}
        )

        result = service.extract_and_geocode_locations(
            "Paris and London are capital cities",
            query="european capitals",
            response_text="Paris is capital of France"
        )

        assert len(result) == 2
        assert result[0]["name"] == "Paris"
        assert result[1]["name"] == "London"

    @patch('app.services.location_extractor.LocationExtractorService.select_valid_locations')
    @patch('app.services.location_extractor.LocationExtractorService.geocode_location')
    @patch('app.services.location_extractor.LocationExtractorService.extract_locations_with_ner')
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
        
        service = LocationExtractorService(
            ner_pipeline=MagicMock(),
            reviewer_llm=MagicMock(),
            geocode_cache={}
        )

        result = service.extract_and_geocode_locations(
            "IRA conflict",
            query="iran vs israel",
            response_text="Conflict between Iran and Israel"
        )

        # IRA should be filtered, only Tehran remains
        assert len(result) == 1
        assert result[0]["name"] == "Tehran"

    @patch('app.services.location_extractor.LocationExtractorService.select_valid_locations')
    @patch('app.services.location_extractor.LocationExtractorService.geocode_location')
    @patch('app.services.location_extractor.LocationExtractorService.extract_locations_with_ner')
    def test_full_pipeline_no_locations(self, mock_extract, mock_geocode, mock_select):
        """Test pipeline when no locations are extracted."""
        mock_extract.return_value = []
        
        service = LocationExtractorService(
            ner_pipeline=MagicMock(),
            reviewer_llm=MagicMock(),
            geocode_cache={}
        )

        result = service.extract_and_geocode_locations("This text has no locations")

        assert result == []
        mock_geocode.assert_not_called()
        mock_select.assert_not_called()


class TestSelectValidLocations:
    """Tests for LLM-based location selection."""

    @patch('app.core.di.get_reviewer_llm')
    def test_llm_selects_correct_candidates(self, mock_get_llm):
        """Test that LLM selects correct candidates based on context."""
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(
            content='[{"location_index": 0, "candidate_index": 0, "reason": "Iran country matches"}]'
        )
        mock_get_llm.return_value = mock_llm
        
        service = LocationExtractorService(
            ner_pipeline=MagicMock(),
            reviewer_llm=mock_llm,
            geocode_cache={}
        )

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

        result = service.select_valid_locations(
            location_candidates,
            query="iran vs israel",
            response_text="Conflict involving Iran"
        )

        assert len(result) == 1
        assert result[0]["country"] == "Iran"

    @patch('app.core.di.get_reviewer_llm')
    def test_llm_handles_parse_error_gracefully(self, mock_get_llm):
        """Test graceful handling of LLM parse errors."""
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content='Invalid JSON response')
        mock_get_llm.return_value = mock_llm
        
        service = LocationExtractorService(
            ner_pipeline=MagicMock(),
            reviewer_llm=mock_llm,
            geocode_cache={}
        )

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
        result = service.select_valid_locations(
            location_candidates,
            query="test",
            response_text=""
        )

        assert len(result) == 1
        assert result[0]["name"] == "Paris"

    @patch('app.core.di.get_reviewer_llm')
    def test_llm_empty_selection(self, mock_get_llm):
        """Test when LLM selects no locations."""
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content='[]')
        mock_get_llm.return_value = mock_llm
        
        service = LocationExtractorService(
            ner_pipeline=MagicMock(),
            reviewer_llm=mock_llm,
            geocode_cache={}
        )

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

        result = service.select_valid_locations(
            location_candidates,
            query="iran vs israel",
            response_text=""
        )

        assert result == []
