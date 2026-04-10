"""
Ontology Service

High-level service for ontology operations backed by Neo4j:
- Entity lookup by UUID or name
- Graph traversal (neighbors, relationships)
- Load/save SessionOntology from Neo4j
"""

from typing import Optional, List
from uuid import UUID
from datetime import datetime
import json

from app.models.ontology import OntologyEntity, OntologyLink, Mention, SessionOntology
from app.services.graph_store import GraphStoreService


class OntologyService:
    """Service for ontology operations backed by Neo4j."""

    def __init__(self, graph_store: GraphStoreService):
        self.graph_store = graph_store

    def load_ontology(self, thread_id: str) -> SessionOntology:
        """Load ontology for a thread from Neo4j."""
        entities = self.graph_store.get_all_entities(thread_id=thread_id)
        links = self.graph_store.get_all_links(thread_id=thread_id)

        ontology = SessionOntology()
        for e_data in entities:
            entity = self._dict_to_entity(e_data)
            if entity:
                ontology.entities[str(entity.uuid)] = entity

        for l_data in links:
            link = self._dict_to_link(l_data)
            if link:
                ontology.links[str(link.uuid)] = link

        return ontology

    def save_ontology(self, thread_id: str, ontology: SessionOntology) -> None:
        """Persist all entities and links in the ontology to Neo4j."""
        for entity in ontology.entities.values():
            self._save_entity(thread_id, entity)

        for link in ontology.links.values():
            self._save_link(thread_id, link)

    def _save_entity(self, thread_id: str, entity: OntologyEntity) -> None:
        """Save a single entity to Neo4j."""
        self.graph_store.create_entity(
            uuid=str(entity.uuid),
            name=entity.name,
            type=entity.type,
            thread_id=thread_id,
            properties=entity.properties,
            mentions=entity.mentions,
            created_by=entity.created_by,
        )

    def _save_link(self, thread_id: str, link: OntologyLink) -> None:
        """Save a single link to Neo4j."""
        self.graph_store.create_link(
            uuid=str(link.uuid),
            source_uuid=str(link.source_uuid),
            target_uuid=str(link.target_uuid),
            type=link.type,
            thread_id=thread_id,
            properties=link.properties,
            mentions=link.mentions,
        )

    def get_entity_by_uuid(
        self, thread_id: str, entity_uuid: UUID
    ) -> Optional[OntologyEntity]:
        """Get entity by UUID."""
        data = self.graph_store.get_entity_by_uuid(str(entity_uuid))
        if not data:
            return None
        return self._dict_to_entity(data)

    def get_entity_by_name(self, thread_id: str, name: str) -> List[OntologyEntity]:
        """Find entities by name (returns list for homonyms)."""
        results = self.graph_store.get_entities_by_name(name, thread_id=thread_id)
        entities = []
        for data in results:
            entity = self._dict_to_entity(data)
            if entity:
                entities.append(entity)
        return entities

    def get_neighbors(
        self, thread_id: str, entity_uuid: UUID, hops: int = 1
    ) -> List[OntologyEntity]:
        """Get entities connected to given entity within N hops."""
        results = self.graph_store.get_neighbors(
            str(entity_uuid), hops=hops, thread_id=thread_id
        )
        entities = []
        for data in results:
            entity = self._dict_to_entity(data)
            if entity:
                entities.append(entity)
        return entities

    def get_links_for_entity(
        self, thread_id: str, entity_uuid: UUID
    ) -> List[OntologyLink]:
        """Get all links involving this entity."""
        results = self.graph_store.get_links_for_entity(
            str(entity_uuid), thread_id=thread_id
        )
        links = []
        for data in results:
            link = self._dict_to_link_record(data)
            if link:
                links.append(link)
        return links

    def get_entity_graph(
        self, thread_id: str, entity_uuid: UUID, hops: int = 2
    ) -> SessionOntology:
        """Get full subgraph for an entity."""
        subgraph = self.graph_store.get_subgraph(
            str(entity_uuid), hops=hops, thread_id=thread_id
        )

        entities = {}
        for e_data in subgraph.get("entities", []):
            entity = self._dict_to_entity(e_data)
            if entity:
                entities[str(entity.uuid)] = entity

        links = {}
        for l_data in subgraph.get("links", []):
            link = self._dict_to_link_record(l_data)
            if link:
                links[str(link.uuid)] = link

        return SessionOntology(entities=entities, links=links)

    def get_context_for_query(
        self, entity_names: List[str], thread_id: str = None
    ) -> str:
        """Get ontology context for RAG retrieval."""
        return self.graph_store.get_context_for_query(entity_names, thread_id=thread_id)

    def get_stats(self, thread_id: str = None) -> dict:
        """Get ontology statistics."""
        return self.graph_store.get_stats(thread_id=thread_id)

    # -------------------------------------------------------------------------
    # Conversion helpers
    # -------------------------------------------------------------------------

    def _dict_to_entity(self, data: dict) -> Optional[OntologyEntity]:
        """Convert Neo4j node dict to OntologyEntity."""
        try:
            node = data.get("e", data)
            if not node:
                return None

            mentions_raw = node.get("mentions", [])
            mentions = []
            if isinstance(mentions_raw, str):
                mentions_parsed = json.loads(mentions_raw)
                if isinstance(mentions_parsed, list):
                    for m in mentions_parsed:
                        if isinstance(m, dict):
                            mentions.append(
                                Mention(
                                    source_text=m.get("source_text", ""),
                                    extracted_at=datetime.fromisoformat(
                                        m.get("extracted_at", datetime.utcnow().isoformat())
                                    ),
                                    confidence=m.get("confidence", 1.0),
                                    thread_id=m.get("thread_id"),
                                )
                            )
            elif isinstance(mentions_raw, list):
                for m in mentions_raw:
                    if isinstance(m, dict):
                        mentions.append(
                            Mention(
                                source_text=m.get("source_text", ""),
                                extracted_at=datetime.fromisoformat(
                                    m.get("extracted_at", datetime.utcnow().isoformat())
                                ),
                                confidence=m.get("confidence", 1.0),
                                thread_id=m.get("thread_id"),
                            )
                        )

            properties_raw = node.get("properties", {})
            if isinstance(properties_raw, str):
                properties_raw = json.loads(properties_raw)

            # Deserialize individual property values that were serialized as JSON strings
            if isinstance(properties_raw, dict):
                for key, value in properties_raw.items():
                    if isinstance(value, str):
                        try:
                            properties_raw[key] = json.loads(value)
                        except (json.JSONDecodeError, ValueError):
                            pass  # Keep as string if not valid JSON

            created_at_str = node.get("created_at", datetime.utcnow().isoformat())
            updated_at_str = node.get("updated_at", datetime.utcnow().isoformat())

            try:
                created_at = datetime.fromisoformat(created_at_str)
            except (ValueError, TypeError):
                created_at = datetime.utcnow()

            try:
                updated_at = datetime.fromisoformat(updated_at_str)
            except (ValueError, TypeError):
                updated_at = datetime.utcnow()

            return OntologyEntity(
                uuid=UUID(node.get("uuid")),
                name=node.get("name", ""),
                type=node.get("type", ""),
                properties=properties_raw,
                mentions=mentions,
                created_at=created_at,
                updated_at=updated_at,
                created_by=node.get("created_by", "llm_extractor"),
            )
        except Exception:
            return None

    def _dict_to_link(self, data: dict) -> Optional[OntologyLink]:
        """Convert Neo4j result dict to OntologyLink."""
        try:
            rel = data
            source_uuid = data.get("source_uuid", "")
            target_uuid = data.get("target_uuid", "")

            mentions_raw = rel.get("mentions", [])
            mentions = []
            if isinstance(mentions_raw, str):
                mentions_parsed = json.loads(mentions_raw)
                if isinstance(mentions_parsed, list):
                    for m in mentions_parsed:
                        if isinstance(m, dict):
                            mentions.append(
                                Mention(
                                    source_text=m.get("source_text", ""),
                                    extracted_at=datetime.fromisoformat(
                                        m.get("extracted_at", datetime.utcnow().isoformat())
                                    ),
                                    confidence=m.get("confidence", 1.0),
                                    thread_id=m.get("thread_id"),
                                )
                            )
            elif isinstance(mentions_raw, list):
                for m in mentions_raw:
                    if isinstance(m, dict):
                        mentions.append(
                            Mention(
                                source_text=m.get("source_text", ""),
                                extracted_at=datetime.fromisoformat(
                                    m.get("extracted_at", datetime.utcnow().isoformat())
                                ),
                                confidence=m.get("confidence", 1.0),
                                thread_id=m.get("thread_id"),
                            )
                        )

            properties_raw = rel.get("properties", {})
            if isinstance(properties_raw, str):
                properties_raw = json.loads(properties_raw)
            
            # Deserialize individual property values that were serialized as JSON strings
            if isinstance(properties_raw, dict):
                for key, value in properties_raw.items():
                    if isinstance(value, str):
                        try:
                            properties_raw[key] = json.loads(value)
                        except (json.JSONDecodeError, ValueError):
                            pass  # Keep as string if not valid JSON

            created_at_str = rel.get("created_at", datetime.utcnow().isoformat())
            updated_at_str = rel.get("updated_at", datetime.utcnow().isoformat())

            try:
                created_at = datetime.fromisoformat(created_at_str)
            except (ValueError, TypeError):
                created_at = datetime.utcnow()

            try:
                updated_at = datetime.fromisoformat(updated_at_str)
            except (ValueError, TypeError):
                updated_at = datetime.utcnow()

            return OntologyLink(
                uuid=UUID(rel.get("uuid")),
                source_uuid=UUID(source_uuid),
                target_uuid=UUID(target_uuid),
                type=rel.get("type", ""),
                properties=properties_raw,
                mentions=mentions,
                created_at=created_at,
                updated_at=updated_at,
            )
        except Exception:
            return None

    def _dict_to_link_record(self, data: dict) -> Optional[OntologyLink]:
        """Convert a Neo4j link record (with direction info) to OntologyLink."""
        try:
            rel = data.get("r", data)
            if not rel:
                return None

            other = data.get("other", {})
            direction = data.get("direction", "OUTGOING")

            mentions_raw = rel.get("mentions", [])
            mentions = []
            if isinstance(mentions_raw, str):
                mentions_raw = json.loads(mentions_raw)
            for m in mentions_raw:
                if isinstance(m, dict):
                    mentions.append(
                        Mention(
                            source_text=m.get("source_text", ""),
                            extracted_at=datetime.fromisoformat(
                                m.get("extracted_at", datetime.utcnow().isoformat())
                            ),
                            confidence=m.get("confidence", 1.0),
                            thread_id=m.get("thread_id"),
                        )
                    )

            properties_raw = rel.get("properties", {})
            if isinstance(properties_raw, str):
                properties_raw = json.loads(properties_raw)
            
            # Deserialize individual property values that were serialized as JSON strings
            if isinstance(properties_raw, dict):
                for key, value in properties_raw.items():
                    if isinstance(value, str):
                        try:
                            properties_raw[key] = json.loads(value)
                        except (json.JSONDecodeError, ValueError):
                            pass  # Keep as string if not valid JSON

            created_at_str = rel.get("created_at", datetime.utcnow().isoformat())
            updated_at_str = rel.get("updated_at", datetime.utcnow().isoformat())

            try:
                created_at = datetime.fromisoformat(created_at_str)
            except (ValueError, TypeError):
                created_at = datetime.utcnow()

            try:
                updated_at = datetime.fromisoformat(updated_at_str)
            except (ValueError, TypeError):
                updated_at = datetime.utcnow()

            if direction == "OUTGOING":
                source_uuid = rel.get("uuid", "")
                target_uuid = other.get("uuid", "")
            else:
                source_uuid = other.get("uuid", "")
                target_uuid = rel.get("uuid", "")

            return OntologyLink(
                uuid=UUID(rel.get("uuid")),
                source_uuid=UUID(source_uuid),
                target_uuid=UUID(target_uuid),
                type=rel.get("type", ""),
                properties=properties_raw,
                mentions=mentions,
                created_at=created_at,
                updated_at=updated_at,
            )
        except Exception:
            return None
