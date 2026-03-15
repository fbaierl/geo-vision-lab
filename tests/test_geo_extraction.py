"""
Tests for Geospatial Extraction Service

Tests for location extraction (GLiNER NER), geocoding, and heat map data generation.
"""

import pytest
from unittest.mock import patch, MagicMock

from app.services.geo_extractor import (
    extract_locations_from_text,
    geocode_location,
    extract_dates_from_text,
    analyze_sentiment,
    get_heatmap_data,
    get_location_clusters,
    extract_locations_with_gliner,
    extract_locations_with_llm
)


class TestLocationExtraction:
    """Tests for GLiNER-based location extraction."""

    def test_extract_gpe_location(self):
        """Test extraction of geo-political entities."""
        text = "The conflict in Ukraine has escalated."
        locations = extract_locations_from_text(text)

        assert len(locations) >= 1
        assert any("Ukraine" in loc["name"] for loc in locations)

    def test_extract_city_location(self):
        """Test extraction of city locations."""
        text = "Forces advanced toward Kyiv and Kharkiv."
        locations = extract_locations_from_text(text)

        # Should find at least one city
        assert len(locations) >= 1
        names = [loc["name"] for loc in locations]
        assert any(name in names for name in ["Kyiv", "Kharkiv"])

    def test_extract_multiple_locations(self):
        """Test extraction of multiple locations from text."""
        text = "Tensions rise in the South China Sea near Taiwan and the Philippines."
        locations = extract_locations_from_text(text)

        assert len(locations) >= 1

    def test_empty_text(self):
        """Test extraction from empty text."""
        locations = extract_locations_from_text("")
        assert locations == []

    def test_no_locations(self):
        """Test text without geographic entities."""
        text = "The economic policy was announced yesterday."
        locations = extract_locations_from_text(text)
        # Should return empty or minimal results
        assert len(locations) == 0


class TestGLiNERExtraction:
    """Tests specific to GLiNER NER model."""

    def test_gliner_extract_countries(self):
        """Test GLiNER extracts country names."""
        text = "France and Germany signed the agreement."
        locations = extract_locations_with_gliner(text)
        
        # GLiNER should find at least one country
        assert len(locations) >= 1
        names = [loc["name"] for loc in locations]
        assert any(name in names for name in ["France", "Germany"])

    def test_gliner_extract_cities(self):
        """Test GLiNER extracts city names."""
        text = "The summit was held in Paris and Berlin."
        locations = extract_locations_with_gliner(text)
        
        assert len(locations) >= 1
        names = [loc["name"] for loc in locations]
        assert any(name in names for name in ["Paris", "Berlin"])

    def test_gliner_fallback_to_llm(self):
        """Test that GLiNER falls back to LLM if model unavailable."""
        # This tests the fallback mechanism
        text = "The conference in Tokyo was attended by leaders."
        locations = extract_locations_with_gliner(text)
        
        # Should return locations (either from GLiNER or LLM fallback)
        assert isinstance(locations, list)


class TestGeocoding:
    """Tests for location geocoding."""

    @pytest.mark.skip(reason="Requires external API")
    def test_geocode_real_city(self):
        """Test geocoding a real city (requires network)."""
        coords = geocode_location("Paris, France")
        assert coords is not None
        assert isinstance(coords, tuple)
        assert len(coords) == 2

    @pytest.mark.skip(reason="Requires external API")
    def test_geocode_country(self):
        """Test geocoding a country (requires network)."""
        coords = geocode_location("Germany")
        assert coords is not None
        # Germany is roughly at 51.1657° N, 10.4515° E
        assert 47 < coords[0] < 55  # Latitude
        assert 5 < coords[1] < 16   # Longitude

    def test_geocode_invalid_location(self):
        """Test geocoding an invalid location."""
        # This should return None for non-existent places
        coords = geocode_location("NotARealPlace12345")
        # May return None or coordinates if Nominatim finds something similar
        # Just ensure it doesn't crash
        assert coords is None or isinstance(coords, tuple)


