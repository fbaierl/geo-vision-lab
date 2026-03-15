"""
Geographic Entity Extraction Service

Extracts location entities from text using GLiNER (specialized NER model).
Stores location mentions with coordinates for heat map visualization.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
import re
import json

from geopy.geocoders import Nominatim
from geopy.exc import GeocoderUnavailable, GeocoderServiceError

from app.services.vector_store import get_collection
from app.services.llm import get_reasoning_llm

logger = logging.getLogger(__name__)

# Global instances (lazy loaded)
_geolocator = None
_gliner_model = None
_llm = None

# Entity types for geographic NER
GEO_ENTITY_TYPES = [
    "country",
    "city", 
    "region",
    "state",
    "province",
    "water_body",
    "landmark",
    "location"
]


def get_geolocator():
    """Load or return cached geolocator."""
    global _geolocator
    if _geolocator is None:
        _geolocator = Nominatim(user_agent="geovision_lab_geo_extractor", timeout=5)
        logger.info("[GEO] Initialized Nominatim geolocator")
    return _geolocator


def _get_gliner():
    """Load or return cached GLiNER model."""
    global _gliner_model
    if _gliner_model is None:
        try:
            from gliner import GLiNER
            # Load small model (~600MB, 50M params) - fast and accurate for NER
            _gliner_model = GLiNER.from_pretrained("knowledgator/gliner-x-small")
            logger.info("[GEO] Loaded GLiNER model for NER (knowledgator/gliner-x-small)")
        except Exception as e:
            logger.warning(f"[GEO] GLiNER not available: {e}")
            logger.info("[GEO] Falling back to LLM-based NER")
            _gliner_model = None
    return _gliner_model


def _get_llm():
    """Load or return cached LLM for fallback and date extraction."""
    global _llm
    if _llm is None:
        try:
            _llm = get_reasoning_llm()
            logger.info("[GEO] Using LLM for fallback extraction")
        except Exception as e:
            logger.warning(f"[GEO] LLM not available: {e}")
            _llm = None
    return _llm


def extract_locations_with_gliner(text: str) -> List[Dict[str, Any]]:
    """
    Extract geographic locations from text using GLiNER.
    
    GLiNER is a specialized NER model that's:
    - 180x smaller than LLM (600MB vs 4-9GB)
    - 100x faster than LLM inference
    - Zero-shot: can detect custom entity types
    - 81-83% F1 score across 60+ entity types
    """
    gliner = _get_gliner()
    if gliner is None:
        logger.warning("[GEO] GLiNER not available, falling back to LLM")
        return extract_locations_with_llm(text)
    
    try:
        # Truncate text if too long (GLiNER handles up to 512 tokens well)
        truncated_text = text[:2000] if len(text) > 2000 else text
        
        # Run NER with geographic entity types
        entities = gliner.predict_entities(truncated_text, GEO_ENTITY_TYPES)
        
        # Format results
        locations = []
        seen = set()
        for entity in entities:
            name = entity.get('text', '').strip()
            label = entity.get('label', 'location')
            
            # Skip duplicates and very short names
            if not name or len(name) < 2 or name in seen:
                continue
            
            seen.add(name)
            locations.append({
                "name": name,
                "type": label,
                "start": entity.get('start', 0),
                "end": entity.get('end', len(text))
            })
        
        logger.debug(f"[GEO] GLiNER extracted {len(locations)} locations")
        return locations
        
    except Exception as e:
        logger.error(f"[GEO] GLiNER extraction failed: {e}")
        return extract_locations_with_llm(text)


def extract_locations_with_llm(text: str) -> List[Dict[str, Any]]:
    """
    Fallback: Extract geographic locations from text using LLM.
    Used when GLiNER is not available.
    """
    llm = _get_llm()
    if llm is None:
        logger.warning("[GEO] LLM not available for extraction")
        return []
    
    # Truncate text if too long
    truncated_text = text[:4000] if len(text) > 4000 else text
    
    prompt = f"""Extract all geographic locations from the following text. Include countries, cities, regions, states, provinces, and notable geographic features.

Text: "{truncated_text}"

Return a JSON array of locations with this exact format:
[
    {{"name": "Location Name", "type": "country|city|region|water_body|other"}},
    ...
]

