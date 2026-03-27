"""
Ontology Merge Logic

Handles merging of ontology deltas into existing ontologies.
Uses UUID-based matching with homonym support.
"""

from datetime import datetime
from app.models.ontology import SessionOntology, OntologyEntity, OntologyLink


def merge_ontologies(current: SessionOntology, delta: SessionOntology) -> SessionOntology:
    """
    Merge delta into current ontology.
    
    Uses UUID-based matching:
    - Entities with same UUID are merged (mentions + properties)
    - Entities with same name but different UUID are kept separate (homonyms)
    - Links are merged by UUID
    
    Args:
        current: Existing ontology
        delta: New ontology delta to merge
    
    Returns:
        Merged ontology
    """
    merged = SessionOntology()
    merged.entities = dict(current.entities)
    
    for uuid_str, new_entity in delta.entities.items():
        if uuid_str in current.entities:
            # Same entity - merge mentions and properties
            existing = current.entities[uuid_str]
            existing.mentions.extend(new_entity.mentions)
            
            # Update properties (new info takes precedence)
            for k, v in new_entity.properties.items():
                if v is not None:
                    existing.properties[k] = v
            
            existing.updated_at = datetime.utcnow()
            merged.entities[uuid_str] = existing
        else:
            # New entity (or homonym with same name)
            merged.entities[uuid_str] = new_entity
    
    # Merge links
    merged.links = dict(current.links)
    for uuid_str, new_link in delta.links.items():
        if uuid_str not in current.links:
            merged.links[uuid_str] = new_link
    
    return merged


def merge_entity(existing: OntologyEntity, new: OntologyEntity) -> OntologyEntity:
    """
    Merge two entities with same UUID.
    
    - Accumulates mentions
    - Updates properties (new values take precedence)
    - Updates timestamp
    
    Args:
        existing: Existing entity (modified in place)
        new: New entity data to merge
    
    Returns:
        Merged entity
    """
    existing.mentions.extend(new.mentions)
    
    for k, v in new.properties.items():
        if v is not None:
            existing.properties[k] = v
    
    existing.updated_at = datetime.utcnow()
    return existing
