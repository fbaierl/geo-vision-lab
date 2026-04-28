"""
Ontology Merge Logic

Handles merging of ontology deltas into existing ontologies.
Uses UUID-based matching with name-based deduplication.
"""

from datetime import datetime
from app.models.ontology import SessionOntology, OntologyEntity, OntologyLink

_CROSS_TYPE_MERGE = {
    frozenset({"location", "country"}): "country",
}


def _merge_mentions(target: OntologyEntity, source: OntologyEntity) -> None:
    """Append non-duplicate mentions from source into target."""
    existing_texts = {m.source_text for m in target.mentions}
    for mention in source.mentions:
        if mention.source_text not in existing_texts:
            target.mentions.append(mention)


def _merge_properties(target: OntologyEntity, source: OntologyEntity) -> None:
    """Copy non-None properties from source that target doesn't already have."""
    for k, v in source.properties.items():
        if v is not None and k not in target.properties:
            target.properties[k] = v


def _find_cross_type_match(
    name: str,
    etype: str,
    name_to_uuid: dict[str, str],
) -> tuple[str, str, str] | None:
    """Check if an entity with the same name but a cross-type exists.

    Returns (existing_uuid, canonical_type, existing_type) or None.
    """
    for pair, canonical in _CROSS_TYPE_MERGE.items():
        if etype.lower() not in pair:
            continue
        other = next(iter(pair - {etype.lower()}))
        other_key = f"{name.lower()}|{other}"
        if other_key in name_to_uuid:
            return name_to_uuid[other_key], canonical, other
    return None


def _resolve_cross_type(
    entities: dict[str, OntologyEntity],
) -> tuple[dict[str, OntologyEntity], dict[str, str]]:
    """Merge entities that share the same name but differ in type where a
    canonical type exists (e.g. Location + Country → Country).

    Returns the deduplicated entity dict and a UUID remapping for links.
    """
    name_to_uuids: dict[str, list[str]] = {}
    for uuid_str, entity in entities.items():
        name_to_uuids.setdefault(entity.name.lower(), []).append(uuid_str)

    remap: dict[str, str] = {}

    for _name, uuids in name_to_uuids.items():
        if len(uuids) < 2:
            continue

        types_present = {entities[u].type.lower() for u in uuids}
        canonical = None
        for pair, target in _CROSS_TYPE_MERGE.items():
            if types_present == pair:
                canonical = target
                break

        if canonical is None:
            continue

        canonical_uuid = None
        to_remove = []
        for u in uuids:
            if entities[u].type.lower() == canonical:
                canonical_uuid = u
            else:
                to_remove.append(u)

        if canonical_uuid is None:
            continue

        canonical_entity = entities[canonical_uuid]
        for old_uuid in to_remove:
            old_entity = entities[old_uuid]
            _merge_mentions(canonical_entity, old_entity)
            _merge_properties(canonical_entity, old_entity)
            canonical_entity.updated_at = datetime.utcnow()
            remap[old_uuid] = canonical_uuid
            del entities[old_uuid]

    return entities, remap


def _merge_same_uuid(
    existing: OntologyEntity,
    new_entity: OntologyEntity,
) -> None:
    """Merge a new entity into an existing one that shares the same UUID."""
    existing.mentions.extend(new_entity.mentions)
    for k, v in new_entity.properties.items():
        if v is not None:
            existing.properties[k] = v
    existing.updated_at = datetime.utcnow()


def _merge_same_name_type(
    existing: OntologyEntity,
    new_entity: OntologyEntity,
    new_uuid: str,
    uuid_remap: dict[str, str],
) -> None:
    """Merge new_entity into existing (same name+type). Record UUID remap."""
    _merge_mentions(existing, new_entity)
    _merge_properties(existing, new_entity)
    existing.updated_at = datetime.utcnow()
    uuid_remap[new_uuid] = str(existing.uuid)


def _merge_cross_type(
    existing: OntologyEntity,
    new_entity: OntologyEntity,
    new_uuid: str,
    canonical_type: str,
    uuid_remap: dict[str, str],
    merged_entities: dict[str, OntologyEntity],
    name_to_uuid: dict[str, str],
    key: str,
) -> bool:
    """Merge across types (Location ↔ Country). Returns True if merged."""
    new_is_canonical = new_entity.type.lower() == canonical_type

    if new_is_canonical:
        _merge_mentions(new_entity, existing)
        _merge_properties(new_entity, existing)
        new_entity.updated_at = datetime.utcnow()
        merged_entities[new_uuid] = new_entity
        uuid_remap[str(existing.uuid)] = new_uuid
        name_to_uuid[key] = new_uuid
    else:
        _merge_mentions(existing, new_entity)
        _merge_properties(existing, new_entity)
        existing.updated_at = datetime.utcnow()
        uuid_remap[new_uuid] = str(existing.uuid)

    return True


