"""
Location Prioritizer Service

Filters and ranks extracted locations based on their relevance to the user query.
This service receives ALL geocoding candidates from the extractor and makes the
single decision about which locations to keep and which candidate to use for each.

All dependencies are injected via the DI container - no global state.
"""

import logging
from typing import List, Dict, Any
from langchain_ollama import ChatOllama
import json
import re

from app.core.di_llm import get_llm

logger = logging.getLogger("agent_flow")


class LocationPrioritizerService:
    """
    Location prioritizer service with explicit dependencies.

    Usage:
        service = LocationPrioritizerService(llm=get_llm())
    """

    def __init__(self, llm: ChatOllama):
        self.llm = llm

    def prioritize_locations(
        self,
        query: str,
        locations: List[Dict[str, Any]],
        response_text: str
    ) -> List[Dict[str, Any]]:
        """
        Use LLM to filter and prioritize locations based on their relevance to the query.
        
        Receives ALL geocoding candidates (flat list) and selects the best candidate
        for each unique location name, then filters by relevance.

        Args:
            query: The original user query
            locations: List of ALL geocoded candidates with name, type, lat, lon, 
                       display_name, country (may contain multiple candidates for same location)
            response_text: The agent's response text (for context)

        Returns:
            Filtered list of selected locations with relevance scores, sorted by relevance
        """
        if not locations:
            return []

        # Group candidates by location name
        candidates_by_name = {}
        for loc in locations:
            name = loc['name'].lower()
            if name not in candidates_by_name:
                candidates_by_name[name] = []
            candidates_by_name[name].append(loc)

        # Build location list for the prompt - group candidates by name
        location_groups = []
        for idx, (name, candidates) in enumerate(candidates_by_name.items()):
            group_text = f"{idx + 1}. {name} ({len(candidates)} candidate(s)):\n"
            for cand_idx, c in enumerate(candidates):
                group_text += (
                    f"   {cand_idx + 1}) {c['display_name']} "
                    f"(Type: {c['type']}, Country: {c['country']}, "
                    f"Lat: {c['lat']:.4f}, Lon: {c['lon']:.4f})\n"
                )
            location_groups.append(group_text)

        location_list = "\n\n".join(location_groups)

        prompt = f"""You are a location relevance filter for a geopolitical intelligence platform.

USER QUERY: {query}

EXTRACTED LOCATIONS (all geocoding candidates shown):
{location_list}

RESPONSE CONTEXT:
{response_text[:500]}

TASK:
1. For EACH location group, select the BEST candidate (or mark as excluded)
2. Assign relevance scores to ALL locations (including 0.0 for excluded ones)

CRITERIA:
1. PRIMARY (relevance: 1.0): The main subject of the query or response
2. SECONDARY (relevance: 0.7): Important related locations (major cities in a country, capitals, etc.)
3. TERTIARY (relevance: 0.4): Mentioned but not central to the query
4. EXCLUDE (relevance: 0.0): Incidental mentions, overly broad regions, wrong country, or not relevant

RULES:
- For country queries: Include the country + 1-2 major cities max
- For region queries: Include the region + 1-2 major cities max
- For city queries: Include only the city
- For multi-country queries: Include all primary countries, limit cities
- Prefer specificity: If query is about "Munich", don't include all of Germany
- Disambiguate using display_name and country (e.g., "Iran, country" vs "Iran, Texas")
- Exclude abbreviations or ambiguous matches (e.g., "IRA" when query is about Iran)
- ALWAYS provide a relevance score and reason for EVERY location group

Respond ONLY with a JSON array in this format:
[
  {{"location_index": 0, "candidate_index": 0, "relevance": 1.0, "reason": "Iran country is main subject"}},
  {{"location_index": 1, "candidate_index": -1, "relevance": 0.0, "reason": "Excluded: wrong country (USA, not Iran)"}},
  {{"location_index": 2, "candidate_index": 2, "relevance": 0.7, "reason": "Tehran is capital of Iran"}}
]

- location_index: Index of the location group (0-indexed, matches the numbered list above)
- candidate_index: Index of the selected candidate (-1 if excluded/no suitable candidate)
- relevance: Score from 0.0 to 1.0 (use 0.0 for excluded locations)
- reason: Brief explanation (REQUIRED for debugging - explain WHY selected or excluded)

IMPORTANT: Return ALL location groups with relevance and reason. Use candidate_index: -1 and relevance: 0.0 for excluded locations."""

        try:
            # Disable reasoning mode for this structured JSON task.
            # The shared LLM still uses reasoning for the main agent graph.
            response = self.llm.invoke(prompt, reasoning=False)
            response_content = response.content if hasattr(response, 'content') else str(response)

            # Parse JSON from response
            json_match = re.search(r'\[.*\]', response_content, re.DOTALL)
            if not json_match:
                logger.warning("[LOCATION_PRIORITIZER] No JSON array found in response")
                return self._fallback_prioritize(candidates_by_name)

            selections = json.loads(json_match.group())

            # Build result from selections - process ALL locations including excluded ones
            result = []
            location_names = list(candidates_by_name.keys())

            for selection in selections:
                loc_idx = selection.get('location_index')
                cand_idx = selection.get('candidate_index')
                relevance = selection.get('relevance', 0.0)
                reason = selection.get('reason', 'No reason provided')

                if loc_idx is not None and 0 <= loc_idx < len(location_names):
                    name = location_names[loc_idx]
                    candidates = candidates_by_name.get(name, [])

                    # Handle excluded locations (candidate_index: -1)
                    if cand_idx == -1:
                        # Create an exclusion entry for debugging
                        excluded_entry = {
                            'name': name,
                            'relevance': 0.0,
                            'selection_reason': reason,
                            'excluded': True,
                            'display_name': f'[EXCLUDED] {name}',
                            'lat': None,
                            'lon': None,
                            'type': 'unknown',
                            'country': 'N/A'
                        }
                        result.append(excluded_entry)
                        logger.info(
                            f"[LOCATION_PRIORITIZER] Excluded: {name} - {reason}"
                        )
                    elif cand_idx is not None and 0 <= cand_idx < len(candidates):
                        selected = candidates[cand_idx].copy()
                        selected['relevance'] = relevance
                        selected['selection_reason'] = reason
                        if relevance > 0:
                            result.append(selected)
                            logger.info(
                                f"[LOCATION_PRIORITIZER] Selected: {selected['name']} → "
                                f"{selected['display_name']} (relevance: {relevance}, reason: {reason})"
                            )
                        else:
                            # Even selected candidates can have 0 relevance if not useful
                            selected['excluded'] = True
                            result.append(selected)
                            logger.info(
                                f"[LOCATION_PRIORITIZER] Selected but excluded: {selected['name']} → "
                                f"{selected['display_name']} (relevance: {relevance}, reason: {reason})"
                            )

            # Sort by relevance (descending) and limit to 5
            result.sort(key=lambda x: x['relevance'], reverse=True)
            result = result[:5]

            logger.info(f"[LOCATION_PRIORITIZER] Filtered to {len(result)} location(s)")
            return result

        except Exception as e:
            logger.error(f"[LOCATION_PRIORITIZER] Failed to prioritize: {e}")
            return self._fallback_prioritize(candidates_by_name)

    def _select_best_candidate(self, candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Select the best candidate from a list (highest specificity)."""
        # Priority: country > region > city > town > village > landmark
        type_priority = {
            'country': 1,
            'region': 2,
            'city': 3,
            'town': 4,
            'village': 5,
            'neighbourhood': 6,
            'landmark': 7
        }
        return min(candidates, key=lambda x: type_priority.get(x['type'], 99))

    def _fallback_prioritize(self, candidates_by_name: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """
        Fallback prioritization when LLM fails.
        Simple heuristic: select best candidate per location, countries/regions first, limit to 5.
        """
        # Select best candidate for each location name
        best_candidates = []
        for name, candidates in candidates_by_name.items():
            best = self._select_best_candidate(candidates)
            best_candidates.append(best)

        # Priority order: country > region > city > landmark
        type_priority = {
            'country': 1,
            'region': 2,
            'city': 3,
            'landmark': 4
        }

        # Sort by type priority
        sorted_locs = sorted(best_candidates, key=lambda x: type_priority.get(x['type'], 5))

        # Assign relevance scores
        result = []
        for i, loc in enumerate(sorted_locs[:5]):
            loc = loc.copy()
            if i == 0:
                loc['relevance'] = 1.0
            elif i < 3:
                loc['relevance'] = 0.7
            else:
                loc['relevance'] = 0.4
            result.append(loc)

        return result[:5]


# =============================================================================
# DI factory function
# =============================================================================

def get_location_prioritizer() -> LocationPrioritizerService:
    """
    Get location prioritizer service with dependencies from DI container.
    """
    return LocationPrioritizerService(llm=get_llm())
