"""
Graph Store Service

Neo4j-backed graph storage for ontology entities and relationships.
Provides CRUD operations, graph traversal, and RAG-oriented retrieval.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from neo4j import Driver
import logging
import json

logger = logging.getLogger(__name__)


class GraphStoreService:
    """Service for Neo4j graph database operations."""

    def __init__(self, driver: Driver):
        self.driver = driver
        self._ensure_constraints()

    def _run(self, query: str, params: dict = None) -> List[Dict[str, Any]]:
        """Execute a Cypher query and return results as list of dicts."""
        with self.driver.session() as session:
            result = session.run(query, params or {})
            return [record.data() for record in result]

    def _run_write(self, query: str, params: dict = None) -> None:
        """Execute a write Cypher query."""
        with self.driver.session() as session:
            session.run(query, params or {})

    def _ensure_constraints(self) -> None:
        """Create uniqueness constraints for entities."""
        constraints = [
            "CREATE CONSTRAINT entity_uuid IF NOT EXISTS FOR (e:Entity) REQUIRE e.uuid IS UNIQUE",
        ]
        with self.driver.session() as session:
            for constraint in constraints:
                try:
                    session.run(constraint)
                except Exception as e:
                    logger.debug("[GRAPH_STORE] Constraint setup: %s", e)
        logger.info("[GRAPH_STORE] Neo4j constraints ensured")

    # ----------------------------------------------------------------
    # Entity CRUD
    # ----------------------------------------------------------------

    def create_entity(
        self,
        uuid: str,
        name: str,
        type: str,
        thread_id: str,
        properties: dict = None,
        mentions: list = None,
        created_by: str = "llm_extractor",
    ) -> None:
        """Create or merge an entity node."""
        now = datetime.utcnow().isoformat()
        props = {
            "uuid": uuid,
            "name": name,
            "type": type,
            "thread_id": thread_id,
            "created_at": now,
            "updated_at": now,
            "created_by": created_by,
            **(properties or {}),
        }
        mentions_json = json.dumps(
            [
                m.model_dump(mode="json") if hasattr(m, "model_dump") else m
                for m in (mentions or [])
            ]
        )
        props["mentions"] = mentions_json

        label = self._type_to_label(type)
        query = f"""
        MERGE (e:{label} {{uuid: $uuid}})
        ON CREATE SET e += $props
        ON MATCH SET e.updated_at = $now, e.mentions = e.mentions + $mentions
        """
        self._run_write(
            query,
            {
                "uuid": uuid,
                "props": props,
                "now": now,
                "mentions": mentions_json,
            },
        )
        logger.debug("[GRAPH_STORE] Created/merged entity: %s (%s)", name, uuid)

    def get_entity_by_uuid(self, uuid: str) -> Optional[Dict[str, Any]]:
        """Get entity by UUID."""
        results = self._run(
            "MATCH (e:Entity {uuid: $uuid}) RETURN e",
            {"uuid": uuid},
        )
        if results:
            return results[0]["e"]
        return None

    def get_entities_by_name(
        self, name: str, thread_id: str = None
    ) -> List[Dict[str, Any]]:
        """Find entities by name (case-insensitive)."""
        params = {"name": name.lower()}
        thread_filter = "AND e.thread_id = $thread_id" if thread_id else ""
        if thread_id:
            params["thread_id"] = thread_id
        query = f"""
        MATCH (e:Entity)
        WHERE toLower(e.name) = $name {thread_filter}
        RETURN e
        """
        results = self._run(query, params)
        return [r["e"] for r in results]

    def update_entity(self, uuid: str, updates: dict) -> None:
        """Update entity properties."""
        now = datetime.utcnow().isoformat()
        query = """
        MATCH (e:Entity {uuid: $uuid})
        SET e += $updates, e.updated_at = $now
        """
        self._run_write(query, {"uuid": uuid, "updates": updates, "now": now})

    def delete_entity(self, uuid: str) -> None:
        """Delete entity and all its relationships."""
        query = """
        MATCH (e:Entity {uuid: $uuid})
        DETACH DELETE e
        """
        self._run_write(query, {"uuid": uuid})

    # ----------------------------------------------------------------
    # Link/Relationship CRUD
    # ----------------------------------------------------------------

    def create_link(
        self,
        uuid: str,
        source_uuid: str,
        target_uuid: str,
        type: str,
        thread_id: str,
        properties: dict = None,
        mentions: list = None,
    ) -> None:
        """Create a relationship between two entities."""
        now = datetime.utcnow().isoformat()
        rel_type = self._type_to_rel_type(type)
        mentions_json = json.dumps(
            [
                m.model_dump(mode="json") if hasattr(m, "model_dump") else m
                for m in (mentions or [])
            ]
        )

        query = f"""
        MATCH (s:Entity {{uuid: $source_uuid}})
        MATCH (t:Entity {{uuid: $target_uuid}})
        MERGE (s)-[r:{rel_type} {{uuid: $uuid}}]->(t)
        ON CREATE SET r.type = $type, r.thread_id = $thread_id,
                      r.created_at = $now, r.updated_at = $now,
                      r.properties = $properties, r.mentions = $mentions
        """
        self._run_write(
            query,
            {
                "uuid": uuid,
                "source_uuid": source_uuid,
                "target_uuid": target_uuid,
                "type": type,
                "thread_id": thread_id,
                "properties": properties or {},
                "mentions": mentions_json,
                "now": now,
            },
        )
        logger.debug(
            "[GRAPH_STORE] Created link: %s -[%s]-> %s",
            source_uuid,
            type,
            target_uuid,
        )

    def get_links_for_entity(
        self, entity_uuid: str, thread_id: str = None
    ) -> List[Dict[str, Any]]:
        """Get all relationships for an entity."""
        thread_filter = "AND r.thread_id = $thread_id" if thread_id else ""
        params = {"entity_uuid": entity_uuid}
        if thread_id:
            params["thread_id"] = thread_id
        query = f"""
        MATCH (e:Entity {{uuid: $entity_uuid}})-[r]-(other:Entity)
        WHERE true {thread_filter}
        RETURN r, other,
               CASE WHEN startNode(r).uuid = $entity_uuid THEN 'OUTGOING' ELSE 'INCOMING' END AS direction
        """
        results = self._run(query, params)
        return results

    def delete_link(self, uuid: str) -> None:
        """Delete a relationship by UUID."""
        query = """
        MATCH ()-[r {uuid: $uuid}]->()
        DELETE r
        """
        self._run_write(query, {"uuid": uuid})

    # ----------------------------------------------------------------
    # Graph Traversal
    # ----------------------------------------------------------------

    def get_neighbors(
        self, entity_uuid: str, hops: int = 1, thread_id: str = None
    ) -> List[Dict[str, Any]]:
        """Get entities connected within N hops."""
        thread_filter = (
            "AND all(rel IN relationships(p) WHERE rel.thread_id = $thread_id)"
            if thread_id
            else ""
        )
        params = {"entity_uuid": entity_uuid, "hops": hops}
        if thread_id:
            params["thread_id"] = thread_id
        query = f"""
        MATCH (e:Entity {{uuid: $entity_uuid}})
        MATCH p = (e)-[*1..$hops]-(neighbor:Entity)
        WHERE neighbor.uuid <> $entity_uuid
        {thread_filter}
        RETURN DISTINCT neighbor
        """
        results = self._run(query, params)
        return [r["neighbor"] for r in results]

    def get_subgraph(
        self, entity_uuid: str, hops: int = 2, thread_id: str = None
    ) -> Dict[str, Any]:
        """Get full subgraph around an entity."""
        params = {"entity_uuid": entity_uuid, "hops": hops}
        thread_filter = ""
        if thread_id:
            params["thread_id"] = thread_id
            thread_filter = (
                "AND all(rel IN relationships(p) WHERE rel.thread_id = $thread_id)"
            )

        query = f"""
        MATCH (center:Entity {{uuid: $entity_uuid}})
        MATCH p = (center)-[*0..$hops]-(other:Entity)
        WHERE true {thread_filter}
        WITH collect(DISTINCT center) + collect(DISTINCT other) AS all_nodes
        UNWIND all_nodes AS node
        WITH collect(DISTINCT node) AS nodes
        MATCH (a)-[r]-(b)
        WHERE a IN nodes AND b IN nodes
        RETURN nodes, collect(DISTINCT r) AS relationships
        """
        results = self._run(query, params)
        if results:
            return {
                "entities": results[0].get("nodes", []),
                "links": results[0].get("relationships", []),
            }
        return {"entities": [], "links": []}

    # ----------------------------------------------------------------
    # RAG-Oriented Retrieval
    # ----------------------------------------------------------------

    def get_entities_by_type(
        self, type: str, thread_id: str = None, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get entities filtered by type."""
        params = {"type": type.lower(), "limit": limit}
        thread_filter = "AND e.thread_id = $thread_id" if thread_id else ""
        if thread_id:
            params["thread_id"] = thread_id
        query = f"""
        MATCH (e:Entity)
        WHERE toLower(e.type) = $type {thread_filter}
        RETURN e
        ORDER BY e.created_at DESC
        LIMIT $limit
        """
        results = self._run(query, params)
        return [r["e"] for r in results]

    def search_entities_by_name_pattern(
        self, pattern: str, thread_id: str = None, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Search entities by name pattern (partial match)."""
        params = {"pattern": f".*{pattern}.*", "limit": limit}
        thread_filter = "AND e.thread_id = $thread_id" if thread_id else ""
        if thread_id:
            params["thread_id"] = thread_id
        query = f"""
        MATCH (e:Entity)
        WHERE e.name =~ $pattern {thread_filter}
        RETURN e
        LIMIT $limit
        """
        results = self._run(query, params)
        return [r["e"] for r in results]

    def get_related_entities(
        self, entity_names: List[str], thread_id: str = None, hops: int = 2
    ) -> List[Dict[str, Any]]:
        """Get entities related to a list of named entities."""
        params = {"names": [n.lower() for n in entity_names], "hops": hops}
        thread_filter = "AND n.thread_id = $thread_id" if thread_id else ""
        if thread_id:
            params["thread_id"] = thread_id
        query = f"""
        MATCH (n:Entity)
        WHERE toLower(n.name) IN $names {thread_filter}
        MATCH p = (n)-[*1..$hops]-(related:Entity)
        WHERE NOT toLower(related.name) IN $names
        RETURN DISTINCT related
        LIMIT 50
        """
        results = self._run(query, params)
        return [r["related"] for r in results]

    def get_context_for_query(
        self,
        entity_names: List[str],
        thread_id: str = None,
        max_entities: int = 10,
    ) -> str:
        """Build a text context string from the ontology graph for a query."""
        if not entity_names:
            return ""

        related = self.get_related_entities(entity_names, thread_id=thread_id, hops=2)

        context_parts = []
        for entity in related[:max_entities]:
            name = entity.get("name", "Unknown")
            etype = entity.get("type", "Entity")
            props = entity.get("properties", {})
            mentions = entity.get("mentions", [])

            desc = f"- {name} ({etype})"
            if props:
                prop_str = ", ".join(f"{k}: {v}" for k, v in props.items() if v)
                if prop_str:
                    desc += f" [{prop_str}]"
            if mentions:
                latest = mentions[-1] if mentions else None
                if latest:
                    source = (
                        latest.get("source_text", "")
                        if isinstance(latest, dict)
                        else str(latest)
                    )
                    if source:
                        desc += f" - mentioned: {source[:100]}"
            context_parts.append(desc)

        rels = self._get_relationships_between_names(entity_names, thread_id)
        if rels:
            rel_parts = []
            for rel in rels:
                src = rel.get("source_name", "?")
                tgt = rel.get("target_name", "?")
                rtype = rel.get("type", "RELATED_TO")
                rel_parts.append(f"- {src} --[{rtype}]--> {tgt}")
            context_parts.extend(rel_parts)

        if context_parts:
            return "KNOWN ONTOLOGY CONTEXT:\n" + "\n".join(context_parts)
        return ""

    def _get_relationships_between_names(
        self, names: List[str], thread_id: str = None
    ) -> List[Dict[str, Any]]:
        """Get direct relationships between named entities."""
        params = {"names": [n.lower() for n in names]}
        thread_filter = "AND r.thread_id = $thread_id" if thread_id else ""
        if thread_id:
            params["thread_id"] = thread_id
        query = f"""
        MATCH (a:Entity)-[r]->(b:Entity)
        WHERE toLower(a.name) IN $names AND toLower(b.name) IN $names
        {thread_filter}
        RETURN a.name AS source_name, b.name AS target_name, r.type AS type
        """
        return self._run(query, params)

    # ----------------------------------------------------------------
    # Bulk Operations
    # ----------------------------------------------------------------

    def clear_thread_ontology(self, thread_id: str) -> None:
        """Delete all entities and relationships for a thread."""
        query = """
        MATCH (e:Entity {thread_id: $thread_id})
        DETACH DELETE e
        """
        self._run_write(query, {"thread_id": thread_id})
        logger.info("[GRAPH_STORE] Cleared ontology for thread: %s", thread_id)

    def get_all_entities(
        self, thread_id: str = None, limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """Get all entities, optionally filtered by thread."""
        params = {"limit": limit}
        thread_filter = ""
        if thread_id:
            params["thread_id"] = thread_id
            thread_filter = "WHERE e.thread_id = $thread_id"
        query = f"""
        MATCH (e:Entity)
        {thread_filter}
        RETURN e
        ORDER BY e.created_at DESC
        LIMIT $limit
        """
        results = self._run(query, params)
        return [r["e"] for r in results]

    def get_all_links(
        self, thread_id: str = None, limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """Get all relationships, optionally filtered by thread."""
        params = {"limit": limit}
        thread_filter = ""
        if thread_id:
            params["thread_id"] = thread_id
            thread_filter = "WHERE r.thread_id = $thread_id"
        query = f"""
        MATCH (a:Entity)-[r]->(b:Entity)
        {thread_filter}
        RETURN r, a.name AS source_name, b.name AS target_name
        ORDER BY r.created_at DESC
        LIMIT $limit
        """
        results = self._run(query, params)
        return results

    def get_stats(self, thread_id: str = None) -> Dict[str, Any]:
        """Get ontology statistics."""
        params = {}
        thread_filter = ""
        if thread_id:
            params["thread_id"] = thread_id
            thread_filter = "WHERE e.thread_id = $thread_id"

        entity_count = self._run(
            f"MATCH (e:Entity) {thread_filter} RETURN count(e) AS count",
            params,
        )
        link_count = self._run(
            f"MATCH ()-[r]->() {thread_filter.replace('e.', 'r.')} RETURN count(r) AS count",
            params,
        )

        return {
            "entity_count": entity_count[0]["count"] if entity_count else 0,
            "link_count": link_count[0]["count"] if link_count else 0,
        }

    # ----------------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------------

    @staticmethod
    def _type_to_label(type: str) -> str:
        """Convert entity type to a valid Neo4j label."""
        label = type.strip().replace(" ", "_")
        if not label[0].isalpha():
            label = "E_" + label
        return label

    @staticmethod
    def _type_to_rel_type(type: str) -> str:
        """Convert relationship type to a valid Neo4j relationship type."""
        rel = type.strip().replace(" ", "_").replace("-", "_")
        if not rel[0].isalpha():
            rel = "R_" + rel
        return rel.upper()
