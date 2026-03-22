"""
Location Processing Sub-Graph

This module implements a dedicated sub-graph for location processing,
replacing the linear 2-node pipeline (LOCATION_EXTRACTOR → LOCATION_PRIORITIZER).

The sub-graph architecture provides:
- Modularity: Location logic is self-contained
- Visibility: Each step emits events for UI streaming
- Extensibility: Easy to add query-aware extraction later
- Debuggability: Intermediate state is explicit

Current Implementation (Phase 1):
┌─────────────────────┐    ┌─────────────────────┐
│  EXTRACT_LOCATIONS  │ →  │  PRIORITIZE_LOCS    │
│  (NER + Geocode)    │    │  (LLM Filtering)    │
└─────────────────────┘    └─────────────────────┘

Future Enhancement (Phase 2 - Query-Aware):
┌─────────────────────┐    ┌─────────────────────┐    ┌─────────────────────┐    ┌─────────────────────┐
│  PARSE_QUERY_LOCS   │ →  │  EXTRACT_NER_LOCS   │ →  │  GEOCODE_WITH_CTX   │ →  │  FILTER_RELEVANCE   │
│  (LLM)              │    │  (NER + Filter)     │    │  (Smart Geocoder)   │    │  (LLM)              │
└─────────────────────┘    └─────────────────────┘    └─────────────────────┘    └─────────────────────┘
"""

from typing import TypedDict, Dict, Any, List
from langgraph.graph import StateGraph
import logging

from langchain_core.messages import HumanMessage

from app.core.di_llm import get_llm
from app.core.di_services import get_location_extractor, get_location_prioritizer
from app.services.location_extractor import LocationExtractorService
from app.services.location_prioritizer import LocationPrioritizerService

logger = logging.getLogger("agent_flow")


# =============================================================================
# Sub-Graph State
# =============================================================================

class LocationSubGraphState(TypedDict):
    """State for the location processing sub-graph."""
    # Input from main graph
    user_query: str
    assistant_response: str
    
    # Intermediate state
    query_target_locations: List[Dict[str, str]]  # Future: extracted from query
    ner_extracted_locations: List[Dict[str, Any]]  # From NER + geocoding
    
    # Output to main graph
    final_locations: List[Dict[str, Any]]


# =============================================================================
# Node: Parse Query Locations (Future Enhancement)
# =============================================================================

def parse_query_locations_node(state: LocationSubGraphState) -> Dict[str, Any]:
    """
    Extract target locations from the user query using LLM.
    
    Future enhancement: This will enable query-aware location filtering.
    For now, returns empty list (passthrough).
    
    Example:
        Query: "What happened in Iran the last 2 weeks?"
        → Target locations: ["Iran"]
        
        Query: "Iran vs Israel conflict"
        → Target locations: ["Iran", "Israel"]
    """
    logger.info("[LOCATION_SUBGRAPH] Parse query locations (placeholder)")
    
    # TODO: Implement LLM-based query location extraction
    # For now, return empty - the NER extractor will find all locations
    
    return {"query_target_locations": []}


# =============================================================================
# Node: Extract NER Locations
# =============================================================================

def extract_ner_locations_node(state: LocationSubGraphState) -> Dict[str, Any]:
    """
    Extract locations from assistant response using NER + geocoding.
    
    Uses the LocationExtractorService to:
    1. Run NER on the response text
    2. Geocode all extracted locations (multi-candidate)
    
    Future enhancement: Filter NER results by query_target_locations.
    """
    logger.info("[LOCATION_SUBGRAPH] Extract NER locations")
    
    assistant_response = state.get("assistant_response", "")
    
    if not assistant_response:
        logger.info("[LOCATION_SUBGRAPH] No response content to extract from")
        return {"ner_extracted_locations": []}
    
    try:
        extractor: LocationExtractorService = get_location_extractor()
        locations = extractor.extract_and_geocode_locations(
            text=assistant_response,
            query=state.get("user_query", ""),
            response_text=assistant_response
        )
        
        # Check for geocoding errors
        if hasattr(extractor, 'geocoding_errors') and extractor.geocoding_errors:
            for error in extractor.geocoding_errors:
                logger.warning(f"[LOCATION_SUBGRAPH] Geocoding error: {error['message']}")
        
        logger.info(f"[LOCATION_SUBGRAPH] Extracted {len(locations)} geocoded location(s)")
        return {"ner_extracted_locations": locations}
        
    except Exception as e:
        logger.error(f"[LOCATION_SUBGRAPH] Extraction failed: {e}")
        return {"ner_extracted_locations": []}