class TestDateExtraction:
    """Tests for date extraction from text."""

    def test_extract_named_dates(self):
        """Test extraction of named date entities."""
        text = "The agreement was signed last week."
        dates = extract_dates_from_text(text)
        
        assert len(dates) >= 1
        assert "last week" in dates

    def test_extract_numeric_dates(self):
        """Test extraction of numeric date patterns."""
        text = "The event occurred on 2024-03-15 and again on 01/15/2024."
        dates = extract_dates_from_text(text)
        
        assert len(dates) >= 1
        assert any("2024" in str(d) for d in dates)

    def test_extract_month_format_dates(self):
        """Test extraction of month-day-year format."""
        text = "On March 15, 2024 the treaty was ratified."
        dates = extract_dates_from_text(text)
        
        assert len(dates) >= 1

    def test_empty_text_dates(self):
        """Test date extraction from empty text."""
        dates = extract_dates_from_text("")
        assert dates == []


class TestSentimentAnalysis:
    """Tests for conflict sentiment analysis."""

    def test_conflict_sentiment_negative(self):
        """Test negative sentiment for conflict-related text."""
        text = "The bombing attack caused casualties and destruction."
        sentiment = analyze_sentiment(text)
        
        assert sentiment < 0  # Negative = conflict

    def test_peaceful_sentiment_positive(self):
        """Test positive sentiment for peaceful text."""
        text = "The peace treaty brought cooperation and development."
        sentiment = analyze_sentiment(text)
        
        assert sentiment > 0  # Positive = peaceful

    def test_neutral_sentiment(self):
        """Test neutral sentiment for mixed text."""
        text = "The situation remains stable with no changes."
        sentiment = analyze_sentiment(text)
        
        assert -0.2 <= sentiment <= 0.2  # Near neutral

    def test_empty_text_sentiment(self):
        """Test sentiment of empty text."""
        sentiment = analyze_sentiment("")
        assert sentiment == 0.0


class TestHeatmapData:
    """Tests for heat map data generation."""

    @pytest.mark.skip(reason="Requires database and external API")
    def test_get_heatmap_data_structure(self):
        """Test heat map data structure (requires DB)."""
        data = get_heatmap_data(min_intensity=0.0)
        
        assert isinstance(data, list)
        if data:
            point = data[0]
            assert "lat" in point
            assert "lng" in point
            assert "intensity" in point
            assert "name" in point

    @pytest.mark.skip(reason="Requires database and external API")
    def test_get_heatmap_data_filtering(self):
        """Test heat map data filtering (requires DB)."""
        # Test with high intensity threshold
        data_high = get_heatmap_data(min_intensity=0.8)
        data_low = get_heatmap_data(min_intensity=0.1)
        
        assert len(data_high) <= len(data_low)


class TestLocationClusters:
    """Tests for location cluster analysis."""

    @pytest.mark.skip(reason="Requires database and external API")
    def test_get_clusters_structure(self):
        """Test cluster data structure (requires DB)."""
        clusters = get_location_clusters()
        
        assert isinstance(clusters, list)
        if clusters:
            cluster = clusters[0]
            assert "center" in cluster
            assert "related_locations" in cluster
            assert "connections" in cluster

    @pytest.mark.skip(reason="Requires database and external API")
    def test_get_clusters_with_query(self):
        """Test cluster filtering by query (requires DB)."""
        clusters = get_location_clusters(query="conflict")
        assert isinstance(clusters, list)


class TestIntegration:
    """Integration tests for the geo extraction pipeline."""

    @pytest.mark.skip(reason="Requires database and external API")
    def test_full_pipeline(self):
        """Test full extraction pipeline (requires DB)."""
        # This would test the complete flow from document to heat map
        # Requires actual documents in the database
        data = get_heatmap_data(min_intensity=0.0)
        
        # Verify data can be used for visualization
        for point in data:
            assert -90 <= point["lat"] <= 90
            assert -180 <= point["lng"] <= 180
            assert 0 <= point["intensity"] <= 1
