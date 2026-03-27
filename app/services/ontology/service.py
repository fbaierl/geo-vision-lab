"""
Ontology Service

High-level service for ontology operations:
- Load/save from MongoDB
- Entity lookup by UUID or name
- Graph traversal (neighbors, relationships)
"""

from typing import Optional, List
from uuid import UUID
from app.models.ontology import OntologyEntity, OntologyLink, SessionOntology


class OntologyService:
    """Service for ontology operations."""
    
    def __init__(self, db):
        self.db = db
    
    async def load_ontology(self, thread_id: str) -> SessionOntology:
        """
        Load ontology for a thread from array-format MongoDB storage.
        
        Args:
            thread_id: Thread/session ID
        
        Returns:
            SessionOntology object
        """
        session = await self.db.sessions.find_one({"thread_id": thread_id})
        if not session:
            return SessionOntology()
        return SessionOntology.from_array_format(session.get("ontology", {}))
    
    async def save_ontology(self, thread_id: str, ontology: SessionOntology):
        """
        Save ontology to MongoDB (converts to array format).
        
        Args:
            thread_id: Thread/session ID
            ontology: Ontology to save
        """
        await self.db.sessions.update_one(
            {"thread_id": thread_id},
            {"$set": {"ontology": ontology.to_array_format()}}
        )
    
    async def get_entity_by_uuid(
        self, 
        thread_id: str, 
        entity_uuid: UUID
    ) -> Optional[OntologyEntity]:
        """
        Get entity by UUID.
        
        Args:
            thread_id: Thread/session ID
            entity_uuid: Entity UUID
        
        Returns:
            OntologyEntity or None if not found
        """
        ontology = await self.load_ontology(thread_id)
        return ontology.entities.get(str(entity_uuid))
    
    async def get_entity_by_name(
        self, 
        thread_id: str, 
        name: str
    ) -> List[OntologyEntity]:
        """
        Find entities by name (returns list for homonyms).
        
        Example: "Georgia" returns both Georgia (country) and Georgia (US state)
        
        Args:
            thread_id: Thread/session ID
            name: Entity name to search for
        
        Returns:
            List of matching OntologyEntity objects
        """
        ontology = await self.load_ontology(thread_id)
        name_lower = name.lower().strip()
        return [e for e in ontology.entities.values() if e.name.lower() == name_lower]
    
    async def get_neighbors(
        self,
        thread_id: str,
        entity_uuid: UUID,
        hops: int = 1
    ) -> List[OntologyEntity]:
        """
        Get entities connected to given entity within N hops.
        
        Args:
            thread_id: Thread/session ID
            entity_uuid: Starting entity UUID
            hops: Number of hops to traverse (default: 1)
        
        Returns:
            List of neighboring OntologyEntity objects
        """
        ontology = await self.load_ontology(thread_id)
        
        connected_uuids = set()
        for link in ontology.links.values():
            if link.source_uuid == entity_uuid:
                connected_uuids.add(link.target_uuid)
            elif link.target_uuid == entity_uuid:
                connected_uuids.add(link.source_uuid)
        
        neighbors = [
            ontology.entities.get(str(u)) 
            for u in connected_uuids 
            if str(u) in ontology.entities
        ]
        
        if hops > 1:
            for neighbor_uuid in connected_uuids:
                more = await self.get_neighbors(thread_id, neighbor_uuid, hops=hops - 1)
                neighbors.extend(more)
        
        return neighbors
    
    async def get_links_for_entity(
        self,
        thread_id: str,
        entity_uuid: UUID
    ) -> List[OntologyLink]:
        """
        Get all links involving this entity.
        
        Args:
            thread_id: Thread/session ID
            entity_uuid: Entity UUID
        
        Returns:
            List of OntologyLink objects
        """
        ontology = await self.load_ontology(thread_id)
        return [
            l for l in ontology.links.values() 
            if l.source_uuid == entity_uuid or l.target_uuid == entity_uuid
        ]
    
    async def get_entity_graph(
        self,
        thread_id: str,
        entity_uuid: UUID,
        hops: int = 2
    ) -> SessionOntology:
        """
        Get full subgraph for an entity (entity + neighbors + links between them).
        
        Args:
            thread_id: Thread/session ID
            entity_uuid: Center entity UUID
            hops: Number of hops to include (default: 2)
        
        Returns:
            SessionOntology containing the subgraph
        """
        ontology = await self.load_ontology(thread_id)
        
        # Get all entities in the subgraph
        subgraph_entities = {
            str(entity_uuid): ontology.entities.get(str(entity_uuid))
        }
        neighbors = await self.get_neighbors(thread_id, entity_uuid, hops=hops)
        for neighbor in neighbors:
            subgraph_entities[str(neighbor.uuid)] = neighbor
        
        # Get all links between these entities
        entity_uuids = set(e.uuid for e in subgraph_entities.values() if e)
        subgraph_links = {}
        for link in ontology.links.values():
            if link.source_uuid in entity_uuids and link.target_uuid in entity_uuids:
                subgraph_links[str(link.uuid)] = link
        
        return SessionOntology(
            entities=subgraph_entities,
            links=subgraph_links
        )
