"""
LLM-driven Relationship Discovery Service

Given selected entities, uses an LLM to discover relationships between them
by analyzing existing ontology, conversation history, and source documents.
New discoveries are added to pending ontology for review.
"""

import logging
import re
import json
import uuid
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq

from app.models.ontology import (
    SessionOntology,
    OntologyEntity,
    OntologyLink,
    Mention,
    OntologyDelta,
    OntologyDeltaEntity,
    OntologyDeltaLink,
)
from app.core.di_llm import get_llm

logger = logging.getLogger("agent_flow")


def _extract_json_from_response(content: str) -> str:
    """Extract JSON from an LLM response that may contain markdown fences or prose."""
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
    if fence_match:
        return fence_match.group(1).strip()
    brace_start = content.find("{")
    brace_end = content.rfind("}")
    if brace_start != -1 and brace_end != -1 and brace_end > brace_start:
        return content[brace_start : brace_end + 1]
    return content


class RelationshipDiscoveryService:
    """Discovers relationships between selected entities using LLM analysis."""

    def __init__(self, llm):
        self.llm = llm
        underlying_llm = llm
        if hasattr(llm, "bound"):
            underlying_llm = llm.bound
        self.is_groq = (
            isinstance(underlying_llm, ChatGroq)
            or "ChatGroq" in type(underlying_llm).__name__
            or "ChatGroq" in str(type(underlying_llm))
        )

        self.prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are an expert Intelligence Analyst tasked with discovering relationships between selected entities.\n\n"
                    "## Task\n"
                    "Analyze the provided context (existing ontology, conversation history, and source documents) and discover ALL relevant relationships between the SELECTED entities.\n"
                    "You may also discover NEW intermediary entities and relationships involving them.\n\n"
                    "## Selected Entities\n"
                    "{selected_entities}\n\n"
                    "## Existing Ontology Context\n"
                    "{ontology_context}\n\n"
                    "## Conversation History\n"
                    "{conversation_history}\n\n"
                    "## Source Document Context\n"
                    "{source_context}\n\n"
                    "## Output Format\n"
                    "Your output MUST be a valid JSON object with this structure:\n"
                    "{{\n"
                    '  "entities": [\n'
                    '    {{"name": "New Entity Name", "type": "Person", "context": "explanation of why this entity is relevant"}}\n'
                    "  ],\n"
                    '  "links": [\n'
                    '    {{"source_entity_name": "Entity A", "target_entity_name": "Entity B", "relationship_type": "RELATED_TO", "context": "evidence supporting this relationship"}}\n'
                    "  ]\n"
                    "}}\n\n"
                    "## CRITICAL INSTRUCTIONS:\n"
                    "1. Discover relationships BETWEEN the selected entities AND any newly discovered intermediary entities\n"
                    "2. Only include NEW entities and NEW links - do NOT repeat ones already in the existing ontology\n"
                    "3. Use exact entity names as they appear in the context\n"
                    "4. The 'context' field must explain WHY this relationship/entity exists based on the evidence\n"
                    "5. Do NOT add markdown formatting (no ```json blocks) - output raw JSON only\n"
                    "6. Use CAPS_SNAKE_CASE for relationship types (e.g., LOCATED_IN, AFFILIATED_WITH, SUPPORTS)\n"
                    "7. You are NOT limited to predefined relationship types - discover new ones as needed\n"
                    "8. If no new relationships can be discovered, return empty arrays\n"
                    "9. Entity types: Location, Person, Organization, Event, Asset, Document, Concept",
                ),
                ("human", "Discover relationships for the selected entities."),
            ]
        )

    def discover(
        self,
        selected_entities: List[Dict[str, Any]],
        ontology_context: str,
        conversation_history: str,
        source_context: str,
    ) -> Tuple[Optional[OntologyDelta], str]:
        """
        Discover relationships between selected entities.

        Returns:
            Tuple of (OntologyDelta with newly discovered entities and links, prompt_text).
        """
        if not selected_entities or len(selected_entities) < 2:
            logger.warning(
                "[RELATIONSHIP_DISCOVERY] At least 2 entities required for discovery"
            )
            return None, ""

        logger.info(
            f"[RELATIONSHIP_DISCOVERY] Starting discovery for {len(selected_entities)} entities"
        )

        # Format selected entities for prompt
        selected_str = "\n".join(
            f"- {e.get('name', 'Unknown')} ({e.get('type', 'Unknown')})"
            for e in selected_entities
        )

        # Build the prompt text for transparency/logging
        try:
            prompt_messages = self.prompt.format_messages(
                selected_entities=selected_str,
                ontology_context=ontology_context or "No existing ontology context.",
                conversation_history=conversation_history or "No conversation history.",
                source_context=source_context or "No source documents.",
            )
            prompt_text = "\n\n".join(
                f"{m.type.upper()}: {m.content}" for m in prompt_messages
            )
        except Exception as fmt_err:
            logger.warning(f"[RELATIONSHIP_DISCOVERY] Failed to format prompt: {fmt_err}")
            prompt_text = ""

        # Use fallback JSON parsing (same pattern as ontology extractor)
        try:
            if self.is_groq:
                discovery_llm = self.llm
            else:
                discovery_llm = self.llm.bind(format="json")

            chain = (self.prompt | discovery_llm).with_config(
                {"tags": ["relationship_discovery"]}
            )
            response = chain.invoke(
                {
                    "selected_entities": selected_str,
                    "ontology_context": ontology_context or "No existing ontology context.",
                    "conversation_history": conversation_history or "No conversation history.",
                    "source_context": source_context or "No source documents.",
                }
            )
            content = response.content

            logger.debug(
                f"[RELATIONSHIP_DISCOVERY] Raw LLM response ({len(content)} chars): {content[:500]}..."
            )

            content = _extract_json_from_response(content)
            data = json.loads(content)

            result = OntologyDelta.model_validate(data)
            logger.info(
                f"[RELATIONSHIP_DISCOVERY] Discovery successful: {len(result.entities)} new entities, {len(result.links)} new links"
            )
            return result, prompt_text

        except json.JSONDecodeError as json_err:
            logger.error(
                f"[RELATIONSHIP_DISCOVERY] JSON parsing failed: {json_err}"
            )
            logger.error(
                f"[RELATIONSHIP_DISCOVERY] Invalid JSON content: {content[:1000] if 'content' in locals() else 'N/A'}..."
            )
            return None, prompt_text
        except Exception as e:
            logger.error(f"[RELATIONSHIP_DISCOVERY] Discovery failed: {e}")
            logger.exception("[RELATIONSHIP_DISCOVERY] Discovery stack trace:")
            return None, prompt_text


