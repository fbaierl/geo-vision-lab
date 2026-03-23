"""
Tests for the LocationPrioritizerService.

Tests cover:
- JSON parsing from LLM responses
- Fallback behavior when LLM fails
- Relevance scoring
- Multi-candidate selection
- Edge cases (no locations, 1 location, many locations)
"""
from unittest.mock import MagicMock, patch
from langchain_core.messages import AIMessage
import pytest

from app.services.location_prioritizer import LocationPrioritizerService


class TestPrioritizeLocations:
    """Tests for LLM-based location prioritization."""

    @patch('app.services.location_prioritizer.LocationPrioritizerService._fallback_prioritize')
    def test_prioritize_with_valid_json_response(self, mock_fallback):
        """Test prioritization when LLM returns valid JSON."""
        mock_llm = MagicMock()
        
        # Mock LLM response with valid JSON array
        mock_response = AIMessage(content='''[
            {"location_index": 0, "candidate_index": 0, "relevance": 1.0, "reason": "Iran is the main subject"},
            {"location_index": 1, "candidate_index": 1, "relevance": 0.7, "reason": "Tehran is capital of Iran"}
        ]''')
        mock_llm.invoke.return_value = mock_response
        
        service = LocationPrioritizerService(llm=mock_llm)
        
        # Test data: multiple candidates for each location
        locations = [
            # Iran candidates (location_index 0)
            {"name": "Iran", "lat": 32.4279, "lon": 53.6880, "display_name": "Iran", "type": "country", "country": "Iran"},
            {"name": "Iran", "lat": 33.8, "lon": -96.6, "display_name": "Iran, Texas, USA", "type": "city", "country": "United States"},
            # Tehran candidates (location_index 1)
            {"name": "Tehran", "lat": 35.6892, "lon": 51.3890, "display_name": "Tehran, Iran", "type": "city", "country": "Iran"},
            {"name": "Tehran", "lat": 38.0, "lon": -122.0, "display_name": "Tehran, California, USA", "type": "city", "country": "United States"},
        ]
        
        result = service.prioritize_locations(
            query="What happened in Iran?",
            locations=locations,
            response_text="Iran experienced significant events in Tehran..."
        )
        
        # Should return 2 locations (Iran and Tehran)
        assert len(result) == 2
        assert result[0]["name"] == "Iran"
        assert result[0]["relevance"] == 1.0
        assert result[1]["name"] == "Tehran"
        assert result[1]["relevance"] == 0.7
        
        # Fallback should NOT be called
        mock_fallback.assert_not_called()

    @patch('app.services.location_prioritizer.LocationPrioritizerService._fallback_prioritize')
    def test_prioritize_with_invalid_json_response(self, mock_fallback):
        """Test that fallback is used when LLM returns invalid JSON."""
        mock_llm = MagicMock()
        
        # Mock LLM response with truncated/invalid JSON
        mock_response = AIMessage(content='[{"location_index": 0, "candidate_index": 0, "relevance": 1.0')
        mock_llm.invoke.return_value = mock_response
        
        # Mock fallback to return test data
        mock_fallback.return_value = [{"name": "Fallback Location", "relevance": 0.5}]
        
        service = LocationPrioritizerService(llm=mock_llm)
        
        locations = [
            {"name": "Test", "lat": 1.0, "lon": 2.0, "display_name": "Test Location", "type": "city", "country": "Test"},
        ]
        
        result = service.prioritize_locations(
            query="Test query",
            locations=locations,
            response_text="Test response"
        )
        
        # Should use fallback
        assert len(result) == 1
        assert result[0]["name"] == "Fallback Location"
        mock_fallback.assert_called_once()

    @patch('app.services.location_prioritizer.LocationPrioritizerService._fallback_prioritize')
    def test_prioritize_with_no_json_array(self, mock_fallback):
        """Test that fallback is used when no JSON array is found."""
        mock_llm = MagicMock()
        
        # Mock LLM response with no JSON array
        mock_response = AIMessage(content='I cannot help with that request.')
        mock_llm.invoke.return_value = mock_response
        
        mock_fallback.return_value = [{"name": "Fallback", "relevance": 0.5}]
        
        service = LocationPrioritizerService(llm=mock_llm)
        
        locations = [{"name": "Test", "lat": 1.0, "lon": 2.0, "display_name": "Test", "type": "city", "country": "Test"}]
        
        result = service.prioritize_locations("Query", locations, "Response")
        
        assert len(result) == 1
        mock_fallback.assert_called_once()

    @patch('app.services.location_prioritizer.LocationPrioritizerService._fallback_prioritize')
    def test_prioritize_with_llm_exception(self, mock_fallback):
        """Test that fallback is used when LLM invocation fails."""
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = Exception("LLM service unavailable")
        
        mock_fallback.return_value = [{"name": "Fallback", "relevance": 0.5}]
        
        service = LocationPrioritizerService(llm=mock_llm)
        
        locations = [{"name": "Test", "lat": 1.0, "lon": 2.0, "display_name": "Test", "type": "city", "country": "Test"}]
        
        result = service.prioritize_locations("Query", locations, "Response")
        
        assert len(result) == 1
        mock_fallback.assert_called_once()

    def test_prioritize_empty_locations(self):
        """Test that empty location list returns empty result."""
        mock_llm = MagicMock()
        service = LocationPrioritizerService(llm=mock_llm)
        
        result = service.prioritize_locations("Query", [], "Response")
        
        assert result == []

    def test_prioritize_filters_by_relevance_threshold(self):
        """Test that locations with low relevance are still included for debugging."""
        mock_llm = MagicMock()

        # LLM returns a location with low relevance
        mock_response = AIMessage(content='''[
            {"location_index": 0, "candidate_index": 0, "relevance": 0.3, "reason": "Not very relevant"}
        ]''')
        mock_llm.invoke.return_value = mock_response

        service = LocationPrioritizerService(llm=mock_llm)

        locations = [{"name": "Test", "lat": 1.0, "lon": 2.0, "display_name": "Test", "type": "city", "country": "Test"}]

        result = service.prioritize_locations("Query", locations, "Response")

        # Now we keep ALL locations for debugging (even with low relevance)
        # But locations with relevance <= 0 are marked as excluded
        assert len(result) == 1
        assert result[0]['relevance'] == 0.3
        assert result[0]['selection_reason'] == "Not very relevant"

    def test_prioritize_limits_to_5_locations(self):
        """Test that result is limited to 5 locations max."""
        mock_llm = MagicMock()
        
        # LLM returns 10 locations
        json_content = '[\n'
        for i in range(10):
            json_content += f'  {{"location_index": {i}, "candidate_index": 0, "relevance": {1.0 - i * 0.1}, "reason": "Reason {i}"}}'
            if i < 9:
                json_content += ','
            json_content += '\n'
        json_content += ']'
        
        mock_response = AIMessage(content=json_content)
        mock_llm.invoke.return_value = mock_response
        
        service = LocationPrioritizerService(llm=mock_llm)
        
        # Create 10 locations
        locations = [
            {"name": f"Loc{i}", "lat": float(i), "lon": float(i), "display_name": f"Location {i}", "type": "city", "country": "Test"}
            for i in range(10)
        ]
        
        result = service.prioritize_locations("Query", locations, "Response")
        
        # Should limit to 5
        assert len(result) == 5

    def test_prioritize_sorts_by_relevance(self):
        """Test that results are sorted by relevance (descending)."""
        mock_llm = MagicMock()
        
        # LLM returns locations in random order
        mock_response = AIMessage(content='''[
            {"location_index": 0, "candidate_index": 0, "relevance": 0.4, "reason": "Low relevance"},
            {"location_index": 1, "candidate_index": 0, "relevance": 1.0, "reason": "High relevance"},
            {"location_index": 2, "candidate_index": 0, "relevance": 0.7, "reason": "Medium relevance"}
        ]''')
        mock_llm.invoke.return_value = mock_response
        
        service = LocationPrioritizerService(llm=mock_llm)
        
        locations = [
            {"name": "Low", "lat": 1.0, "lon": 1.0, "display_name": "Low", "type": "city", "country": "Test"},
            {"name": "High", "lat": 2.0, "lon": 2.0, "display_name": "High", "type": "city", "country": "Test"},
            {"name": "Medium", "lat": 3.0, "lon": 3.0, "display_name": "Medium", "type": "city", "country": "Test"},
        ]
        
        result = service.prioritize_locations("Query", locations, "Response")
        
        # Should be sorted by relevance descending
        assert len(result) == 3
        assert result[0]["relevance"] == 1.0
        assert result[1]["relevance"] == 0.7
        assert result[2]["relevance"] == 0.4


