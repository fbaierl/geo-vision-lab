"""
Geographic NER for Response Post-Processing

Extracts locations AND connections from agent responses using the existing
Qwen LLM — no additional model downloads required.

Returns geocoded data + relationship arrows for Palantir-style map rendering.
"""

import logging
import json
import re
from typing import List, Dict, Any, Optional, Tuple
from geopy.geocoders import Nominatim

logger = logging.getLogger(__name__)

# Cache for geocoded locations
_geocache: Dict[str, Optional[Tuple[float, float]]] = {}
_geolocator = None


def _get_geolocator() -> Optional[Nominatim]:
    """Get or create geolocator instance."""
    global _geolocator
    if _geolocator is None:
        try:
            _geolocator = Nominatim(user_agent="geovision_response_ner", timeout=5)
        except Exception as e:
            logger.warning(f"[GEO_NER] Geolocator init failed: {e}")
            _geolocator = None
    return _geolocator


def _geocode_cached(location_name: str) -> Optional[Tuple[float, float]]:
    """Geocode with caching to avoid repeated API calls."""
    if location_name in _geocache:
        return _geocache[location_name]

    geolocator = _get_geolocator()
    if geolocator is None:
        return None

    try:
        location = geolocator.geocode(location_name, timeout=5)
        if location:
            coords = (location.latitude, location.longitude)
            _geocache[location_name] = coords
            logger.debug(f"[GEO_NER] Geocoded '{location_name}' -> {coords}")
            return coords
    except Exception as e:
        logger.debug(f"[GEO_NER] Geocode failed for '{location_name}': {e}")

    _geocache[location_name] = None
    return None


# ---------------------------------------------------------------------------
# LLM-based extraction (primary method)
# ---------------------------------------------------------------------------

GEO_EXTRACTION_PROMPT = """You are a geographic intelligence analyst. Extract ALL geographic entities and relationships from this text.

TEXT:
{text}

USER QUERY CONTEXT:
{query}

Return ONLY valid JSON in this exact format (no markdown, no backticks, no explanation):
{{
  "locations": [
    {{
      "name": "Location Name",
      "type": "country|city|region|military_base|strait|island",
      "role": "aggressor|target|ally|neutral|staging"
    }}
  ],
  "connections": [
    {{
      "from": "Source Location Name",
      "to": "Target Location Name",
      "type": "attack|threat|support|movement|blockade",
      "intensity": "high|medium|low",
      "description": "Brief description of the action"
    }}
  ]
}}

Rules:
- Include REAL geographic locations only (countries, cities, regions, islands, straits, bases)
- Connections should reflect the directionality described in the text
- For military scenarios: use "attack" for offensive moves, "support" for allied support, "movement" for troop movements
- Be specific about coastal landing sites or specific strategic locations when mentioned
- Return empty lists if no locations found
"""