def _safe_parse_properties(properties_raw):
    """Safely parse properties that may be JSON strings from Neo4j."""
    if isinstance(properties_raw, str):
        try:
            properties_raw = json.loads(properties_raw)
        except (json.JSONDecodeError, ValueError):
            return {}
    if isinstance(properties_raw, dict):
        return properties_raw
    return {}


def _ensure_dict(obj):
    """Safely cast an object to a dict, or return empty dict."""
    if isinstance(obj, dict):
        return obj
    return {}


def _build_ontology_context(
    thread_id: str,
    selected_uuids: List[str],
    graph_store,
    pending_ontology: Optional[Dict[str, Any]] = None,
) -> str:
    """Build ontology context string from existing committed and pending entities."""
    context_parts = []

    # Get subgraphs around each selected entity
    all_entities = {}
    all_links = []

    for entity_uuid in selected_uuids:
        try:
            subgraph = graph_store.get_subgraph(entity_uuid, hops=2, thread_id=thread_id)
            for ent in _ensure_dict(subgraph).get("entities", []):
                ent = _ensure_dict(ent)
                if ent:
                    all_entities[ent.get("uuid")] = ent
            for link in _ensure_dict(subgraph).get("links", []):
                all_links.append(link)
        except Exception as e:
            logger.warning(
                f"[RELATIONSHIP_DISCOVERY] Failed to get subgraph for {entity_uuid}: {e}"
            )

    # Also include pending ontology context
    if pending_ontology:
        pending_entities = _ensure_dict(pending_ontology).get("entities", {})
        pending_links = _ensure_dict(pending_ontology).get("links", {})
        for uuid_str, ent in pending_entities.items():
            ent = _ensure_dict(ent)
            if ent:
                all_entities[uuid_str] = ent
        for uuid_str, link in pending_links.items():
            all_links.append(link)

    # Format entities
    if all_entities:
        context_parts.append("Existing Entities:")
        for ent in all_entities.values():
            ent = _ensure_dict(ent)
            if not ent:
                continue
            name = ent.get("name", "Unknown")
            etype = ent.get("type", "Unknown")
            props = _safe_parse_properties(ent.get("properties", {}))
            prop_str = ", ".join(f"{k}: {v}" for k, v in props.items() if v)
            line = f"- {name} ({etype})"
            if prop_str:
                line += f" [{prop_str}]"
            context_parts.append(line)

    # Format links
    if all_links:
        context_parts.append("\nExisting Relationships:")
        seen_links = set()
        for link in all_links:
            link = _ensure_dict(link)
            if not link:
                continue
            src_uuid = link.get("source_uuid") or link.get("source_id") or link.get("source")
            tgt_uuid = link.get("target_uuid") or link.get("target_id") or link.get("target")
            rtype = link.get("type", "RELATED_TO")

            src_name = "?"
            tgt_name = "?"
            for ent in all_entities.values():
                ent = _ensure_dict(ent)
                if not ent:
                    continue
                if ent.get("uuid") == src_uuid:
                    src_name = ent.get("name", "?")
                if ent.get("uuid") == tgt_uuid:
                    tgt_name = ent.get("name", "?")

            link_key = (src_name, tgt_name, rtype)
            if link_key not in seen_links:
                seen_links.add(link_key)
                context_parts.append(f"- {src_name} --[{rtype}]--> {tgt_name}")

    return "\n".join(context_parts) if context_parts else "No existing ontology."