class TestFallbackPrioritize:
    """Tests for fallback prioritization when LLM fails."""

    def test_fallback_selects_best_candidate_per_location(self):
        """Test that fallback selects highest-specificity candidate for each location."""
        mock_llm = MagicMock()
        service = LocationPrioritizerService(llm=mock_llm)
        
        # Multiple candidates for same location name
        locations = [
            {"name": "Paris", "lat": 48.8566, "lon": 2.3522, "display_name": "Paris, France", "type": "city", "country": "France"},
            {"name": "Paris", "lat": 33.8, "lon": -96.6, "display_name": "Paris, Texas", "type": "city", "country": "USA"},
        ]
        
        # Group by name (as the main function does)
        candidates_by_name = {"paris": locations}
        
        result = service._fallback_prioritize(candidates_by_name)
        
        # Should select one candidate for Paris
        assert len(result) == 1
        assert result[0]["name"] == "Paris"

    def test_fallback_prioritizes_by_type(self):
        """Test that fallback prioritizes countries over regions over cities."""
        mock_llm = MagicMock()
        service = LocationPrioritizerService(llm=mock_llm)
        
        candidates_by_name = {
            "paris": [{"name": "Paris", "type": "city", "lat": 1.0, "lon": 1.0, "display_name": "Paris", "country": "France"}],
            "france": [{"name": "France", "type": "country", "lat": 2.0, "lon": 2.0, "display_name": "France", "country": "France"}],
            "ile_de_france": [{"name": "Ile-de-France", "type": "region", "lat": 3.0, "lon": 3.0, "display_name": "Ile-de-France", "country": "France"}],
        }
        
        result = service._fallback_prioritize(candidates_by_name)
        
        # Should sort by type: country first, then region, then city
        assert len(result) == 3
        assert result[0]["type"] == "country"
        assert result[1]["type"] == "region"
        assert result[2]["type"] == "city"

    def test_fallback_limits_to_5_locations(self):
        """Test that fallback limits results to 5 locations."""
        mock_llm = MagicMock()
        service = LocationPrioritizerService(llm=mock_llm)
        
        # Create 10 locations
        candidates_by_name = {
            f"loc{i}": [{"name": f"Loc{i}", "type": "city", "lat": float(i), "lon": float(i), "display_name": f"Loc{i}", "country": "Test"}]
            for i in range(10)
        }
        
        result = service._fallback_prioritize(candidates_by_name)
        
        assert len(result) == 5

    def test_fallback_assigns_relevance_scores(self):
        """Test that fallback assigns relevance scores based on position."""
        mock_llm = MagicMock()
        service = LocationPrioritizerService(llm=mock_llm)
        
        candidates_by_name = {
            "loc1": [{"name": "Loc1", "type": "country", "lat": 1.0, "lon": 1.0, "display_name": "Loc1", "country": "Test"}],
            "loc2": [{"name": "Loc2", "type": "country", "lat": 2.0, "lon": 2.0, "display_name": "Loc2", "country": "Test"}],
            "loc3": [{"name": "Loc3", "type": "country", "lat": 3.0, "lon": 3.0, "display_name": "Loc3", "country": "Test"}],
            "loc4": [{"name": "Loc4", "type": "country", "lat": 4.0, "lon": 4.0, "display_name": "Loc4", "country": "Test"}],
        }
        
        result = service._fallback_prioritize(candidates_by_name)
        
        # First location gets 1.0, next two get 0.7, rest get 0.4
        assert result[0]["relevance"] == 1.0
        assert result[1]["relevance"] == 0.7
        assert result[2]["relevance"] == 0.7
        assert result[3]["relevance"] == 0.4


