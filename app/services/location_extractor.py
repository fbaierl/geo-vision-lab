import logging
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
from typing import List, Dict, Any, Optional
import time

logger = logging.getLogger("agent_flow")

# Cache for geocoding results to avoid repeated API calls
_geocode_cache: Dict[str, Optional[Dict[str, Any]]] = {}

# Hugging Face NER model - using dslim/bert-base-NER for location extraction
# This model can identify LOC (locations), GPE (geopolitical entities), and FAC (facilities)
_ner_pipeline = None


def get_ner_pipeline():
    """Lazy load the Hugging Face NER pipeline."""
    global _ner_pipeline
    if _ner_pipeline is None:
        try:
            from transformers import AutoTokenizer, AutoModelForTokenClassification
            from transformers import pipeline
            
            model_name = "dslim/bert-base-NER"
            tokenizer = AutoTokenizer.from_pretrained(model_name)
            model = AutoModelForTokenClassification.from_pretrained(model_name)
            _ner_pipeline = pipeline(
                "ner",
                model=model,
                tokenizer=tokenizer,
                aggregation_strategy="simple"
            )
            logger.info("[LOCATION_EXTRACTOR] Loaded Hugging Face NER model: dslim/bert-base-NER")
        except Exception as e:
            logger.error(f"[LOCATION_EXTRACTOR] Failed to load NER model: {e}")
            raise
    return _ner_pipeline


def extract_locations_with_ner(text: str) -> List[Dict[str, str]]:
    """
    Extract geographic locations from text using Hugging Face NER.

    Returns list of dicts with 'name' and 'type' keys.
    Note: The type is a preliminary classification based on NER labels.
    For accurate types, use extract_and_geocode_locations() which geocodes via Nominatim.
    """
    ner_pipeline = get_ner_pipeline()
    ner_results = ner_pipeline(text)

    locations = []
    seen = set()

    for entity in ner_results:
        # Hugging Face NER returns: LOC, GPE, FAC, ORG, PER, etc.
        entity_label = entity.get("entity_group", entity.get("label", ""))
        entity_text = entity.get("word", entity.get("entity_text", ""))

        # Only process location-related entities
        if entity_label in ["LOC", "GPE", "FAC"]:
            if entity_text not in seen:
                seen.add(entity_text)
                loc_type = {
                    "GPE": "country",
                    "LOC": "landmark",
                    "FAC": "landmark"
                }.get(entity_label, "other")

                locations.append({
                    "name": entity_text,
                    "type": loc_type,
                    "label": entity_label
                })

    logger.info(f"[LOCATION_EXTRACTOR] Found {len(locations)} location(s) via NER: {[loc['name'] for loc in locations]}")
    return locations


def geocode_location(location_name: str) -> Optional[Dict[str, Any]]:
    """
    Geocode a location name using Nominatim (OpenStreetMap).

    Returns dict with 'lat', 'lon', 'type', 'display_name'.

    Location type is determined using Nominatim's structured address data.
    """
    # Check cache first
    if location_name in _geocode_cache:
        logger.debug(f"[LOCATION_EXTRACTOR] Cache hit for: {location_name}")
        return _geocode_cache[location_name]

    try:
        geolocator = Nominatim(user_agent="geovision_lab_location_extractor")
        location = geolocator.geocode(location_name, timeout=10, addressdetails=1)

        if location:
            result = {
                "lat": location.latitude,
                "lon": location.longitude,
                "display_name": location.address,
                "found": True
            }

            raw_address = location.raw.get('address', {})

            if 'country' in raw_address and len(raw_address) == 1:
                result["type"] = "country"
            elif 'country_code' in raw_address and 'state' in raw_address:
                result["type"] = "region"
            elif 'state' in raw_address and raw_address.get('state') != raw_address.get('country'):
                result["type"] = "region"
            elif 'city' in raw_address or 'town' in raw_address or 'village' in raw_address:
                result["type"] = "city"
            elif 'county' in raw_address or 'municipality' in raw_address:
                result["type"] = "region"
            else:
                result["type"] = "landmark"

            logger.debug(f"[LOCATION_EXTRACTOR] Geocoded '{location_name}' to ({result['lat']}, {result['lon']}) as {result['type']}")
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
    ner_locations = extract_locations_with_ner(text)

    if not ner_locations:
        return []

    geocoded_locations = []

    for loc in ner_locations:
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