Only return the JSON array, no other text. If no locations found, return []."""

    try:
        response = llm.invoke(prompt)
        content = response.content if hasattr(response, 'content') else str(response)
        
        # Extract JSON from response
        json_match = re.search(r'\[.*\]', content, re.DOTALL)
        if json_match:
            locations = json.loads(json_match.group())
            logger.debug(f"[GEO] LLM extracted {len(locations)} locations")
            return locations
        return []
    except Exception as e:
        logger.error(f"[GEO] LLM extraction failed: {e}")
        return []


def extract_locations_from_text(text: str) -> List[Dict[str, Any]]:
    """
    Extract geographic locations from text.
    
    Uses GLiNER (specialized NER model) as primary method,
    falls back to LLM if GLiNER is unavailable.
    
    Returns list of dicts with:
    - name: Location name
    - type: Entity type (country, city, region, etc.)
    - context: Surrounding text context
    """
    if not text or len(text.strip()) == 0:
        return []
    
    # Use GLiNER for extraction (primary method)
    ner_locations = extract_locations_with_gliner(text)
    
    # Add context to each location
    locations = []
    for loc in ner_locations:
        name = loc.get('name', '')
        if not name:
            continue
            
        # Find location in text and get context
        name_lower = name.lower()
        text_lower = text.lower()
        start_idx = loc.get('start', text_lower.find(name_lower))
        
        if start_idx >= 0:
            context_start = max(0, start_idx - 50)
            context_end = min(len(text), start_idx + len(name) + 50)
            context = text[context_start:context_end]
        else:
            context = text[:200]  # Fallback
        
        locations.append({
            "name": name,
            "type": loc.get('type', 'location'),
            "context": context,
            "start": start_idx,
            "end": start_idx + len(name)
        })
    
    logger.debug(f"[GEO] Extracted {len(locations)} location entities from text")
    return locations


def extract_dates_from_text(text: str) -> List[str]:
    """
    Extract date references from text using LLM.
    
    GLiNER is NER-specific, so we use LLM for temporal extraction.
    """
    llm = _get_llm()
    if llm is None or not text:
        return []
    
    truncated_text = text[:2000] if len(text) > 2000 else text
    
    prompt = f"""Extract all date and time references from the following text.

Text: "{truncated_text}"

Return a JSON array of date strings found. Only return the array, no other text.
Example: ["2024-03-15", "last week", "January 2024"]