class TestSelectBestCandidate:
    """Tests for the candidate selection heuristic."""

    def test_select_country_over_city(self):
        """Test that country is selected over city."""
        mock_llm = MagicMock()
        service = LocationPrioritizerService(llm=mock_llm)
        
        candidates = [
            {"name": "Iran", "type": "city", "lat": 33.8, "lon": -96.6, "display_name": "Iran, Texas", "country": "USA"},
            {"name": "Iran", "type": "country", "lat": 32.4, "lon": 53.7, "display_name": "Iran", "country": "Iran"},
        ]
        
        result = service._select_best_candidate(candidates)
        
        assert result["type"] == "country"

    def test_select_city_over_landmark(self):
        """Test that city is selected over landmark."""
        mock_llm = MagicMock()
        service = LocationPrioritizerService(llm=mock_llm)
        
        candidates = [
            {"name": "Paris", "type": "landmark", "lat": 1.0, "lon": 1.0, "display_name": "Paris Monument", "country": "France"},
            {"name": "Paris", "type": "city", "lat": 48.8, "lon": 2.3, "display_name": "Paris, France", "country": "France"},
        ]
        
        result = service._select_best_candidate(candidates)
        
        assert result["type"] == "city"

    def test_select_first_when_same_type(self):
        """Test that first candidate is selected when all have same type."""
        mock_llm = MagicMock()
        service = LocationPrioritizerService(llm=mock_llm)

        candidates = [
            {"name": "Paris", "type": "city", "lat": 48.8, "lon": 2.3, "display_name": "Paris, France", "country": "France"},
            {"name": "Paris", "type": "city", "lat": 33.8, "lon": -96.6, "display_name": "Paris, Texas", "country": "USA"},
        ]

        result = service._select_best_candidate(candidates)

        # Should select first one (France)
        assert result["display_name"] == "Paris, France"


