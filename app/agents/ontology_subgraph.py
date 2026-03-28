"""
Ontology Processing Sub-Graph

Extracts full graphs (Entities + Links) with UUID-based identity.
Implements two-pass extraction with gap resolution for missing entity references.
"""

from typing import TypedDict, Dict, Any, List, Literal
from langgraph.graph import StateGraph
import logging
import uuid

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
    
    # Gap tracking for two-pass extraction
    gap_entity_names: List[str]
    gap_entities_raw: List[Dict[str, Any]]
    pending_links: List[Dict[str, Any]]


def extract_ontology_node(state: OntologySubGraphState) -> Dict[str, Any]:
    """
    Pass 1: Extract entities and links from the assistant response.
    Identifies gap entities (referenced in links but not extracted).
    
    Uses UUID-based identity for entities and links.
    """
    try:
        logger.info("[ONTOLOGY_SUBGRAPH] Pass 1: Extracting entities and links")

        assistant_response = state.get("assistant_response", "")
        query = state.get("user_query", "")
        query_id = state.get("query_id", "unknown")

        if not assistant_response:
            logger.info("[ONTOLOGY_SUBGRAPH] No assistant response to process")
            return {
                "extracted_delta": SessionOntology(),
                "gap_entity_names": [],
                "gap_entities_raw": [],
                "pending_links": []
            }

        extractor = get_ontology_extractor()
        delta = extractor.extract(text=assistant_response, query=query)

        if not delta:
            logger.warning("[ONTOLOGY_SUBGRAPH] Extractor returned None - no delta extracted")
            return {
                "extracted_delta": SessionOntology(),
                "gap_entity_names": [],
                "gap_entities_raw": [],
                "pending_links": []
            }

        logger.info(f"[ONTOLOGY_SUBGRAPH] Extractor returned {len(delta.entities)} entities and {len(delta.links)} links")

        session_delta = SessionOntology()
        loc_extractor = get_location_extractor()

        # Track name -> UUID for link resolution within this batch
        name_to_uuid = {}
        entities_created = 0

        # Process Entities
        for ext_ent in delta.entities:
            try:
                logger.info(f"[ONTOLOGY_SUBGRAPH] Processing entity: '{ext_ent.name}' (type: {ext_ent.type})")

                # Generate UUID for this entity
                entity_uuid = uuid.uuid4()

                properties = {}

                # If it's a location, geocode it!
                if ext_ent.type == "Location":
                    try:
                        candidates = loc_extractor.geocode_location(ext_ent.name)
                        if candidates:
                            best = candidates[0]
                            properties["lat"] = best["lat"]
                            properties["lon"] = best["lon"]
                            properties["country"] = best.get("country", "")
                            properties["display_name"] = best.get("display_name", "")
                            logger.info(f"[ONTOLOGY_SUBGRAPH] ✓ Geocoded '{ext_ent.name}' → lat:{best['lat']}, lon:{best['lon']}, country:{best.get('country', 'N/A')}")
                        else:
                            logger.warning(f"[ONTOLOGY_SUBGRAPH] Geocoding returned no results for '{ext_ent.name}'")
                    except Exception as geo_error:
                        logger.error(f"[ONTOLOGY_SUBGRAPH] Geocoding failed for '{ext_ent.name}': {geo_error}")

                entity = OntologyEntity(
                    uuid=entity_uuid,
                    name=ext_ent.name,
                    type=ext_ent.type,
                    properties=properties,
                    mentions=[Mention(source_text=ext_ent.context, thread_id=query_id)],
                    created_by="llm_extractor"
                )

                # Store keyed by UUID string
                session_delta.entities[str(entity_uuid)] = entity
                entities_created += 1
                logger.info(f"[ONTOLOGY_SUBGRAPH] ✓ Created entity: UUID={entity_uuid}, name='{ext_ent.name}', type={ext_ent.type}")

                # Map name to UUID for link resolution
                name_to_uuid[ext_ent.name.lower()] = entity_uuid

            except Exception as entity_error:
                logger.error(f"[ONTOLOGY_SUBGRAPH] Failed to process entity '{ext_ent.name}': {entity_error}")
                logger.exception("[ONTOLOGY_SUBGRAPH] Entity processing stack trace:")

        # Identify gaps and collect pending links
        gap_names = set()
        pending_links = []
        
        for ext_link in delta.links:
            src_name = ext_link.source_entity_name.lower()
            tgt_name = ext_link.target_entity_name.lower()

            # Check if both entities exist
            source_uuid = name_to_uuid.get(src_name)
            target_uuid = name_to_uuid.get(tgt_name)

            # Track missing entities
            if not source_uuid:
                gap_names.add(ext_link.source_entity_name)
            if not target_uuid:
                gap_names.add(ext_link.target_entity_name)

            # Store link for later processing (after gap resolution)
            pending_links.append({
                "source_entity_name": ext_link.source_entity_name,
                "target_entity_name": ext_link.target_entity_name,
                "relationship_type": ext_link.relationship_type,
                "context": ext_link.context
            })

        logger.info("[ONTOLOGY_SUBGRAPH] === PASS 1 SUMMARY ===")
        logger.info(f"[ONTOLOGY_SUBGRAPH] ✓ Entities created: {entities_created}")
        logger.info(f"[ONTOLOGY_SUBGRAPH] → Links pending resolution: {len(pending_links)}")
        logger.info(f"[ONTOLOGY_SUBGRAPH] ? Gap entities detected: {len(gap_names)}")
        if gap_names:
            logger.info(f"[ONTOLOGY_SUBGRAPH] Gap entity names: {list(gap_names)}")
        logger.info("[ONTOLOGY_SUBGRAPH] ========================")

        return {
            "extracted_delta": session_delta,
            "gap_entity_names": list(gap_names),
            "gap_entities_raw": [],
            "pending_links": pending_links
        }

    except Exception as e:
        logger.error(f"[ONTOLOGY_SUBGRAPH] Critical error during ontology extraction: {e}")
        logger.exception("[ONTOLOGY_SUBGRAPH] Full stack trace:")
        return {
            "extracted_delta": SessionOntology(),
            "gap_entity_names": [],
            "gap_entities_raw": [],
            "pending_links": []
        }