If no dates found, return []."""

    try:
        response = llm.invoke(prompt)
        content = response.content if hasattr(response, 'content') else str(response)
        
        json_match = re.search(r'\[.*\]', content, re.DOTALL)
        if json_match:
            dates = json.loads(json_match.group())
            return list(set(dates))  # Remove duplicates
        return []
    except Exception as e:
        logger.error(f"[GEO] LLM date extraction failed: {e}")
        return []


def analyze_sentiment(text: str) -> float:
    """
    Simple sentiment analysis for conflict detection.
    
    Returns score from -1.0 (negative/conflict) to 1.0 (positive/peaceful).
    """
    # Simple keyword-based sentiment for conflict detection
    conflict_keywords = [
        'war', 'conflict', 'attack', 'battle', 'fight', 'violence',
        'crisis', 'tension', 'threat', 'invasion', 'bombing',
        'casualty', 'death', 'destroyed', 'damaged', 'strike'
    ]
    
    peaceful_keywords = [
        'peace', 'agreement', 'treaty', 'cooperation', 'dialogue',
        'development', 'growth', 'improvement', 'aid', 'support'
    ]
    
    text_lower = text.lower()
    
    conflict_count = sum(1 for word in conflict_keywords if word in text_lower)
    peaceful_count = sum(1 for word in peaceful_keywords if word in text_lower)
    
    total = conflict_count + peaceful_count
    if total == 0:
        return 0.0
    
    # Negative score indicates conflict, positive indicates peace
    score = (peaceful_count - conflict_count) / total
    return max(-1.0, min(1.0, score))


def process_document_locations() -> List[Dict[str, Any]]:
    """
    Process all documents in the vector store and extract location data.
    
    Returns aggregated location data for heat map generation.
    """
    collection = get_collection()
    location_map = {}  # name -> aggregated data
    
    logger.info("[GEO] Processing documents for location extraction...")
    
    # Get all documents from the collection
    docs = collection.find({}, {"page_content": 1, "metadata": 1})
    
    for doc in docs:
        text = doc.get("page_content", "")
        if not text:
            continue

        doc_id = str(doc.get("_id", ""))
        
        # Extract locations
        locations = extract_locations_from_text(text)
        
        # Extract dates
        dates = extract_dates_from_text(text)
        
        # Analyze sentiment
        sentiment = analyze_sentiment(text)
        
        for loc in locations:
            name = loc["name"]
            
            # Skip if already processed this location in this doc
            if name in location_map and doc_id in location_map[name]["document_ids"]:
                continue
            
            # Geocode if not already cached
            if name not in location_map:
                coords = geocode_location(name)
                if coords is None:
                    continue  # Skip if we can't geocode
                
                location_map[name] = {
                    "location_name": name,
                    "coordinates": list(coords),
                    "mention_count": 0,
                    "document_ids": [],
                    "contexts": [],
                    "sentiment_scores": [],
                    "dates": [],
                    "location_type": loc["type"]
                }
            
            # Update aggregated data
            location_map[name]["mention_count"] += 1
            location_map[name]["document_ids"].append(doc_id)
            location_map[name]["contexts"].append(loc["context"][:200])
            location_map[name]["sentiment_scores"].append(sentiment)
            location_map[name]["dates"].extend(dates)
    
    # Calculate final metrics
    results = []
    for name, data in location_map.items():
        avg_sentiment = sum(data["sentiment_scores"]) / len(data["sentiment_scores"]) if data["sentiment_scores"] else 0.0
        
        # Calculate intensity based on mention count and sentiment
        # Higher mentions + more negative sentiment = higher intensity
        base_intensity = min(1.0, data["mention_count"] / 10.0)
        sentiment_factor = (1.0 - avg_sentiment) / 2.0  # Convert -1..1 to 0..1
        intensity = (base_intensity + sentiment_factor) / 2.0
        
        # Get date range
        unique_dates = list(set(data["dates"]))
        first_mention = min(unique_dates) if unique_dates else None
        last_mention = max(unique_dates) if unique_dates else None
        
        results.append({
            "location_name": data["location_name"],
            "coordinates": data["coordinates"],
            "mention_count": data["mention_count"],
            "document_ids": list(set(data["document_ids"])),
            "contexts": data["contexts"][:5],  # Keep top 5 contexts
            "sentiment_score": avg_sentiment,
            "intensity": intensity,
            "first_mention": first_mention,
            "last_mention": last_mention,
            "location_type": data["location_type"]
        })
    
    # Sort by intensity (highest first)
    results.sort(key=lambda x: x["intensity"], reverse=True)
    
    logger.info(f"[GEO] Extracted {len(results)} unique locations from documents")
    return results


def geocode_location(location_name: str) -> Optional[Tuple[float, float]]:
    """
    Geocode a location name to coordinates.

    Returns (latitude, longitude) or None if not found.
    """
    geolocator = get_geolocator()
    if geolocator is None:
        return None

    try:
        location = geolocator.geocode(location_name, timeout=5)
        if location:
            logger.debug(f"[GEO] Geocoded '{location_name}' -> ({location.latitude}, {location.longitude})")
            return (location.latitude, location.longitude)
        else:
            logger.debug(f"[GEO] Could not geocode '{location_name}'")
            return None
    except (GeocoderUnavailable, GeocoderServiceError) as e:
        logger.warning(f"[GEO] Geocoding service unavailable for '{location_name}': {e}")
        return None
    except Exception as e:
        logger.error(f"[GEO] Geocoding error for '{location_name}': {e}")
        return None


def get_heatmap_data(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    min_intensity: float = 0.1
) -> List[Dict[str, Any]]:
    """
    Get heat map data with optional filtering.
    
    Args:
        date_from: Filter locations mentioned after this date
        date_to: Filter locations mentioned before this date
        min_intensity: Minimum intensity threshold (0.0-1.0)
    
    Returns:
        List of heat points with coordinates and intensity
    """
    locations = process_document_locations()
    
    # Apply filters
    filtered = []
    for loc in locations:
        # Intensity filter
        if loc["intensity"] < min_intensity:
            continue
        
        # Date filters (basic string comparison for now)
        if date_from and loc["last_mention"] and loc["last_mention"] < date_from:
            continue
        if date_to and loc["first_mention"] and loc["first_mention"] > date_to:
            continue
        
        filtered.append({
            "lat": loc["coordinates"][0],
            "lng": loc["coordinates"][1],
            "intensity": loc["intensity"],
            "name": loc["location_name"],
            "mention_count": loc["mention_count"],
            "sentiment": loc["sentiment_score"]
        })
    
    return filtered


def get_location_clusters(query: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Get clusters of locations mentioned together in documents.
    
    Args:
        query: Optional query to filter clusters by topic
    
    Returns:
        List of clusters with locations and connections
    """
    collection = get_collection()
    clusters = []
    
    logger.info("[GEO] Analyzing location clusters...")
    
    # Get documents and extract co-occurring locations
    docs = collection.find({}, {"page_content": 1})
    
    co_occurrence_map = {}  # (loc1, loc2) -> count
    
    for doc in docs:
        text = doc.get("page_content", "")
        locations = extract_locations_from_text(text)
        
        if len(locations) < 2:
            continue
        
        # Record co-occurrences
        location_names = [loc["name"] for loc in locations]
        for i, loc1 in enumerate(location_names):
            for loc2 in location_names[i+1:]:
                if loc1 == loc2:
                    continue
                pair = tuple(sorted([loc1, loc2]))
                co_occurrence_map[pair] = co_occurrence_map.get(pair, 0) + 1
    
    # Build clusters from strong co-occurrences
    threshold = 2  # Minimum co-occurrences to form a connection
    location_clusters = {}
    
    for (loc1, loc2), count in co_occurrence_map.items():
        if count >= threshold:
            # Add to cluster
            if loc1 not in location_clusters:
                location_clusters[loc1] = {"locations": set(), "connections": []}
            if loc2 not in location_clusters:
                location_clusters[loc2] = {"locations": set(), "connections": []}
            
            location_clusters[loc1]["locations"].add(loc2)
            location_clusters[loc2]["locations"].add(loc1)
            location_clusters[loc1]["connections"].append((loc2, count))
            location_clusters[loc2]["connections"].append((loc1, count))
    
    # Convert to output format with coordinates
    for loc_name, cluster_data in location_clusters.items():
        coords = geocode_location(loc_name)
        if coords is None:
            continue
        
        cluster = {
            "center": {
                "name": loc_name,
                "lat": coords[0],
                "lng": coords[1]
            },
            "related_locations": [],
            "connections": []
        }
        
        for related_name, strength in cluster_data["connections"]:
            related_coords = geocode_location(related_name)
            if related_coords:
                cluster["related_locations"].append({
                    "name": related_name,
                    "lat": related_coords[0],
                    "lng": related_coords[1],
                    "strength": strength
                })
                cluster["connections"].append({
                    "from": [coords[0], coords[1]],
                    "to": [related_coords[0], related_coords[1]],
                    "strength": strength
                })
        
        if cluster["related_locations"]:
            clusters.append(cluster)
    
    logger.info(f"[GEO] Found {len(clusters)} location clusters")
    return clusters


