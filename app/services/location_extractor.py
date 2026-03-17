"""
Location Extractor Pipeline
============================

This module extracts geographic locations from text and validates them
using a 3-step pipeline with NO hardcoding and NO heuristics.

All dependencies are injected via the DI container - no global state.
"""

import logging
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
from typing import List, Dict, Any, Optional
import time
import re
import json

from langchain_ollama import ChatOllama
from app.core.di_nlp import get_ner_pipeline
from app.core.di_llm import get_reviewer_llm
from app.core.di_nlp import get_geocode_cache

logger = logging.getLogger("agent_flow")


class LocationExtractorService:
    """
    Location extractor service with explicit dependencies.
    
    Usage:
        # With DI (recommended)
        from app.core.di import get_location_extractor_service
        service = LocationExtractorService(**get_location_extractor_service())
        
        # Or with explicit dependencies
        service = LocationExtractorService(
            ner_pipeline=pipeline,
            reviewer_llm=llm,
            geocode_cache={}
        )
    """
    
    def __init__(
        self,
        ner_pipeline: Any,
        reviewer_llm: ChatOllama,
        geocode_cache: Optional[Dict[str, Optional[List[Dict[str, Any]]]]] = None
    ):
        self.ner_pipeline = ner_pipeline
        self.reviewer_llm = reviewer_llm
        self.geocode_cache = geocode_cache if geocode_cache is not None else {}
    
    def extract_locations_with_ner(self, text: str) -> List[Dict[str, str]]:
        """
        Extract geographic locations from text using Hugging Face NER.

        Returns list of dicts with 'name' and 'type' keys.
        """
        ner_results = self.ner_pipeline(text)

        locations = []
        seen = set()

        for entity in ner_results:
            entity_label = entity.get("entity_group", entity.get("label", ""))
            entity_text = entity.get("word", entity.get("entity_text", ""))

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
    
    def geocode_location(self, location_name: str) -> List[Dict[str, Any]]:
        """
        Geocode a location name using Nominatim (OpenStreetMap).

        Returns ALL geocoding candidates (not just the first match).
        """
        # Check cache first
        if location_name in self.geocode_cache:
            logger.debug(f"[LOCATION_EXTRACTOR] Cache hit for: {location_name}")
            cached = self.geocode_cache[location_name]
            return cached if cached else []

        try:
            geolocator = Nominatim(user_agent="geovision_lab_location_extractor")

            results = geolocator.geocode(
                location_name,
                timeout=10,
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

        except (GeocoderTimedOut, GeocoderServiceError) as e:
            logger.warning(f"[LOCATION_EXTRACTOR] Geocoding error for '{location_name}': {e}")
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
    
    def select_valid_locations(
        self,
        location_candidates: List[List[Dict[str, Any]]],
        query: str,
        response_text: str
    ) -> List[Dict[str, Any]]:
        """
        Use LLM to select valid locations from all geocoding candidates.

        This is the SOLE decision-making step. No filtering, no heuristics.
        """
        if not location_candidates:
            return []

        if not query:
            return [candidates[0] for candidates in location_candidates if candidates]

        # Build candidate display for prompt
        candidate_text = ""
        for i, candidates in enumerate(location_candidates):
            if not candidates:
                continue
            candidate_text += f"\n{i+1}. {candidates[0]['name']}:\n"
            for j, c in enumerate(candidates):
                candidate_text += (
                    f"   {j+1}) {c['display_name']} "
                    f"(Type: {c['type']}, Country: {c['country']})\n"
                )

        prompt = f"""You are a geographic location validator for a geopolitical intelligence platform.

USER QUERY: {query}

EXTRACTED LOCATIONS (all geocoding candidates shown):
{candidate_text}

RESPONSE CONTEXT:
{response_text[:500] if response_text else 'N/A'}

TASK:
Select which locations are VALID for this query by choosing the correct candidate.

A location is VALID if:
- The geocoding matches the intended place in the query context
- Example: "Iran" should match Iran (country), not Iran, Texas
- Example: "IRA" in context of "iran vs israel" should be excluded (no valid Iran option)

Respond ONLY with a JSON array of objects:
[
  {{"location_index": 0, "candidate_index": 0, "reason": "Iran country matches query context"}},
  {{"location_index": 2, "candidate_index": 0, "reason": "Tel Aviv is city in Israel"}}
]

- location_index: Index of the location (0-indexed)
- candidate_index: Index of the candidate to use (0-indexed)
- reason: Brief explanation

If no locations are valid, respond with empty array: []"""

        try:
            response = self.reviewer_llm.invoke(prompt)
            response_content = response.content if hasattr(response, 'content') else str(response)

            # Parse JSON from response
            json_match = re.search(r'\[.*\]', response_content, re.DOTALL)
            if not json_match:
                logger.warning(f"[LOCATION_EXTRACTOR] Could not parse LLM response: {response_content}")
                return [candidates[0] for candidates in location_candidates if candidates]

            selections = json.loads(json_match.group())

            # Build result from selections
            result = []
            for selection in selections:
                loc_idx = selection.get('location_index')
                cand_idx = selection.get('candidate_index')

                if loc_idx is not None and cand_idx is not None:
                    if 0 <= loc_idx < len(location_candidates):
                        candidates = location_candidates[loc_idx]
                        if 0 <= cand_idx < len(candidates):
                            result.append(candidates[cand_idx])
                            logger.info(
                                f"[LOCATION_EXTRACTOR] Selected: {candidates[cand_idx]['name']} → "
                                f"{candidates[cand_idx]['display_name']} ({selection.get('reason', 'no reason')})"
                            )

            logger.info(f"[LOCATION_EXTRACTOR] LLM selected {len(result)}/{len(location_candidates)} locations")
            return result

        except Exception as e:
            logger.error(f"[LOCATION_EXTRACTOR] LLM selection failed: {e}")
            return [candidates[0] for candidates in location_candidates if candidates]
    
    def extract_and_geocode_locations(
        self,
        text: str,
        query: str = "",
        response_text: str = ""
    ) -> List[Dict[str, Any]]:
        """
        Full pipeline: Extract locations with NER, geocode with ALL candidates,
        and use LLM to select valid locations.
        """
        # STEP 1: Extract locations with NER
        ner_locations = self.extract_locations_with_ner(text)

        if not ner_locations:
            return []

        # STEP 2: Get ALL geocoding candidates for each location
        location_candidates = []
        for loc in ner_locations:
            time.sleep(0.1)  # Rate limiting
            candidates = self.geocode_location(loc["name"])
            if candidates:
                location_candidates.append(candidates)
                logger.debug(
                    f"[LOCATION_EXTRACTOR] {loc['name']}: {len(candidates)} candidate(s) found"
                )

        if not location_candidates:
            return []

        # STEP 3: LLM selects valid locations
        validated_locations = self.select_valid_locations(
            location_candidates,
            query=query,
            response_text=response_text
        )

        logger.info(
            f"[LOCATION_EXTRACTOR] Pipeline complete: {len(validated_locations)} validated location(s)"
        )
        return validated_locations


# =============================================================================
# Backward-compatible functions (using DI internally)
# =============================================================================

def get_location_extractor() -> LocationExtractorService:
    """
    Get location extractor service with dependencies from DI container.

    This is the recommended way to get a LocationExtractorService instance.
    """
    return LocationExtractorService(
        ner_pipeline=get_ner_pipeline(),
        reviewer_llm=get_reviewer_llm(),
        geocode_cache=get_geocode_cache()
    )


# Legacy function wrappers for backward compatibility

def extract_and_geocode_locations(
    text: str,
    query: str = "",
    response_text: str = ""
) -> List[Dict[str, Any]]:
    """Extract and geocode locations (legacy wrapper using DI)."""
    return get_location_extractor().extract_and_geocode_locations(text, query, response_text)
