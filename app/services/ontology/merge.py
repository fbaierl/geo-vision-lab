"""
Ontology Merge Logic

Handles merging of ontology deltas into existing ontologies.
Uses UUID-based matching with name-based deduplication.
"""

from datetime import datetime
from app.models.ontology import SessionOntology, OntologyEntity, OntologyLink


def merge_ontologies(
    current: SessionOntology, delta: SessionOntology
) -> SessionOntology:
    """
    Merge delta into current ontology.

    Uses UUID-based matching with name deduplication:
    - Entities with same UUID are merged (mentions + properties)
    - Entities with same name+type are merged (deduplication)
    - Links are merged by UUID, with source/target remapping for deduplicated entities

    Args:
        current: Existing ontology
        delta: New ontology delta to merge

    Returns:
        Merged ontology
    """
    merged = SessionOntology()
    merged.entities = dict(current.entities)

    # Build name+type -> UUID mapping for existing entities
    name_to_uuid = {}
    for uuid_str, entity in current.entities.items():
        key = f"{entity.name.lower()}|{entity.type}"
        name_to_uuid[key] = uuid_str

    # Track UUID remapping for link updates
    uuid_remap = {}

    for uuid_str, new_entity in delta.entities.items():
        if uuid_str in current.entities:
            # Same UUID - merge mentions and properties
            existing = current.entities[uuid_str]
            existing.mentions.extend(new_entity.mentions)

            # Update properties (new info takes precedence)
            for k, v in new_entity.properties.items():
                if v is not None:
                    existing.properties[k] = v

            existing.updated_at = datetime.utcnow()
            merged.entities[uuid_str] = existing
        else:
            # Check for name+type duplicate
            key = f"{new_entity.name.lower()}|{new_entity.type}"
            if key in name_to_uuid:
                # Duplicate found - merge into existing entity
                existing_uuid = name_to_uuid[key]
                existing = merged.entities[existing_uuid]

                # Add new mentions
                for mention in new_entity.mentions:
                    # Avoid duplicate mentions
                    if not any(
                        m.source_text == mention.source_text for m in existing.mentions
                    ):
                        existing.mentions.append(mention)

                # Merge properties (new info takes precedence)
                for k, v in new_entity.properties.items():
                    if v is not None and k not in existing.properties:
                        existing.properties[k] = v

                existing.updated_at = datetime.utcnow()

                # Record UUID remapping for link updates
                uuid_remap[uuid_str] = existing_uuid
            else:
                # New unique entity
                merged.entities[uuid_str] = new_entity
                name_to_uuid[key] = uuid_str

    # Merge links with UUID remapping
    merged.links = dict(current.links)
    for uuid_str, new_link in delta.links.items():
        if uuid_str not in current.links:
            # Remap source and target UUIDs if they were deduplicated
            # Convert UUID objects to strings for lookup
            source_uuid_str = str(new_link.source_uuid)
            target_uuid_str = str(new_link.target_uuid)

            source_uuid = uuid_remap.get(source_uuid_str, source_uuid_str)
            target_uuid = uuid_remap.get(target_uuid_str, target_uuid_str)

            # Create new link with remapped UUIDs
            remapped_link = OntologyLink(
                uuid=new_link.uuid,
                source_uuid=source_uuid,
                target_uuid=target_uuid,
                type=new_link.type,
                properties=new_link.properties,
                mentions=new_link.mentions,
                created_at=new_link.created_at,
                updated_at=new_link.updated_at,
            )
            merged.links[uuid_str] = remapped_link

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
