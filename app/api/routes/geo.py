"""
Geospatial API Routes

Endpoints for heat map data, location clusters, and territory boundaries.
"""

import logging
from typing import Optional, List
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel

from app.services.geo_extractor import (
    get_heatmap_data,
    get_location_clusters,
    get_territory_boundary
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/geo", tags=["geospatial"])


class HeatPoint(BaseModel):
    """Heat map point data."""
    lat: float
    lng: float
    intensity: float
    name: str
    mention_count: int
    sentiment: float


class ClusterLocation(BaseModel):
    """Location within a cluster."""
    name: str
    lat: float
    lng: float
    strength: int


class ClusterConnection(BaseModel):
    """Connection between locations in a cluster."""
    from_: List[float]
    to: List[float]
    strength: int


class Cluster(BaseModel):
    """Location cluster data."""
    center: ClusterLocation
    related_locations: List[ClusterLocation]
    connections: List[ClusterConnection]


class TerritoryFeature(BaseModel):
    """GeoJSON territory feature."""
    type: str
    properties: dict
    geometry: dict


@router.get("/heatmap", response_model=List[HeatPoint])
async def get_heatmap(
    date_from: Optional[str] = Query(None, description="Filter locations after this date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="Filter locations before this date (YYYY-MM-DD)"),
    min_intensity: float = Query(0.1, ge=0.0, le=1.0, description="Minimum intensity threshold")
):
    """
    Get heat map data for geographic visualization.
    
    Returns location data with intensity scores based on:
    - Mention frequency in documents
    - Sentiment analysis (conflict detection)
    - Temporal relevance
    
    **Example:**
    ```
    GET /geo/heatmap?min_intensity=0.3&date_from=2024-01-01
    ```
    """
    try:
        data = get_heatmap_data(
            date_from=date_from,
            date_to=date_to,
            min_intensity=min_intensity
        )
        return data
    except Exception as e:
        logger.error(f"[GEO API] Heatmap generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate heat map data: {str(e)}")


@router.get("/clusters", response_model=List[Cluster])
async def get_clusters(
    query: Optional[str] = Query(None, description="Optional query to filter clusters by topic")
):
    """
    Get location clusters showing co-occurring geographic entities.
    
    Clusters are formed by analyzing which locations are mentioned
    together in the same document contexts.
    
    **Example:**
    ```
    GET /geo/clusters?query=conflict
    ```
    """
    try:
        clusters = get_location_clusters(query=query)
        return clusters
    except Exception as e:
        logger.error(f"[GEO API] Cluster analysis failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to analyze clusters: {str(e)}")


@router.get("/territory/{location_name}", response_model=TerritoryFeature)
async def get_territory(location_name: str):
    """
    Get GeoJSON boundary for a country or region.
    
    Returns territory boundaries with faction control information.
    
    **Example:**
    ```
    GET /geo/territory/Ukraine
    ```
    """
    try:
        boundary = get_territory_boundary(location_name)
        
        if boundary is None:
            raise HTTPException(
                status_code=404,
                detail=f"Territory boundary not found for '{location_name}'"
            )
        
        return boundary
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[GEO API] Territory lookup failed for '{location_name}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch territory: {str(e)}")


@router.get("/location/{location_name}")
async def get_location_info(location_name: str):
    """
    Get detailed information about a specific location.
    
    Returns coordinates, mention statistics, and context excerpts.
    
    **Example:**
    ```
    GET /geo/location/Kyiv
    ```
    """
    try:
        from app.services.geo_extractor import geocode_location, process_document_locations
        
        # Get coordinates
        coords = geocode_location(location_name)
        if coords is None:
            raise HTTPException(
                status_code=404,
                detail=f"Location '{location_name}' not found"
            )
        
        # Get aggregated data
        all_locations = process_document_locations()
        location_data = next(
            (loc for loc in all_locations if loc["location_name"].lower() == location_name.lower()),
            None
        )
        
        if location_data:
            return {
                "name": location_data["location_name"],
                "coordinates": location_data["coordinates"],
                "mention_count": location_data["mention_count"],
                "intensity": location_data["intensity"],
                "sentiment": location_data["sentiment_score"],
                "first_mention": location_data["first_mention"],
                "last_mention": location_data["last_mention"],
                "contexts": location_data["contexts"]
            }
        else:
            return {
                "name": location_name,
                "coordinates": list(coords),
                "mention_count": 0,
                "intensity": 0,
                "sentiment": 0,
                "contexts": []
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[GEO API] Location lookup failed for '{location_name}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch location: {str(e)}")
