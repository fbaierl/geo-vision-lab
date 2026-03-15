"""
Tests for Geospatial API Endpoints

Tests for the /geo/* API routes.
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


class TestGeoHeatmapEndpoint:
    """Tests for GET /geo/heatmap endpoint."""

    def test_heatmap_endpoint_exists(self):
        """Test that the heatmap endpoint is accessible."""
        response = client.get("/geo/heatmap")
        # Should return 200 even with empty data
        assert response.status_code == 200

    def test_heatmap_endpoint_returns_list(self):
        """Test that heatmap returns a list structure."""
        response = client.get("/geo/heatmap")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_heatmap_min_intensity_filter(self):
        """Test heatmap with min_intensity parameter."""
        response = client.get("/geo/heatmap?min_intensity=0.5")
        assert response.status_code == 200
        data = response.json()
        
        # All returned points should have intensity >= 0.5
        for point in data:
            assert point["intensity"] >= 0.5

    def test_heatmap_invalid_intensity(self):
        """Test heatmap with invalid intensity value."""
        response = client.get("/geo/heatmap?min_intensity=1.5")
        # Should return 422 for validation error
        assert response.status_code == 422

    def test_heatmap_date_filtering(self):
        """Test heatmap with date filtering parameters."""
        response = client.get("/geo/heatmap?date_from=2024-01-01&date_to=2024-12-31")
        assert response.status_code == 200


class TestGeoClustersEndpoint:
    """Tests for GET /geo/clusters endpoint."""

    def test_clusters_endpoint_exists(self):
        """Test that the clusters endpoint is accessible."""
        response = client.get("/geo/clusters")
        assert response.status_code == 200

    def test_clusters_endpoint_returns_list(self):
        """Test that clusters returns a list structure."""
        response = client.get("/geo/clusters")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_clusters_with_query(self):
        """Test clusters with query parameter."""
        response = client.get("/geo/clusters?query=test")
        assert response.status_code == 200


class TestGeoTerritoryEndpoint:
    """Tests for GET /geo/territory/{location_name} endpoint."""

    @pytest.mark.skip(reason="Requires external geocoding API")
    def test_territory_valid_location(self):
        """Test territory lookup for a valid location."""
        response = client.get("/geo/territory/France")
        assert response.status_code == 200
        data = response.json()
        
        assert data["type"] == "Feature"
        assert "properties" in data
        assert "geometry" in data

    def test_territory_not_found(self):
        """Test territory lookup for non-existent location."""
        response = client.get("/geo/territory/NotARealCountry12345")
        # Should return 404 for not found
        assert response.status_code == 404

    @pytest.mark.skip(reason="Requires external geocoding API")
    def test_territory_country(self):
        """Test territory lookup for a country."""
        response = client.get("/geo/territory/Germany")
        assert response.status_code == 200
        data = response.json()
        
        assert data["properties"]["name"] == "Germany"


class TestGeoLocationEndpoint:
    """Tests for GET /geo/location/{location_name} endpoint."""

    @pytest.mark.skip(reason="Requires external geocoding API")
    def test_location_valid(self):
        """Test location lookup for a valid location."""
        response = client.get("/geo/location/Paris")
        assert response.status_code == 200
        data = response.json()
        
        assert "name" in data
        assert "coordinates" in data
        assert len(data["coordinates"]) == 2

    def test_location_not_found(self):
        """Test location lookup for non-existent location."""
        response = client.get("/geo/location/NotARealPlace12345")
        # May return 404 or empty data
        assert response.status_code in [200, 404]


class TestGeoAPIValidation:
    """Tests for API input validation."""

    def test_heatmap_negative_intensity(self):
        """Test heatmap with negative intensity."""
        response = client.get("/geo/heatmap?min_intensity=-0.5")
        # Should return 422 for validation error
        assert response.status_code == 422

    def test_geo_api_tags(self):
        """Test that geo endpoints have proper tags."""
        openapi = app.openapi()
        geo_paths = [path for path in openapi["paths"] if "/geo/" in path]
        
        assert len(geo_paths) >= 3  # heatmap, clusters, territory


class TestGeoAPIResponses:
    """Tests for API response structure."""

    def test_heatmap_point_structure(self):
        """Test heatmap point has required fields."""
        response = client.get("/geo/heatmap")
        data = response.json()
        
        if data:  # If there's data
            point = data[0]
            required_fields = ["lat", "lng", "intensity", "name"]
            for field in required_fields:
                assert field in point

    def test_cluster_structure(self):
        """Test cluster has required fields."""
        response = client.get("/geo/clusters")
        data = response.json()
        
        if data:  # If there's data
            cluster = data[0]
            required_fields = ["center", "related_locations", "connections"]
            for field in required_fields:
                assert field in cluster