def _build_conversation_history(messages: List[Dict[str, Any]]) -> str:
    """Build conversation history string from session messages."""
    if not messages:
        return ""

    parts = []
    for msg in messages:
        msg = _ensure_dict(msg)
        if not msg:
            continue
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if role == "user":
            parts.append(f"User: {content}")
        elif role == "assistant":
            parts.append(f"Assistant: {content}")

    return "\n\n".join(parts[-20:])  # Last 20 messages


def _build_source_context(
    vector_store, entity_names: List[str], k: int = 5
) -> str:
    """Search source documents for relevant chunks related to entity names."""
    if not vector_store or not entity_names:
        return ""

    # Use entity names as search queries
    query = " ".join(entity_names)
    try:
        results = vector_store.similarity_search(query, k=k)
        if not results:
            return ""

        parts = []
        for i, doc in enumerate(results, 1):
            doc = _ensure_dict(doc)
            if not doc:
                continue
            content = doc.get("page_content", "")
            source = _ensure_dict(doc.get("metadata", {})).get("source", "Unknown source")
            if content:
                parts.append(f"[Source {i}: {source}]\n{content[:800]}")

        return "\n\n".join(parts)
    except Exception as e:
        logger.warning(f"[RELATIONSHIP_DISCOVERY] Vector search failed: {e}")
        return ""


