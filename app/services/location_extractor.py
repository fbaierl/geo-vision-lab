"""
Location Extractor Pipeline
============================

This module extracts geographic locations from text using a 2-step pipeline:
1. NER extraction to find location names
2. Geocoding to get ALL candidates from Nominatim

The extractor returns ALL candidates without filtering - the prioritizer node
is responsible for selecting relevant locations based on the query context.

All dependencies are injected via the DI container - no global state.
"""

import logging
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError, GeocoderQuotaExceeded
from typing import List, Dict, Any, Optional
import time
import os

from app.core.di_nlp import get_ner_pipeline
from app.core.di_nlp import get_geocode_cache

logger = logging.getLogger("agent_flow")

# Nominatim URL configuration
NOMINATIM_URL = os.getenv("NOMINATIM_URL", None)
NOMINATIM_TIMEOUT = int(os.getenv("NOMINATIM_TIMEOUT", "10"))


class LocationExtractorService:
    """
    Location extractor service with explicit dependencies.

    Usage:
        from app.core.di_nlp import get_ner_pipeline, get_geocode_cache

        service = LocationExtractorService(
            ner_pipeline=get_ner_pipeline(),
            geocode_cache=get_geocode_cache()
        )
    """

    def __init__(
        self,
        ner_pipeline: Any,
        geocode_cache: Optional[Dict[str, Optional[List[Dict[str, Any]]]]] = None
    ):
        self.ner_pipeline = ner_pipeline
        self.geocode_cache = geocode_cache if geocode_cache is not None else {}
        self.geocoding_errors = []

    def extract_locations_with_ner(self, text: str) -> List[Dict[str, str]]:
        """
        Extract geographic locations from text using Hugging Face NER.

        Returns list of dicts with 'name' and 'type' keys.
        Skips entities shorter than 3 characters to filter out abbreviations
        like 'IRA', 'UN', 'EU' that are often misclassified as locations.
        """
        try:
            ner_results = self.ner_pipeline(text)

            locations = []
            seen = set()

            for entity in ner_results:
                entity_label = entity.get("entity_group", entity.get("label", ""))
                entity_text = entity.get("word", entity.get("entity_text", ""))

                # Skip entities shorter than 3 characters (filters out abbreviations)
                if len(entity_text) < 3:
                    continue

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

            logger.info(f"[LOCATION_EXTRACTOR] Found {len(locations)} location(s) via NER")
            return locations
        except Exception as e:
            logger.error(f"[LOCATION_EXTRACTOR] NER pipeline error: {e}")
            return []

    def geocode_location(self, location_name: str) -> List[Dict[str, Any]]:
        """
        Geocode a location name using Nominatim (OpenStreetMap).

        Returns ALL geocoding candidates (not just the first match).
        Handles rate limiting gracefully with retries.
        """
        # Check cache first
        if location_name in self.geocode_cache:
            logger.debug(f"[LOCATION_EXTRACTOR] Cache hit for: {location_name}")
            cached = self.geocode_cache[location_name]
            return cached if cached else []

        max_retries = 3
        retry_delay = 2.0

        for attempt in range(max_retries):
            try:
                # Use custom URL if configured (self-hosted Nominatim)
                if NOMINATIM_URL:
                    from geopy.adapters import HTTPAdapter
                    geolocator = Nominatim(
                        user_agent="geovision_lab_location_extractor",
                        adapter_factory=HTTPAdapter
                    )
                    # Override default URL
                    geolocator.base_url = NOMINATIM_URL.replace('/search', '')
                else:
                    geolocator = Nominatim(user_agent="geovision_lab_location_extractor")

                results = geolocator.geocode(
                    location_name,
                    timeout=NOMINATIM_TIMEOUT,
                    addressdetails=1,
                    limit=10,
                    exactly_one=False
                )

                if not results:
                    logger.debug(f"[LOCATION_EXTRACTOR] No results for: {location_name}")
                    self.geocode_cache[location_name] = []
                    return []

                candidates = []
                for result in results:
                    raw_address = result.raw.get('address', {})

                    candidate = {
                        "name": location_name,
                        "lat": result.latitude,
                        "lon": result.longitude,
                        "display_name": result.address,
                        "type": self._classify_location_type(raw_address),
                        "country": raw_address.get('country', 'Unknown'),
                        "state": raw_address.get('state', ''),
                        "city": raw_address.get('city', raw_address.get('town', ''))
                    }
                    candidates.append(candidate)

                logger.debug(f"[LOCATION_EXTRACTOR] Found {len(candidates)} candidate(s) for '{location_name}'")
                self.geocode_cache[location_name] = candidates
                return candidates

            except GeocoderQuotaExceeded as e:
                logger.warning(
                    f"[LOCATION_EXTRACTOR] Rate limit hit for '{location_name}' "
                    f"(attempt {attempt + 1}/{max_retries}): {e}"
                )
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))  # Exponential backoff
                else:
                    error_msg = f"Nominatim rate limit exceeded after {max_retries} attempts. Consider using self-hosted Nominatim."
                    self.geocoding_errors.append({
                        "location": location_name,
                        "error": "rate_limit",
                        "message": error_msg
                    })
                    logger.error(f"[LOCATION_EXTRACTOR] {error_msg}")
                    self.geocode_cache[location_name] = []
                    return []

            except (GeocoderTimedOut, GeocoderServiceError) as e:
                logger.warning(f"[LOCATION_EXTRACTOR] Geocoding error for '{location_name}': {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                else:
                    self.geocode_cache[location_name] = []
                    return []

        self.geocode_cache[location_name] = []
        return []

    def _classify_location_type(self, address: Dict[str, Any]) -> str:
        """
        Classify location type from Nominatim address data.

        Priority: country > state > city > town > village > landmark
        """
        if 'country' in address and len(address) == 1:
            return "country"
        elif 'state' in address and 'country' in address and len(address) <= 3:
            return "region"
        elif 'city' in address:
            return "city"
        elif 'town' in address:
            return "town"
        elif 'village' in address:
            return "village"
        elif 'suburb' in address or 'neighbourhood' in address:
            return "neighbourhood"
        else:
            return "landmark"

    def extract_and_geocode_locations(
        self,
        text: str,
        query: str = "",
        response_text: str = ""
    ) -> List[Dict[str, Any]]:
        """
        Full pipeline: Extract locations with NER and geocode with ALL candidates.
        
        Returns ALL geocoded candidates without filtering.
        The prioritizer node is responsible for selecting relevant locations.
        
        Note: query and response_text parameters are kept for API compatibility
        but are no longer used for filtering.
        """
        # STEP 1: Extract locations with NER
        ner_locations = self.extract_locations_with_ner(text)

        if not ner_locations:
            return []

        # STEP 2: Get ALL geocoding candidates for each location
        all_candidates = []
        for loc in ner_locations:
            time.sleep(0.1)  # Rate limiting
            candidates = self.geocode_location(loc["name"])
            if candidates:
                # Add all candidates to the result list
                all_candidates.extend(candidates)
                logger.debug(
                    f"[LOCATION_EXTRACTOR] {loc['name']}: {len(candidates)} candidate(s) found"
                )

        logger.info(
            f"[LOCATION_EXTRACTOR] Pipeline complete: {len(all_candidates)} total candidate(s)"
        )
        return all_candidates


# =============================================================================
# DI factory function
# =============================================================================

def get_location_extractor() -> LocationExtractorService:
    """
    Get location extractor service with dependencies from DI container.

    This is the recommended way to get a LocationExtractorService instance.
    """
    return LocationExtractorService(
        ner_pipeline=get_ner_pipeline(),
        geocode_cache=get_geocode_cache()
    )