# =============================================================================
# Node: Geocode with Context (Future Enhancement)
# =============================================================================

def geocode_with_context_node(state: LocationSubGraphState) -> Dict[str, Any]:
    """
    Geocode locations with country context from query.
    
    Future enhancement: Use query_target_locations to bias geocoding.
    For now, returns the NER-extracted locations unchanged.
    """
    logger.info("[LOCATION_SUBGRAPH] Geocode with context (passthrough)")
    
    # TODO: Implement smart geocoding with country context
    # For now, just pass through the NER results
    return {}  # No change to state


# =============================================================================
# Node: Filter Relevant Locations
# =============================================================================

def filter_relevant_locations_node(state: LocationSubGraphState) -> Dict[str, Any]:
    """
    Filter and prioritize locations based on relevance to query.
    
    Uses the LocationPrioritizerService to:
    1. Send all geocoded candidates to LLM
    2. LLM selects best candidates and assigns relevance scores
    3. Returns filtered list sorted by relevance
    """
    logger.info("[LOCATION_SUBGRAPH] Filter relevant locations")
    
    locations = state.get("ner_extracted_locations", [])
    
    if not locations:
        logger.info("[LOCATION_SUBGRAPH] No locations to prioritize")
        return {"final_locations": []}
    
    try:
        prioritizer: LocationPrioritizerService = get_location_prioritizer()
        prioritized = prioritizer.prioritize_locations(
            query=state.get("user_query", ""),
            locations=locations,
            response_text=state.get("assistant_response", "")
        )
        
        logger.info(f"[LOCATION_SUBGRAPH] Prioritized to {len(prioritized)} location(s)")
        return {"final_locations": prioritized}
        
    except Exception as e:
        logger.error(f"[LOCATION_SUBGRAPH] Prioritization failed: {e}")
        # Return original locations on failure
        return {"final_locations": locations}


# =============================================================================
# Conditional Edge: Check if NER extraction found locations
# =============================================================================

def should_prioritize(state: LocationSubGraphState) -> str:
    """Decide whether to run prioritization or skip to end."""
    locations = state.get("ner_extracted_locations", [])
    if locations:
        return "prioritize"
    else:
        return "skip_prioritize"


# =============================================================================
# Build Sub-Graph
# =============================================================================

def create_location_subgraph() -> StateGraph:
    """
    Create and compile the location processing sub-graph.
    
    Returns:
        Compiled StateGraph ready to be added to main graph
    """
    workflow = StateGraph(LocationSubGraphState)
    
    # Add nodes
    workflow.add_node("parse_query_locations", parse_query_locations_node)
    workflow.add_node("extract_ner_locations", extract_ner_locations_node)
    workflow.add_node("geocode_with_context", geocode_with_context_node)
    workflow.add_node("filter_relevant_locations", filter_relevant_locations_node)
    
    # Set entry point
    workflow.set_entry_point("parse_query_locations")
    
    # Define edges
    workflow.add_edge("parse_query_locations", "extract_ner_locations")
    workflow.add_conditional_edges(
        "extract_ner_locations",
        should_prioritize,
        {
            "prioritize": "geocode_with_context",
            "skip_prioritize": "__end__"
        }
    )
    workflow.add_edge("geocode_with_context", "filter_relevant_locations")
    workflow.add_edge("filter_relevant_locations", "__end__")
    
    return workflow.compile()


# =============================================================================
# Compiled Sub-Graph (for import)
# =============================================================================

location_subgraph = create_location_subgraph()