def _deduplicate_entities_by_name(
    entities: dict[str, OntologyEntity],
    uuid_remap: dict[str, str],
) -> dict[str, OntologyEntity]:
    """Merge entities that share the same name regardless of type.

    First occurrence wins; subsequent duplicates are merged into it
    and their UUIDs are recorded in uuid_remap for link remapping.
    """
    name_to_uuid: dict[str, str] = {}
    to_remove: list[str] = []

    for uuid_str, entity in list(entities.items()):
        name = entity.name.lower()
        if name in name_to_uuid:
            existing_uuid = name_to_uuid[name]
            existing = entities[existing_uuid]
            _merge_mentions(existing, entity)
            _merge_properties(existing, entity)
            existing.updated_at = datetime.utcnow()
            uuid_remap[uuid_str] = existing_uuid
            to_remove.append(uuid_str)
        else:
            name_to_uuid[name] = uuid_str

    for uuid_str in to_remove:
        del entities[uuid_str]

    return entities


def merge_ontologies(
    current: SessionOntology,
    delta: SessionOntology,
    deduplicate_names: bool = False,
) -> SessionOntology:
    """Merge delta into current ontology.

    Strategy:
    1. Same UUID → merge mentions/properties
    2. Same name+type → deduplicate into existing
    3. Same name, cross-type (Location↔Country) → merge into canonical type
    4. Otherwise → add as new entity
    5. Post-merge pass: resolve any remaining cross-type duplicates
    6. (Optional) Post-merge pass: resolve any remaining same-name duplicates
    7. Merge links with UUID remapping
    """
    merged = SessionOntology()
    merged.entities = dict(current.entities)

    name_to_uuid: dict[str, str] = {}
    for uuid_str, entity in current.entities.items():
        key = f"{entity.name.lower()}|{entity.type}"
        name_to_uuid[key] = uuid_str

    uuid_remap: dict[str, str] = {}

    for uuid_str, new_entity in delta.entities.items():
        if uuid_str in current.entities:
            _merge_same_uuid(current.entities[uuid_str], new_entity)
            merged.entities[uuid_str] = current.entities[uuid_str]
            continue

        key = f"{new_entity.name.lower()}|{new_entity.type}"

        if key in name_to_uuid:
            existing = merged.entities[name_to_uuid[key]]
            _merge_same_name_type(existing, new_entity, uuid_str, uuid_remap)
            continue

        cross = _find_cross_type_match(new_entity.name, new_entity.type, name_to_uuid)
        if cross is not None:
            existing_uuid, canonical_type, _ = cross
            existing = merged.entities[existing_uuid]
            _merge_cross_type(
                existing,
                new_entity,
                uuid_str,
                canonical_type,
                uuid_remap,
                merged.entities,
                name_to_uuid,
                key,
            )
            continue

        merged.entities[uuid_str] = new_entity
        name_to_uuid[key] = uuid_str

    merged.entities, post_remap = _resolve_cross_type(merged.entities)
    uuid_remap.update(post_remap)

    if deduplicate_names:
        merged.entities = _deduplicate_entities_by_name(merged.entities, uuid_remap)

    merged.links = dict(current.links)
    _merge_links(merged, delta, uuid_remap)

    return merged


def _merge_links(
    merged: SessionOntology,
    delta: SessionOntology,
    uuid_remap: dict[str, str],
) -> None:
    """Merge delta links into merged ontology, remapping UUIDs as needed."""
    for uuid_str, new_link in delta.links.items():
        if uuid_str in merged.links:
            continue

        source_uuid = uuid_remap.get(
            str(new_link.source_uuid), str(new_link.source_uuid)
        )
        target_uuid = uuid_remap.get(
            str(new_link.target_uuid), str(new_link.target_uuid)
        )

        merged.links[uuid_str] = OntologyLink(
            uuid=new_link.uuid,
            source_uuid=source_uuid,
            target_uuid=target_uuid,
            type=new_link.type,
            properties=new_link.properties,
            mentions=new_link.mentions,
            created_at=new_link.created_at,
            updated_at=new_link.updated_at,
        )

    for link in merged.links.values():
        source_str = str(link.source_uuid)
        target_str = str(link.target_uuid)
        if source_str in uuid_remap or target_str in uuid_remap:
            link.source_uuid = uuid_remap.get(source_str, source_str)
            link.target_uuid = uuid_remap.get(target_str, target_str)


def merge_entity(existing: OntologyEntity, new: OntologyEntity) -> OntologyEntity:
    """Merge two entities with same UUID.

    - Accumulates mentions
    - Updates properties (new values take precedence)
    - Updates timestamp
    """
    existing.mentions.extend(new.mentions)
    for k, v in new.properties.items():
        if v is not None:
            existing.properties[k] = v
    existing.updated_at = datetime.utcnow()
    return existing
