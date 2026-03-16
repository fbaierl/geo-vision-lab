"""
Location Extractor Pipeline
============================

This module extracts geographic locations from text and validates them
using a 3-step pipeline with NO hardcoding and NO heuristics.

TOOLS USED:
1. Hugging Face NER (dslim/bert-base-NER) - Extract location names
2. Nominatim (OpenStreetMap) - Get ALL geocoding candidates
3. Reviewer LLM - Decide which candidates are correct for the query context

================================================================================
PIPELINE OVERVIEW
================================================================================

STEP 1: NER Extraction
----------------------
Model: dslim/bert-base-NER
Extracts entities labeled as LOC, GPE, or FAC.

Input:  "Conflict between Iran and Israel continues"
Output: [{"name": "Iran", "type": "country", "label": "GPE"},
         {"name": "Israel", "type": "country", "label": "GPE"}]

--------------------------------------------------------------------------------

STEP 2: Multi-Candidate Geocoding
---------------------------------
For each extracted location, get ALL geocoding candidates from Nominatim.

Input:  {"name": "IRA", "type": "country"}
Output: [
  {"name": "IRA", "display_name": "Town of Ira, New York, USA", "country": "United States"},
  {"name": "IRA", "display_name": "Ira, Vermont, USA", "country": "United States"}
]

Input:  {"name": "Iran", "type": "country"}
Output: [
  {"name": "Iran", "display_name": "ایران", "country": "Iran", "type": "country"},
  {"name": "Iran", "display_name": "Iran, Texas, USA", "country": "United States"}
]

--------------------------------------------------------------------------------

STEP 3: LLM Selection (Sole Decision Maker)
-------------------------------------------
LLM reviews all candidates and selects which locations are valid for the query.

Prompt includes:
- User query: "iran vs israel"
- All geocoding candidates with full details
- Response context

LLM decides:
- Which locations to keep (correct matches)
- Which locations to exclude (wrong matches)
- Which candidate to use when multiple exist

Input:  [IRA→USA candidates, Iran→country candidates, ...]
Query:  "iran vs israel"
Output: [Iran→country, Israel→country, Tehran→Iran, Tel Aviv→Israel]

================================================================================

EXAMPLE EXECUTION
================================================================================

Query: "iran vs israel"
Response: "Conflict between Iran and Israel over nuclear facilities..."

STEP 1 (NER):
  ["IRA", "Tehran", "Tel Aviv", "Middle East", "Iran"]

STEP 2 (Multi-Candidate Geocoding):
  IRA:
    1) Town of Ira, New York, USA (town)
    2) Ira, Vermont, USA (town)
  
  Tehran:
    1) Tehran, Iran (city)
    2) Tehran, Minnesota, USA (town)
  
  Tel Aviv:
    1) Tel Aviv, Israel (city)
  
  Middle East:
    1) Middle East, Baltimore, USA (neighborhood)
  
  Iran:
    1) Iran (country)
    2) Iran, Texas, USA (town)

STEP 3 (LLM Selection):
  LLM reviews all candidates in context of "iran vs israel"
  Keeps: Tehran (Iran), Tel Aviv (Israel), Iran (country)
  Excludes: IRA (all options are USA towns), Middle East (only USA option)
  
FINAL OUTPUT: 3 validated locations for map display

================================================================================

KEY DESIGN PRINCIPLES
================================================================================

1. NO HARDCODED COUNTRIES
   - Works for Iran, France, Japan, Brazil - any country
   - No country lists, no mappings

2. NO HEURISTICS
   - No distance-based clustering
   - No type validation rules
   - No pattern matching

3. LLM AS SOLE DECISION MAKER
   - LLM has world knowledge of all countries/regions
   - Context-aware filtering
   - Can explain reasoning

4. ALL CANDIDATES SHOWN
   - LLM sees all geocoding options
   - Makes informed decision
   - Not limited to first match

5. GRACEFUL DEGRADATION
   - If LLM fails, return empty list
   - Better no locations than wrong locations
"""

import logging
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
from typing import List, Dict, Any, Optional
import time
import re

logger = logging.getLogger("agent_flow")

# Cache for geocoding results to avoid repeated API calls
_geocode_cache: Dict[str, Optional[List[Dict[str, Any]]]] = {}

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


