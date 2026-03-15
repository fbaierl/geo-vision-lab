import logging
import spacy
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
from typing import List, Dict, Any, Optional
import time

logger = logging.getLogger("agent_flow")

# Cache for geocoding results to avoid repeated API calls
_geocode_cache: Dict[str, Optional[Dict[str, Any]]] = {}

# Load spaCy model - using en_core_web_sm for NER
# This model can identify GPE (geopolitical entities), LOC (locations), and FAC (facilities)
_nlp = None


def get_ner_model():
    """Lazy load the spaCy NER model."""
    global _nlp
    if _nlp is None:
        try:
            _nlp = spacy.load("en_core_web_sm")
            logger.info("[LOCATION_EXTRACTOR] Loaded spaCy en_core_web_sm model")
        except OSError:
            logger.warning("[LOCATION_EXTRACTOR] spaCy model not found. Downloading...")
            import subprocess
            subprocess.run(["python", "-m", "spacy", "download", "en_core_web_sm"], check=True)
            _nlp = spacy.load("en_core_web_sm")
            logger.info("[LOCATION_EXTRACTOR] Successfully downloaded and loaded spaCy model")
    return _nlp


def extract_locations_with_ner(text: str) -> List[Dict[str, str]]:
    """
    Extract geographic locations from text using spaCy NER.
    
    Returns list of dicts with 'name' and 'type' keys.
    """
    nlp = get_ner_model()
    doc = nlp(text)
    
    locations = []
    seen = set()
    
    for ent in doc.ents:
        # GPE = Geopolitical Entity (countries, cities, states)
        # LOC = Location (non-gpe locations like mountains, bodies of water)
        # FAC = Facility (airports, buildings, etc.)
        if ent.label_ in ["GPE", "LOC", "FAC"]:
            if ent.text not in seen:
                seen.add(ent.text)
                loc_type = {
                    "GPE": "city",  # Could be country, city, or state - we'll geocode to find out
                    "LOC": "landmark",
                    "FAC": "landmark"
                }.get(ent.label_, "other")
                
                locations.append({
                    "name": ent.text,
                    "type": loc_type,
                    "label": ent.label_  # Keep original spaCy label for reference
                })
    
    logger.info(f"[LOCATION_EXTRACTOR] Found {len(locations)} location(s) via NER: {[loc['name'] for loc in locations]}")
    return locations


def geocode_location(location_name: str) -> Optional[Dict[str, Any]]:
    """
    Geocode a location name using Nominatim (OpenStreetMap).
    
    Returns dict with 'lat', 'lon', 'type', 'display_name' or None if not found.
    """
    # Check cache first
    if location_name in _geocode_cache:
        logger.debug(f"[LOCATION_EXTRACTOR] Cache hit for: {location_name}")
        return _geocode_cache[location_name]
    
    try:
        # Nominatim requires a user_agent
        geolocator = Nominatim(user_agent="geovision_lab_location_extractor")
        
        # Try geocoding
        location = geolocator.geocode(location_name, timeout=10)
        
        if location:
            result = {
                "lat": location.latitude,
                "lon": location.longitude,
                "display_name": location.address,
                "found": True
            }
            
            # Try to determine more specific type from the address
            address_lower = location.address.lower()
            if "country" in address_lower or "nation" in address_lower:
                result["type"] = "country"
            elif "city" in address_lower or "town" in address_lower or "village" in address_lower:
                result["type"] = "city"
            elif "state" in address_lower or "province" in address_lower or "region" in address_lower:
                result["type"] = "region"
            else:
                result["type"] = "landmark"
            
            logger.debug(f"[LOCATION_EXTRACTOR] Geocoded '{location_name}' to ({result['lat']}, {result['lon']})")
            _geocode_cache[location_name] = result
            return result
        else:
            logger.debug(f"[LOCATION_EXTRACTOR] No results for: {location_name}")
            _geocode_cache[location_name] = None
            return None
            
    except (GeocoderTimedOut, GeocoderServiceError) as e:
        logger.warning(f"[LOCATION_EXTRACTOR] Geocoding error for '{location_name}': {e}")
        _geocode_cache[location_name] = None
        return None


def extract_and_geocode_locations(text: str) -> List[Dict[str, Any]]:
    """
    Full pipeline: Extract locations with NER, then geocode each one.
    
    Returns list of location dicts with name, type, lat, lon.
    Only includes locations that were successfully geocoded.
    """
    # Step 1: Extract locations using NER
    ner_locations = extract_locations_with_ner(text)
    
    if not ner_locations:
        return []
    
    # Step 2: Geocode each location
    geocoded_locations = []
    
    for loc in ner_locations:
        # Small delay to respect Nominatim's rate limiting (1 request per second)
        time.sleep(0.1)
        
        geo_result = geocode_location(loc["name"])
        
        if geo_result and geo_result.get("found"):
            geocoded_locations.append({
                "name": loc["name"],
                "type": geo_result.get("type", loc["type"]),
                "lat": geo_result["lat"],
                "lon": geo_result["lon"],
                "display_name": geo_result.get("display_name", "")
            })
    
    logger.info(f"[LOCATION_EXTRACTOR] Successfully geocoded {len(geocoded_locations)}/{len(ner_locations)} locations")
    return geocoded_locations