def detect_gaps_node(state: OntologySubGraphState) -> Dict[str, Any]:
    """
    Node that passes through state for gap detection.
    The actual routing decision is made by route_after_gap_detection.
    """
    gap_names = state.get("gap_entity_names", [])
    
    if gap_names:
        logger.info(f"[ONTOLOGY_SUBGRAPH] Gap detection: {len(gap_names)} missing entities found")
    else:
        logger.info("[ONTOLOGY_SUBGRAPH] Gap detection: No missing entities")
    
    # Just pass through the state - routing happens in route_after_gap_detection
    return {}


def route_after_gap_detection(state: OntologySubGraphState) -> Literal["extract_gap_entities", "merge_and_finalize"]:
    """
    Conditional router: Check if gap entities need to be extracted.
    
    Returns:
        "extract_gap_entities" if gaps detected
        "merge_and_finalize" if no gaps (proceed directly to finalization)
    """
    gap_names = state.get("gap_entity_names", [])
    
    if gap_names:
        logger.info("[ONTOLOGY_SUBGRAPH] Routing to gap extraction")
        return "extract_gap_entities"
    else:
        logger.info("[ONTOLOGY_SUBGRAPH] Routing to finalization")
        return "merge_and_finalize"


def extract_gap_entities_node(state: OntologySubGraphState) -> Dict[str, Any]:
    """
    Pass 2: Extract only the missing gap entities.
    
    Uses targeted LLM prompt to recover entities that were referenced in links
    but not extracted in pass 1.
    """
    try:
        gap_names = state.get("gap_entity_names", [])
        assistant_response = state.get("assistant_response", "")
        query = state.get("user_query", "")
        
        if not gap_names:
            logger.warning("[ONTOLOGY_SUBGRAPH] Gap extraction called with no gap names")
            return {"gap_entities_raw": []}
        
        logger.info(f"[ONTOLOGY_SUBGRAPH] Pass 2: Extracting {len(gap_names)} gap entities: {gap_names}")
        
        extractor = get_ontology_extractor()
        gap_entities = extractor.extract_missing_entities(
            text=assistant_response,
            missing_names=gap_names,
            query=query
        )
        
        # Convert to raw dict format for merging
        gap_entities_raw = [
            {
                "name": e.name,
                "type": e.type,
                "context": e.context
            }
            for e in gap_entities
        ]
        
        logger.info(f"[ONTOLOGY_SUBGRAPH] Gap extraction complete: {len(gap_entities_raw)} entities recovered")
        
        # Track which gaps were resolved
        resolved_names = [e["name"] for e in gap_entities_raw]
        unresolved = set(gap_names) - set(resolved_names)
        if unresolved:
            logger.warning(f"[ONTOLOGY_SUBGRAPH] Unresolved gap entities (not found in text): {unresolved}")
        
        return {"gap_entities_raw": gap_entities_raw}
        
    except Exception as e:
        logger.error(f"[ONTOLOGY_SUBGRAPH] Error during gap entity extraction: {e}")
        logger.exception("[ONTOLOGY_SUBGRAPH] Gap extraction stack trace:")
        return {"gap_entities_raw": []}