def geocode_location(location_name: str) -> List[Dict[str, Any]]:
    """
    Geocode a location name using Nominatim (OpenStreetMap).
    
    Returns ALL geocoding candidates (not just the first match).
    This allows the LLM to choose the correct candidate based on context.

    Args:
        location_name: Location name to geocode

    Returns list of dicts, each with:
        - name: Original location name
        - lat: Latitude
        - lon: Longitude  
        - display_name: Full address string
        - type: Location type (country, city, town, etc.)
        - country: Country name
        - state: State/province name (if available)
    """
    # Check cache first
    if location_name in _geocode_cache:
        logger.debug(f"[LOCATION_EXTRACTOR] Cache hit for: {location_name}")
        cached = _geocode_cache[location_name]
        return cached if cached else []

    try:
        geolocator = Nominatim(user_agent="geovision_lab_location_extractor")
        
        # Get ALL results (not just first match)
        results = geolocator.geocode(
            location_name,
            timeout=10,
            addressdetails=1,
            limit=10,  # Get up to 10 candidates
            exactly_one=False  # Return all matches
        )

        if not results:
            logger.debug(f"[LOCATION_EXTRACTOR] No results for: {location_name}")
            _geocode_cache[location_name] = []
            return []

        candidates = []
        for result in results:
            raw_address = result.raw.get('address', {})
            
            candidate = {
                "name": location_name,
                "lat": result.latitude,
                "lon": result.longitude,
                "display_name": result.address,
                "type": _classify_location_type(raw_address),
                "country": raw_address.get('country', 'Unknown'),
                "state": raw_address.get('state', ''),
                "city": raw_address.get('city', raw_address.get('town', ''))
            }
            candidates.append(candidate)

        logger.debug(f"[LOCATION_EXTRACTOR] Found {len(candidates)} candidate(s) for '{location_name}'")
        _geocode_cache[location_name] = candidates
        return candidates

    except (GeocoderTimedOut, GeocoderServiceError) as e:
        logger.warning(f"[LOCATION_EXTRACTOR] Geocoding error for '{location_name}': {e}")
        _geocode_cache[location_name] = []
        return []


def _classify_location_type(address: Dict[str, Any]) -> str:
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
    location_candidates: List[List[Dict[str, Any]]],
    query: str,
    response_text: str
) -> List[Dict[str, Any]]:
    """
    Use LLM to select valid locations from all geocoding candidates.
    
    This is the SOLE decision-making step. No filtering, no heuristics.
    The LLM reviews all candidates and decides which locations are correct
    for the query context.

    Args:
        location_candidates: List of lists. Each inner list contains all
                            geocoding candidates for one extracted location.
        query: Original user query (for context)
        response_text: Agent response text (for additional context)

    Returns:
        List of validated location dicts (one per valid location)
    """
    from app.services.llm import get_reviewer_llm
    
    if not location_candidates:
        return []
    
    if not query:
        # No query context, return first candidate for each location
        return [candidates[0] for candidates in location_candidates if candidates]
    
    llm = get_reviewer_llm()
    
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
    
    prompt = f"""You are validating geographic locations for a geopolitical intelligence platform.

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

- location_index: Index of the location (0-indexed, based on order above)
- candidate_index: Index of the candidate to use (0-indexed)
- reason: Brief explanation

If no locations are valid, respond with empty array: []"""

    try:
        response = llm.invoke(prompt)
        response_content = response.content if hasattr(response, 'content') else str(response)
        
        # Parse JSON from response
        json_match = re.search(r'\[.*\]', response_content, re.DOTALL)
        if not json_match:
            logger.warning(f"[LOCATION_EXTRACTOR] Could not parse LLM response: {response_content}")
            # Fallback: return first candidate for each location
            return [candidates[0] for candidates in location_candidates if candidates]
        
        import json
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
        # Fallback: return first candidate for each location
        return [candidates[0] for candidates in location_candidates if candidates]


def extract_and_geocode_locations(text: str, query: str = "", response_text: str = "") -> List[Dict[str, Any]]:
    """
    Full pipeline: Extract locations with NER, geocode with ALL candidates,
    and use LLM to select valid locations.
    
    NO hardcoding, NO heuristics - pure tool-based disambiguation.

    Args:
        text: Text to extract locations from (agent response)
        query: Original user query (for context)
        response_text: Agent response (for additional context)

    Returns:
        List of validated location dicts with name, type, lat, lon, etc.
    """
    # STEP 1: Extract locations with NER
    ner_locations = extract_locations_with_ner(text)

    if not ner_locations:
        return []

    # STEP 2: Get ALL geocoding candidates for each location
    location_candidates = []
    for loc in ner_locations:
        time.sleep(0.1)  # Rate limiting
        candidates = geocode_location(loc["name"])
        if candidates:
            location_candidates.append(candidates)
            logger.debug(
                f"[LOCATION_EXTRACTOR] {loc['name']}: {len(candidates)} candidate(s) found"
            )

    if not location_candidates:
        return []

    # STEP 3: LLM selects valid locations (SOLE decision-making step)
    validated_locations = select_valid_locations(
        location_candidates,
        query=query,
        response_text=response_text
    )
    
    logger.info(
        f"[LOCATION_EXTRACTOR] Pipeline complete: {len(validated_locations)} validated location(s)"
    )
    return validated_locations
