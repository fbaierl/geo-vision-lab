import logging
from typing import List, Dict, Any
from app.services.llm import get_reviewer_llm
import json
import re

logger = logging.getLogger("agent_flow")


def prioritize_locations(query: str, locations: List[Dict[str, Any]], response_text: str) -> List[Dict[str, Any]]:
    """
    Use LLM to filter and prioritize locations based on their relevance to the query.
    
    Args:
        query: The original user query
        locations: List of extracted locations with name, type, lat, lon
        response_text: The agent's response text (for context)
    
    Returns:
        Filtered list of locations with relevance scores, sorted by relevance
    """
    if not locations:
        return []
    
    # If only 1-2 locations, keep them all
    if len(locations) <= 2:
        for loc in locations:
            loc['relevance'] = 1.0
        return locations
    
    llm = get_reviewer_llm()
    
    # Build location list for the prompt
    location_list = "\n".join([
        f"- {loc['name']} ({loc['type']})"
        for loc in locations
    ])
    
    prompt = f"""You are a location relevance filter for a geopolitical intelligence platform.

USER QUERY: {query}

EXTRACTED LOCATIONS:
{location_list}

RESPONSE CONTEXT:
{response_text[:500]}  # Truncate to avoid token limits

TASK:
Filter and rank these locations by their relevance to the user's query.

CRITERIA:
1. PRIMARY (relevance: 1.0): The main subject of the query or response
2. SECONDARY (relevance: 0.7): Important related locations (major cities in a country, capitals, etc.)
3. TERTIARY (relevance: 0.4): Mentioned but not central to the query
4. EXCLUDE (relevance: 0.0): Incidental mentions, overly broad regions, or not relevant

RULES:
- For country queries: Include the country + 1-2 major cities max
- For region queries: Include the region + 1-2 major cities max  
- For city queries: Include only the city
- For multi-country queries: Include all primary countries, limit cities
- Prefer specificity: If query is about "Munich", don't include all of Germany

Respond ONLY with a JSON array in this format:
[
  {{"name": "Location Name", "relevance": 1.0}},
  {{"name": "Location Name", "relevance": 0.7}},
  ...
]

Only include locations with relevance >= 0.4. Limit to 5 locations max."""

    try:
        response = llm.invoke(prompt)
        response_text = response.content if hasattr(response, 'content') else str(response)
        
        # Parse JSON from response
        json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
        if not json_match:
            logger.warning("[LOCATION_PRIORITIZER] No JSON array found in response")
            # Fallback: return top 3 locations
            return _fallback_prioritize(locations)
        
        ranked = json.loads(json_match.group())
        
        # Create a mapping of name to relevance
        relevance_map = {item['name'].lower(): item['relevance'] for item in ranked}
        
        # Filter and score locations
        result = []
        for loc in locations:
            relevance = relevance_map.get(loc['name'].lower(), 0.4)
            if relevance >= 0.4:
                loc['relevance'] = relevance
                result.append(loc)
        
        # Sort by relevance (descending) and limit to 5
        result.sort(key=lambda x: x['relevance'], reverse=True)
        result = result[:5]
        
        logger.info(f"[LOCATION_PRIORITIZER] Filtered {len(locations)} locations to {len(result)}")
        return result
        
    except Exception as e:
        logger.error(f"[LOCATION_PRIORITIZER] Failed to prioritize: {e}")
        # Fallback: return top 3 locations
        return _fallback_prioritize(locations)


def _fallback_prioritize(locations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Fallback prioritization when LLM fails.
    Simple heuristic: countries/regions first, then cities, limit to 3.
    """
    # Priority order: country > region > city > landmark
    type_priority = {
        'country': 1,
        'region': 2,
        'city': 3,
        'landmark': 4
    }
    
    # Sort by type priority
    sorted_locs = sorted(locations, key=lambda x: type_priority.get(x['type'], 5))
    
    # Assign relevance scores
    for i, loc in enumerate(sorted_locs[:5]):
        if i == 0:
            loc['relevance'] = 1.0
        elif i < 3:
            loc['relevance'] = 0.7
        else:
            loc['relevance'] = 0.4
    
    return sorted_locs[:5]