class TestExcludedLocations:
    """Tests for the exclusion feature (candidate_index: -1)."""

    def test_excluded_location_with_candidate_index_minus_one(self):
        """Test that locations with candidate_index: -1 are marked as excluded."""
        mock_llm = MagicMock()

        # LLM returns a mix of included and excluded locations
        mock_response = AIMessage(content='''[
            {"location_index": 0, "candidate_index": 0, "relevance": 1.0, "reason": "Iran is main subject"},
            {"location_index": 1, "candidate_index": -1, "relevance": 0.0, "reason": "Wrong country (USA, not Iran)"},
            {"location_index": 2, "candidate_index": 0, "relevance": 0.7, "reason": "Tehran is capital"}
        ]''')
        mock_llm.invoke.return_value = mock_response

        service = LocationPrioritizerService(llm=mock_llm)

        locations = [
            {"name": "iran", "type": "country", "lat": 32.4, "lon": 53.7, "display_name": "Iran", "country": "Iran"},
            {"name": "ira", "type": "village", "lat": 43.2, "lon": -76.5, "display_name": "Ira, New York", "country": "USA"},
            {"name": "tehran", "type": "city", "lat": 35.7, "lon": 51.4, "display_name": "Tehran, Iran", "country": "Iran"},
        ]

        result = service.prioritize_locations("Tell me about Iran war", locations, "Response")

        # Should have 3 locations (including the excluded one), sorted by relevance
        assert len(result) == 3

        # First location (Iran) should be included with highest relevance
        assert result[0]['name'] == 'iran'
        assert result[0]['relevance'] == 1.0
        assert result[0].get('excluded') is None or result[0].get('excluded') is False

        # Second location (Tehran) should be included with medium relevance
        assert result[1]['name'] == 'tehran'
        assert result[1]['relevance'] == 0.7

        # Third location (Ira) should be excluded (sorted to end due to 0.0 relevance)
        assert result[2]['name'] == 'ira'
        assert result[2]['relevance'] == 0.0
        assert result[2]['excluded'] is True
        assert result[2]['selection_reason'] == "Wrong country (USA, not Iran)"

    def test_all_excluded_locations_sorted_by_relevance(self):
        """Test that excluded locations (relevance 0.0) are sorted to the end."""
        mock_llm = MagicMock()

        mock_response = AIMessage(content='''[
            {"location_index": 0, "candidate_index": -1, "relevance": 0.0, "reason": "Not relevant"},
            {"location_index": 1, "candidate_index": 0, "relevance": 1.0, "reason": "Main subject"},
            {"location_index": 2, "candidate_index": -1, "relevance": 0.0, "reason": "Wrong location"}
        ]''')
        mock_llm.invoke.return_value = mock_response

        service = LocationPrioritizerService(llm=mock_llm)

        locations = [
            {"name": "loc1", "type": "city", "lat": 1.0, "lon": 1.0, "display_name": "Location 1", "country": "Test"},
            {"name": "loc2", "type": "country", "lat": 2.0, "lon": 2.0, "display_name": "Location 2", "country": "Test"},
            {"name": "loc3", "type": "city", "lat": 3.0, "lon": 3.0, "display_name": "Location 3", "country": "Test"},
        ]

        result = service.prioritize_locations("Query", locations, "Response")

        # Should be sorted by relevance (descending)
        assert result[0]['relevance'] == 1.0  # loc2
        assert result[1]['relevance'] == 0.0  # loc1
        assert result[2]['relevance'] == 0.0  # loc3
