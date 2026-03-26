"""
Ontology Processing Sub-Graph

Replaces the location sub-graph to extract full graphs (Entities + Links).
"""

from typing import TypedDict, Dict, Any
from langgraph.graph import StateGraph
import logging

from app.models.ontology import SessionOntology, OntologyEntity, OntologyLink, Mention
from app.services.ontology_extractor import get_ontology_extractor
from app.services.location_extractor import get_location_extractor

logger = logging.getLogger("agent_flow")

class OntologySubGraphState(TypedDict):
    """State for the ontology processing sub-graph."""
    user_query: str
    assistant_response: str
    query_id: str
    
    # Output delta
    extracted_delta: SessionOntology


def extract_ontology_node(state: OntologySubGraphState) -> Dict[str, Any]:
    """Extracts the ontology from the assistant response."""
    logger.info("[ONTOLOGY_SUBGRAPH] Extracting entities and links")

    assistant_response = state.get("assistant_response", "")
    query = state.get("user_query", "")

    if not assistant_response:
        return {"extracted_delta": SessionOntology()}
        
    extractor = get_ontology_extractor()
    delta = extractor.extract(text=assistant_response, query=query)
    
    if not delta:
        return {"extracted_delta": SessionOntology()}
        
    session_delta = SessionOntology()
    loc_extractor = get_location_extractor()
    
    # Process Entities
    for ext_ent in delta.entities:
        ent_id = ext_ent.name.lower().strip()
        properties = {}
        
        # If it's a location, geocode it!
        if ext_ent.type == "Location":
            candidates = loc_extractor.geocode_location(ext_ent.name)
            if candidates:
                # Just take the best candidate for now to avoid blocking on LLM prioritization
                best = candidates[0]
                properties["lat"] = best["lat"]
                properties["lon"] = best["lon"]
                properties["country"] = best.get("country", "")
                properties["display_name"] = best.get("display_name", "")
                
        entity = OntologyEntity(
            id=ent_id,
            type=ext_ent.type,
            name=ext_ent.name,
            properties=properties,
            mentions=[Mention(source_text=ext_ent.context)]
        )
        session_delta.entities[ent_id] = entity
        
    # Process Links
    for ext_link in delta.links:
        src_id = ext_link.source_entity_name.lower().strip()
        tgt_id = ext_link.target_entity_name.lower().strip()
        # Create a deterministic ID for the link
        link_id = f"{src_id}_{ext_link.relationship_type.lower()}_{tgt_id}"
        
        link = OntologyLink(
            id=link_id,
            source_id=src_id,
            target_id=tgt_id,
            type=ext_link.relationship_type,
            mentions=[Mention(source_text=ext_link.context)]
        )
        session_delta.links[link_id] = link
        
    logger.info(f"[ONTOLOGY_SUBGRAPH] Found {len(session_delta.entities)} entities and {len(session_delta.links)} links")
    return {"extracted_delta": session_delta}


def create_ontology_subgraph() -> StateGraph:
    workflow = StateGraph(OntologySubGraphState)
    workflow.add_node("extract_ontology", extract_ontology_node)
    workflow.set_entry_point("extract_ontology")
    workflow.add_edge("extract_ontology", "__end__")
    return workflow.compile()

ontology_subgraph = create_ontology_subgraph()