def discover_relationships(
    thread_id: str,
    selected_uuids: List[str],
    graph_store,
    vector_store,
    session_messages: List[Dict[str, Any]],
    pending_ontology: Optional[Dict[str, Any]] = None,
) -> Tuple[SessionOntology, str]:
    """
    High-level function to discover relationships between selected entities.

    Args:
        thread_id: Session thread ID
        selected_uuids: List of selected entity UUIDs
        graph_store: GraphStoreService instance
        vector_store: VectorStoreService instance
        session_messages: Session chat messages
        pending_ontology: Current pending ontology dict (optional)

    Returns:
        Tuple of (SessionOntology with newly discovered entities and links, prompt_text)
    """
    logger.info(
        f"[RELATIONSHIP_DISCOVERY] Discovering relationships for {len(selected_uuids)} entities in thread {thread_id}"
    )

    # Gather selected entity details
    selected_entities = []
    for uuid_str in selected_uuids:
        try:
            ent = graph_store.get_entity_by_uuid(uuid_str)
            if ent:
                selected_entities.append(
                    {
                        "uuid": uuid_str,
                        "name": ent.get("name", "Unknown"),
                        "type": ent.get("type", "Unknown"),
                        "properties": _safe_parse_properties(ent.get("properties", {})),
                    }
                )
            elif pending_ontology and uuid_str in pending_ontology.get("entities", {}):
                pending_ent = pending_ontology["entities"][uuid_str]
                selected_entities.append(
                    {
                        "uuid": uuid_str,
                        "name": pending_ent.get("name", "Unknown"),
                        "type": pending_ent.get("type", "Unknown"),
                        "properties": _safe_parse_properties(pending_ent.get("properties", {})),
                    }
                )
        except Exception as e:
            logger.warning(
                f"[RELATIONSHIP_DISCOVERY] Failed to load entity {uuid_str}: {e}"
            )

    if len(selected_entities) < 2:
        logger.warning(
            "[RELATIONSHIP_DISCOVERY] Less than 2 valid entities found, skipping discovery"
        )
        return SessionOntology(), ""

    # Build contexts
    ontology_context = _build_ontology_context(
        thread_id, selected_uuids, graph_store, pending_ontology
    )
    conversation_history = _build_conversation_history(session_messages)

    entity_names = [e["name"] for e in selected_entities]
    source_context = _build_source_context(vector_store, entity_names)

    # Run LLM discovery
    service = RelationshipDiscoveryService(llm=get_llm())
    delta, prompt_text = service.discover(
        selected_entities=selected_entities,
        ontology_context=ontology_context,
        conversation_history=conversation_history,
        source_context=source_context,
    )

    if not delta or (not delta.entities and not delta.links):
        logger.info("[RELATIONSHIP_DISCOVERY] No new relationships discovered")
        return SessionOntology(), prompt_text

    # Process delta into SessionOntology (same pattern as ontology_subgraph)
    from app.services.location_extractor import get_location_extractor

    session_delta = SessionOntology()
    name_to_uuid = {}

    # Process entities
    for ext_ent in delta.entities:
        try:
            entity_uuid = uuid.uuid4()
            properties = {}

            # Geocode locations
            if ext_ent.type == "Location":
                try:
                    loc_extractor = get_location_extractor()
                    candidates = loc_extractor.geocode_location(ext_ent.name)
                    if candidates:
                        best = candidates[0]
                        properties["lat"] = best["lat"]
                        properties["lon"] = best["lon"]
                        properties["country"] = best.get("country", "")
                        properties["display_name"] = best.get("display_name", "")
                except Exception as geo_error:
                    logger.warning(
                        f"[RELATIONSHIP_DISCOVERY] Geocoding failed for '{ext_ent.name}': {geo_error}"
                    )

            entity = OntologyEntity(
                uuid=entity_uuid,
                name=ext_ent.name,
                type=ext_ent.type,
                properties=properties,
                mentions=[
                    Mention(
                        source_text=ext_ent.context or "Discovered via LLM relationship discovery",
                        thread_id=thread_id,
                    )
                ],
                created_by="llm_relationship_discovery",
            )

            session_delta.entities[str(entity_uuid)] = entity
            name_to_uuid[ext_ent.name.lower()] = entity_uuid
            logger.info(
                f"[RELATIONSHIP_DISCOVERY] Created entity: {ext_ent.name} ({ext_ent.type})"
            )
        except Exception as e:
            logger.error(
                f"[RELATIONSHIP_DISCOVERY] Failed to process entity '{ext_ent.name}': {e}"
            )

    # Process links
    for ext_link in delta.links:
        try:
            src_name = ext_link.source_entity_name.lower()
            tgt_name = ext_link.target_entity_name.lower()

            source_uuid = name_to_uuid.get(src_name)
            target_uuid = name_to_uuid.get(tgt_name)

            # Also check selected entities and pending ontology
            if not source_uuid:
                for sel in selected_entities:
                    if sel["name"].lower() == src_name:
                        source_uuid = uuid.UUID(sel["uuid"])
                        break
            if not target_uuid:
                for sel in selected_entities:
                    if sel["name"].lower() == tgt_name:
                        target_uuid = uuid.UUID(sel["uuid"])
                        break

            # Check pending ontology
            if not source_uuid and pending_ontology:
                for u, ent in pending_ontology.get("entities", {}).items():
                    if ent.get("name", "").lower() == src_name:
                        source_uuid = uuid.UUID(u)
                        break
            if not target_uuid and pending_ontology:
                for u, ent in pending_ontology.get("entities", {}).items():
                    if ent.get("name", "").lower() == tgt_name:
                        target_uuid = uuid.UUID(u)
                        break

            # Check committed ontology via graph store
            if not source_uuid:
                try:
                    results = graph_store.get_entities_by_name(
                        ext_link.source_entity_name, thread_id=thread_id
                    )
                    if results:
                        source_uuid = uuid.UUID(results[0]["uuid"])
                except Exception:
                    pass
            if not target_uuid:
                try:
                    results = graph_store.get_entities_by_name(
                        ext_link.target_entity_name, thread_id=thread_id
                    )
                    if results:
                        target_uuid = uuid.UUID(results[0]["uuid"])
                except Exception:
                    pass

            if not source_uuid or not target_uuid:
                logger.warning(
                    f"[RELATIONSHIP_DISCOVERY] Skipping unresolvable link: '{ext_link.source_entity_name}' -> '{ext_link.target_entity_name}'"
                )
                continue

            link_uuid = uuid.uuid4()
            link = OntologyLink(
                uuid=link_uuid,
                source_uuid=source_uuid,
                target_uuid=target_uuid,
                type=ext_link.relationship_type,
                mentions=[
                    Mention(
                        source_text=ext_link.context or "Discovered via LLM relationship discovery",
                        thread_id=thread_id,
                    )
                ],
                created_by="llm_relationship_discovery",
            )

            session_delta.links[str(link_uuid)] = link
            logger.info(
                f"[RELATIONSHIP_DISCOVERY] Created link: {ext_link.source_entity_name} --[{ext_link.relationship_type}]--> {ext_link.target_entity_name}"
            )
        except Exception as e:
            logger.error(
                f"[RELATIONSHIP_DISCOVERY] Failed to process link '{ext_link.source_entity_name}' -> '{ext_link.target_entity_name}': {e}"
            )

    logger.info(
        f"[RELATIONSHIP_DISCOVERY] Discovery complete: {len(session_delta.entities)} entities, {len(session_delta.links)} links"
    )
    return session_delta, prompt_text