def merge_and_finalize_node(state: OntologySubGraphState) -> Dict[str, Any]:
    """
    Finalization: Merge gap entities and process all pending links.
    
    - Adds gap entities to the session delta with UUIDs
    - Processes pending links using the complete entity set
    - Returns the final extracted delta
    """
    try:
        logger.info("[ONTOLOGY_SUBGRAPH] Finalization: Merging entities and processing links")
        
        session_delta = state.get("extracted_delta", SessionOntology())
        gap_entities_raw = state.get("gap_entities_raw", [])
        pending_links = state.get("pending_links", [])
        query_id = state.get("query_id", "unknown")
        
        # Build name -> UUID map from existing entities
        name_to_uuid = {}
        for entity_uuid_str, entity in session_delta.entities.items():
            name_to_uuid[entity.name.lower()] = uuid.UUID(entity_uuid_str)
        
        # Process gap entities
        gap_entities_created = 0
        for gap_ent in gap_entities_raw:
            try:
                entity_name = gap_ent["name"]
                entity_name_lower = entity_name.lower()
                
                # Skip if already exists (shouldn't happen, but safety check)
                if entity_name_lower in name_to_uuid:
                    logger.warning(f"[ONTOLOGY_SUBGRAPH] Gap entity '{entity_name}' already exists, skipping")
                    continue
                
                logger.info(f"[ONTOLOGY_SUBGRAPH] Processing gap entity: '{entity_name}' (type: {gap_ent['type']})")
                
                # Generate UUID for this entity
                entity_uuid = uuid.uuid4()
                
                entity = OntologyEntity(
                    uuid=entity_uuid,
                    name=entity_name,
                    type=gap_ent["type"],
                    properties={},
                    mentions=[Mention(source_text=gap_ent.get("context", ""), thread_id=query_id)],
                    created_by="llm_extractor_gap_resolution"
                )
                
                session_delta.entities[str(entity_uuid)] = entity
                name_to_uuid[entity_name_lower] = entity_uuid
                gap_entities_created += 1
                logger.info(f"[ONTOLOGY_SUBGRAPH] ✓ Created gap entity: UUID={entity_uuid}, name='{entity_name}', type={gap_ent['type']}")
                
            except Exception as entity_error:
                logger.error(f"[ONTOLOGY_SUBGRAPH] Failed to process gap entity '{gap_ent.get('name', 'unknown')}': {entity_error}")
                logger.exception("[ONTOLOGY_SUBGRAPH] Gap entity processing stack trace:")
        
        # Process pending links
        links_created = 0
        links_skipped = 0
        
        for link_data in pending_links:
            try:
                src_name = link_data["source_entity_name"].lower()
                tgt_name = link_data["target_entity_name"].lower()
                
                source_uuid = name_to_uuid.get(src_name)
                target_uuid = name_to_uuid.get(tgt_name)
                
                if not source_uuid or not target_uuid:
                    links_skipped += 1
                    logger.warning(
                        f"[ONTOLOGY_SUBGRAPH] ✗ Link still references missing entities: "
                        f"'{link_data['source_entity_name']}' (found: {bool(source_uuid)}) -> "
                        f"'{link_data['target_entity_name']}' (found: {bool(target_uuid)})"
                        f" - likely hallucinated relationship"
                    )
                    continue
                
                # Generate UUID for this link
                link_uuid = uuid.uuid4()
                
                link = OntologyLink(
                    uuid=link_uuid,
                    source_uuid=source_uuid,
                    target_uuid=target_uuid,
                    type=link_data["relationship_type"],
                    mentions=[Mention(source_text=link_data.get("context", ""), thread_id=query_id)],
                    created_by="llm_extractor"
                )
                
                session_delta.links[str(link_uuid)] = link
                links_created += 1
                logger.info(
                    f"[ONTOLOGY_SUBGRAPH] ✓ Created link: UUID={link_uuid}, "
                    f"'{link_data['source_entity_name']}' -[{link_data['relationship_type']}]-> '{link_data['target_entity_name']}'"
                )
                
            except Exception as link_error:
                logger.error(f"[ONTOLOGY_SUBGRAPH] Failed to process link '{link_data['source_entity_name']}' -> '{link_data['target_entity_name']}': {link_error}")
                logger.exception("[ONTOLOGY_SUBGRAPH] Link processing stack trace:")
        
        logger.info("[ONTOLOGY_SUBGRAPH] === FINALIZATION SUMMARY ===")
        logger.info(f"[ONTOLOGY_SUBGRAPH] ✓ Total entities: {len(session_delta.entities)}")
        logger.info(f"[ONTOLOGY_SUBGRAPH] ✓ Gap entities merged: {gap_entities_created}")
        logger.info(f"[ONTOLOGY_SUBGRAPH] ✓ Links created: {links_created}")
        logger.info(f"[ONTOLOGY_SUBGRAPH] ✗ Links skipped (unresolvable): {links_skipped}")
        logger.info("[ONTOLOGY_SUBGRAPH] ================================")
        
        return {"extracted_delta": session_delta}
        
    except Exception as e:
        logger.error(f"[ONTOLOGY_SUBGRAPH] Critical error during finalization: {e}")
        logger.exception("[ONTOLOGY_SUBGRAPH] Finalization stack trace:")
        return {"extracted_delta": SessionOntology()}


def create_ontology_subgraph() -> StateGraph:
    """Create and configure the ontology processing subgraph with gap resolution."""
    workflow = StateGraph(OntologySubGraphState)
    
    # Add nodes
    workflow.add_node("extract_ontology", extract_ontology_node)
    workflow.add_node("detect_gaps", detect_gaps_node)
    workflow.add_node("extract_gap_entities", extract_gap_entities_node)
    workflow.add_node("merge_and_finalize", merge_and_finalize_node)
    
    # Set entry point
    workflow.set_entry_point("extract_ontology")
    
    # Define edges
    workflow.add_edge("extract_ontology", "detect_gaps")
    
    # Conditional routing based on gap detection
    workflow.add_conditional_edges("detect_gaps", route_after_gap_detection)
    
    # Gap extraction flows to finalization
    workflow.add_edge("extract_gap_entities", "merge_and_finalize")
    
    # Finalization ends the subgraph
    workflow.add_edge("merge_and_finalize", "__end__")
    
    return workflow.compile()


ontology_subgraph = create_ontology_subgraph()