def _extract_with_llm(text: str, user_query: str = "") -> Dict[str, Any]:
    """Extract locations and connections using the Qwen LLM (sync)."""
    from app.services.llm import get_reasoning_llm

    try:
        llm = get_reasoning_llm()
        prompt = GEO_EXTRACTION_PROMPT.format(
            text=text[:3000],
            query=user_query[:200] if user_query else "General geopolitical query"
        )
        response = llm.invoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

        json_match = re.search(r"\{.*\}", content, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            logger.debug(
                f"[GEO_NER] LLM extracted {len(result.get('locations', []))} locations, "
                f"{len(result.get('connections', []))} connections"
            )
            return result
        else:
            logger.warning(f"[GEO_NER] No JSON found in LLM response: {content[:200]}")
            return {"locations": [], "connections": []}

    except json.JSONDecodeError as e:
        logger.error(f"[GEO_NER] JSON parse error: {e}")
        return {"locations": [], "connections": []}
    except Exception as e:
        logger.error(f"[GEO_NER] LLM extraction failed: {e}", exc_info=True)
        return {"locations": [], "connections": []}


async def _extract_with_llm_async(text: str, user_query: str = "") -> Dict[str, Any]:
    """Async version using ainvoke with a small, FAST model (Qwen 0.8B)."""
    from app.services.llm import get_qa_llm

    try:
        llm = get_qa_llm()
        prompt = GEO_EXTRACTION_PROMPT.format(
            text=text[:3000],
            query=user_query[:200] if user_query else "General geopolitical query"
        )
        # 30s timeout is enough for 0.8B
        response = await llm.ainvoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

        json_match = re.search(r"\{.*\}", content, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            logger.info(
                f"[GEO_NER] Fast LLM extracted {len(result.get('locations', []))} locations, "
                f"{len(result.get('connections', []))} connections"
            )
            return result
        else:
            logger.warning(f"[GEO_NER] No JSON found in fast LLM response")
            return {"locations": [], "connections": []}

    except Exception as e:
        logger.error(f"[GEO_NER] Fast LLM extraction failed: {e}")
        return {"locations": [], "connections": []}


# ---------------------------------------------------------------------------
# Fallback: hardcoded keyword scan
# ---------------------------------------------------------------------------

_KNOWN_COUNTRIES = [
    "China", "Taiwan", "Japan", "Okinawa", "USA", "America", "Philippines",
    "Vietnam", "South Korea", "North Korea", "Russia", "Ukraine", "Belarus",
    "Poland", "Germany", "France", "UK", "Israel", "Iran", "Gaza", "Syria",
    "Iraq", "Turkey", "India", "Pakistan", "Afghanistan", "Saudi Arabia",
]

_CONFLICT_KEYWORDS = {
    "attack": ["attack", "invade", "strike", "assault", "bomb", "missile"],
    "threat": ["threaten", "intimidate", "coerce", "pressure"],
    "support": ["support", "ally", "defend", "reinforce", "supply"],
    "movement": ["deploy", "move", "advance", "retreat", "maneuver"],
}


def _extract_fallback(text: str) -> Dict[str, Any]:
    """Fallback extraction using keyword scanning."""
    locations = []
    seen = set()

    for country in _KNOWN_COUNTRIES:
        if country in text and country not in seen:
            seen.add(country)
            locations.append({"name": country, "type": "country", "role": "neutral"})

    # Simple connection detection: find the "attack"/"support" keywords and
    # try to build connections between the first two locations found
    connections = []
    if len(locations) >= 2:
        text_lower = text.lower()
        conn_type = "threat"
        for ct, keywords in _CONFLICT_KEYWORDS.items():
            if any(kw in text_lower for kw in keywords):
                conn_type = ct
                break

        intensity = "high" if conn_type == "attack" else "medium"
        connections.append({
            "from": locations[0]["name"],
            "to": locations[1]["name"],
            "type": conn_type,
            "intensity": intensity,
            "description": f"{conn_type.title()} detected in text",
        })

    return {"locations": locations, "connections": connections}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_with_coordinates(
    text: str,
    user_query: str = "",
) -> Dict[str, Any]:
    """Sync version (for compatibility). See extract_with_coordinates_async for the preferred path."""
    if not text or len(text.strip()) < 10:
        return {"locations": [], "connections": [], "stats": {"total": 0, "geocoded": 0}}

    clean_text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    logger.info("[GEO_NER] Starting LLM-based geo extraction (sync)")
    raw = _extract_with_llm(clean_text, user_query)

    if not raw.get("locations"):
        logger.info("[GEO_NER] LLM returned no locations, using fallback")
        raw = _extract_fallback(clean_text)

    return _build_result(raw)


async def extract_with_coordinates_async(
    text: str,
    user_query: str = "",
) -> Dict[str, Any]:
    """
    Async version — preferred. Uses ainvoke so the event loop is not blocked.

    Args:
        text: The agent's final response text
        user_query: The original user question (for better context)
    """
    if not text or len(text.strip()) < 10:
        return {"locations": [], "connections": [], "stats": {"total": 0, "geocoded": 0}}

    clean_text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    logger.info("[GEO_NER] Starting LLM-based geo extraction (async)")
    raw = await _extract_with_llm_async(clean_text, user_query)

    if not raw.get("locations"):
        logger.info("[GEO_NER] LLM returned no locations, using fallback")
        raw = _extract_fallback(clean_text)

    return await _build_result_async(raw)


async def _build_result_async(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Async version: parallelize geocoding to avoid blocking loop."""
    import asyncio
    raw_locations = raw.get("locations", [])
    raw_connections = raw.get("connections", [])

    # Parallel geocoding
    unique_names = list(set(
        [l.get("name", "").strip() for l in raw_locations] +
        [c.get("from", "").strip() for c in raw_connections] +
        [c.get("to", "").strip() for c in raw_connections]
    ))
    unique_names = [n for n in unique_names if n]

    async def geocode_task(name):
        return name, await asyncio.to_thread(_geocode_cached, name)

    geocode_results = await asyncio.gather(*[geocode_task(n) for n in unique_names])
    coord_map = {name: coords for name, coords in geocode_results if coords}

    # --- Build final objects ---
    location_map: Dict[str, Dict] = {}
    for loc in raw_locations:
        name = loc.get("name", "").strip()
        if not name or name in location_map:
            continue
        coords = coord_map.get(name)
        location_map[name] = {
            "name": name,
            "type": loc.get("type", "location"),
            "role": loc.get("role", "neutral"),
            "coordinates": list(coords) if coords else None,
            "confidence": "high" if coords else "low",
        }

    geocoded_connections = []
    for conn in raw_connections:
        from_name = conn.get("from", "").strip()
        to_name = conn.get("to", "").strip()
        from_coords = coord_map.get(from_name)
        to_coords = coord_map.get(to_name)

        if from_coords and to_coords:
            geocoded_connections.append({
                "from_name": from_name,
                "to_name": to_name,
                "from_coords": list(from_coords),
                "to_coords": list(to_coords),
                "type": conn.get("type", "threat"),
                "intensity": conn.get("intensity", "medium"),
                "description": conn.get("description", ""),
            })

    final_locations = [
        loc for loc in location_map.values() if loc.get("coordinates")
    ]

    logger.info(
        f"[GEO_NER] Done: {len(final_locations)} locations, "
        f"{len(geocoded_connections)} connections"
    )

    return {
        "locations": final_locations,
        "connections": geocoded_connections,
        "stats": {
            "total": len(raw_locations),
            "geocoded": len(final_locations),
            "connections": len(geocoded_connections),
        },
    }


def _build_result(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Sync bridge (fallback check)."""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # This shouldn't really happen in this app structure anymore
            return {"locations": [], "connections": [], "stats": {}}
        return loop.run_until_complete(_build_result_async(raw))
    except Exception:
        # Extremely raw fallback if loop issues
        return {"locations": [], "connections": [], "stats": {}}