def get_territory_boundary(location_name: str) -> Optional[Dict[str, Any]]:
    """
    Get GeoJSON boundary for a country or region.
    
    Uses Nominatim to fetch boundary polygons.
    """
    geolocator = get_geolocator()
    
    try:
        # Search for the location with polygon data
        location = geolocator.geocode(
            location_name,
            timeout=10,
            addressdetails=True,
            polygon_geojson=1
        )
        
        if location and hasattr(location, 'raw') and 'geojson' in location.raw:
            geojson = location.raw['geojson']
            
            # Determine controlling faction based on location type
            # (This is a placeholder - real implementation would need conflict data)
            faction = "neutral"
            if location.raw.get('address', {}).get('country_code', '').upper() in ['RU', 'UA']:
                faction = "contested"
            
            return {
                "type": "Feature",
                "properties": {
                    "name": location_name,
                    "faction": faction,
                    "status": "active"
                },
                "geometry": geojson
            }
        
        # Fallback: try country-level search
        if location and location.raw.get('address', {}).get('country'):
            country = location.raw['address']['country']
            country_location = geolocator.geocode(
                country,
                timeout=10,
                polygon_geojson=1
            )
            
            if country_location and hasattr(country_location, 'raw') and 'geojson' in country_location.raw:
                return {
                    "type": "Feature",
                    "properties": {
                        "name": country,
                        "faction": "neutral",
                        "status": "stable"
                    },
                    "geometry": country_location.raw['geojson']
                }
        
        return None
        
    except Exception as e:
        logger.error(f"[GEO] Error fetching territory boundary for '{location_name}': {e}")
        return None
