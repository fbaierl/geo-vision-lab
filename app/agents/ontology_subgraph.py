"""
Ontology Processing Sub-Graph

Extracts full graphs (Entities + Links) with UUID-based identity.
"""

from typing import TypedDict, Dict, Any
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


def extract_ontology_node(state: OntologySubGraphState) -> Dict[str, Any]:
    """
    Extracts the ontology from the assistant response.

    Uses UUID-based identity for entities and links.
    """
    try:
        logger.info("[ONTOLOGY_SUBGRAPH] Extracting entities and links")

        assistant_response = state.get("assistant_response", "")
        query = state.get("user_query", "")
        query_id = state.get("query_id", "unknown")

        if not assistant_response:
            logger.info("[ONTOLOGY_SUBGRAPH] No assistant response to process")
            return {"extracted_delta": SessionOntology()}

        extractor = get_ontology_extractor()
        delta = extractor.extract(text=assistant_response, query=query)

        if not delta:
            logger.warning("[ONTOLOGY_SUBGRAPH] Extractor returned None - no delta extracted")
            return {"extracted_delta": SessionOntology()}

        logger.info(f"[ONTOLOGY_SUBGRAPH] Extractor returned {len(delta.entities)} entities and {len(delta.links)} links")

        session_delta = SessionOntology()
        loc_extractor = get_location_extractor()

        # Track name -> UUID for link resolution within this batch
        name_to_uuid = {}
        entities_created = 0
        links_created = 0
        links_skipped = 0

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

        # Process Links
        for ext_link in delta.links:
            try:
                src_name = ext_link.source_entity_name.lower()
                tgt_name = ext_link.target_entity_name.lower()

                # Look up UUIDs from entities extracted in this batch
                source_uuid = name_to_uuid.get(src_name)
                target_uuid = name_to_uuid.get(tgt_name)

                # Skip link if we don't have both entities
                if not source_uuid or not target_uuid:
                    links_skipped += 1
                    logger.warning(
                        f"[ONTOLOGY_SUBGRAPH] ✗ Link references unknown entities: "
                        f"'{ext_link.source_entity_name}' (found: {bool(source_uuid)}) -> "
                        f"'{ext_link.target_entity_name}' (found: {bool(target_uuid)})"
                    )
                    continue

                # Generate UUID for this link
                link_uuid = uuid.uuid4()

                link = OntologyLink(
                    uuid=link_uuid,
                    source_uuid=source_uuid,
                    target_uuid=target_uuid,
                    type=ext_link.relationship_type,
                    mentions=[Mention(source_text=ext_link.context, thread_id=query_id)],
                    created_by="llm_extractor"
                )

                session_delta.links[str(link_uuid)] = link
                links_created += 1
                logger.info(
                    f"[ONTOLOGY_SUBGRAPH] ✓ Created link: UUID={link_uuid}, "
                    f"'{ext_link.source_entity_name}' -[{ext_link.relationship_type}]-> '{ext_link.target_entity_name}'"
                )

            except Exception as link_error:
                logger.error(f"[ONTOLOGY_SUBGRAPH] Failed to process link '{ext_link.source_entity_name}' -> '{ext_link.target_entity_name}': {link_error}")
                logger.exception("[ONTOLOGY_SUBGRAPH] Link processing stack trace:")

        logger.info("[ONTOLOGY_SUBGRAPH] === EXTRACTION SUMMARY ===")
        logger.info(f"[ONTOLOGY_SUBGRAPH] ✓ Entities created: {entities_created}")
        logger.info(f"[ONTOLOGY_SUBGRAPH] ✓ Links created: {links_created}")
        logger.info(f"[ONTOLOGY_SUBGRAPH] ✗ Links skipped (missing references): {links_skipped}")
        logger.info("[ONTOLOGY_SUBGRAPH] ==========================")
        
        return {"extracted_delta": session_delta}

    except Exception as e:
        logger.error(f"[ONTOLOGY_SUBGRAPH] Critical error during ontology extraction: {e}")
        logger.exception("[ONTOLOGY_SUBGRAPH] Full stack trace:")
        return {"extracted_delta": SessionOntology()}


def create_ontology_subgraph() -> StateGraph:
    workflow = StateGraph(OntologySubGraphState)
    workflow.add_node("extract_ontology", extract_ontology_node)
    workflow.set_entry_point("extract_ontology")
    workflow.add_edge("extract_ontology", "__end__")
    return workflow.compile()


ontology_subgraph = create_ontology_subgraph()
