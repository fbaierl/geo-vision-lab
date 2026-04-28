"""
Tests for Ontology Merge Logic

Tests the merge_ontologies function with various scenarios:
- UUID-based merging
- Name-based deduplication
- Link remapping
- Mention deduplication
"""

from app.models.ontology import SessionOntology, OntologyEntity, OntologyLink, Mention
from app.services.ontology.merge import merge_ontologies


class TestOntologyMerge:
    """Test suite for ontology merging functionality."""

    def create_entity(
        self,
        name: str,
        type: str,
        uuid: str = None,
        mentions: list = None,
        properties: dict = None,
    ):
        """Helper to create test entities."""
        from uuid import uuid4

        entity = OntologyEntity(
            uuid=uuid4() if uuid is None else uuid,
            name=name,
            type=type,
            properties=properties or {},
            mentions=mentions or [],
            created_by="test",
        )
        if uuid:
            entity.uuid = uuid
        return entity

    def create_link(
        self, source_uuid: str, target_uuid: str, type: str, uuid: str = None
    ):
        """Helper to create test links."""
        from uuid import uuid4

        link = OntologyLink(
            uuid=uuid4() if uuid is None else uuid,
            source_uuid=source_uuid,
            target_uuid=target_uuid,
            type=type,
            mentions=[],
            created_by="test",
        )
        if uuid:
            link.uuid = uuid
        return link

    def create_mention(self, text: str):
        """Helper to create test mentions."""
        return Mention(source_text=text, confidence=1.0)

    def test_merge_by_uuid(self):
        """Test that entities with matching UUIDs are merged."""
        # Arrange
        uuid = "550e8400-e29b-41d4-a716-446655440000"

        current = SessionOntology()
        entity1 = self.create_entity("Germany", "Location", uuid=uuid)
        entity1.mentions = [self.create_mention("Germany is in Europe")]
        current.entities[uuid] = entity1

        delta = SessionOntology()
        entity2 = self.create_entity("Germany", "Location", uuid=uuid)
        entity2.mentions = [self.create_mention("Germany has 83M people")]
        delta.entities[uuid] = entity2

        # Act
        merged = merge_ontologies(current, delta)

        # Assert
        assert len(merged.entities) == 1
        assert uuid in merged.entities
        assert len(merged.entities[uuid].mentions) == 2

    def test_deduplicate_by_name_and_type(self):
        """Test that entities with same name+type are deduplicated (not duplicated)."""
        # Arrange - Simulating the German Chancellors scenario
        uuid1 = "cc8498de-3f30-482c-82ad-00f0cb3490d1"
        uuid2 = "75144852-67c3-44d7-9c4d-a137674df771"

        current = SessionOntology()
        olaf1 = self.create_entity("Olaf Scholz", "Person", uuid=uuid1)
        olaf1.mentions = [
            self.create_mention("The current Chancellor of Germany is Olaf Scholz")
        ]
        current.entities[uuid1] = olaf1

        delta = SessionOntology()
        olaf2 = self.create_entity("Olaf Scholz", "Person", uuid=uuid2)
        olaf2.mentions = [
            self.create_mention(
                "The previous Chancellor of Germany before Olaf Scholz was Angela Merkel"
            )
        ]
        delta.entities[uuid2] = olaf2

        # Act
        merged = merge_ontologies(current, delta)

        # Assert - Should have only 1 Olaf Scholz, not 2
        olaf_entities = [
            e
            for e in merged.entities.values()
            if e.name == "Olaf Scholz" and e.type == "Person"
        ]
        assert len(olaf_entities) == 1, (
            f"Expected 1 Olaf Scholz, got {len(olaf_entities)}"
        )

        # Should have both mentions
        assert len(olaf_entities[0].mentions) == 2

    def test_deduplicate_multiple_entities(self):
        """Test deduplication with multiple duplicate entities (Germany example)."""
        # Arrange
        uuid_germany_1 = "feaec317-051c-46ea-b2a6-5b5d7f402724"
        uuid_germany_2 = "049de5f6-8fca-44fe-81b6-f1cfd09cd784"
        uuid_germany_3 = "f866de32-2cb6-4b19-917e-0113d89a538e"

        current = SessionOntology()
        germany1 = self.create_entity("Germany", "Location", uuid=uuid_germany_1)
        germany1.mentions = [
            self.create_mention("The current Chancellor of Germany is Olaf Scholz")
        ]
        germany1.properties = {"lat": 51.16, "lon": 10.45}
        current.entities[uuid_germany_1] = germany1

        delta = SessionOntology()
        germany2 = self.create_entity("Germany", "Location", uuid=uuid_germany_2)
        germany2.mentions = [
            self.create_mention(
                "The previous Chancellor of Germany before Olaf Scholz was Angela Merkel"
            )
        ]
        delta.entities[uuid_germany_2] = germany2

        germany3 = self.create_entity("Germany", "Location", uuid=uuid_germany_3)
        germany3.mentions = [
            self.create_mention(
                "The previous Chancellor of Germany before Angela Merkel was Gerhard Schröder."
            )
        ]
        delta.entities[uuid_germany_3] = germany3

        # Act
        merged = merge_ontologies(current, delta)

        # Assert - Should have only 1 Germany
        germany_entities = [
            e
            for e in merged.entities.values()
            if e.name == "Germany" and e.type == "Location"
        ]
        assert len(germany_entities) == 1, (
            f"Expected 1 Germany, got {len(germany_entities)}"
        )

        # Should have all 3 mentions
        assert len(germany_entities[0].mentions) == 3

        # Should preserve properties
        assert germany_entities[0].properties.get("lat") == 51.16

    def test_link_remap_after_deduplication(self):
        """Test that links are remapped when entities are deduplicated."""
        # Arrange
        olaf_uuid_1 = "cc8498de-3f30-482c-82ad-00f0cb3490d1"
        olaf_uuid_2 = "75144852-67c3-44d7-9c4d-a137674df771"
        germany_uuid_1 = "feaec317-051c-46ea-b2a6-5b5d7f402724"
        germany_uuid_2 = "049de5f6-8fca-44fe-81b6-f1cfd09cd784"

        current = SessionOntology()
        olaf1 = self.create_entity("Olaf Scholz", "Person", uuid=olaf_uuid_1)
        germany1 = self.create_entity("Germany", "Location", uuid=germany_uuid_1)
        current.entities[olaf_uuid_1] = olaf1
        current.entities[germany_uuid_1] = germany1

        link1 = self.create_link(olaf_uuid_1, germany_uuid_1, "CHANCELLOR_OF")
        current.links[str(link1.uuid)] = link1

        delta = SessionOntology()
        olaf2 = self.create_entity("Olaf Scholz", "Person", uuid=olaf_uuid_2)
        germany2 = self.create_entity("Germany", "Location", uuid=germany_uuid_2)
        delta.entities[olaf_uuid_2] = olaf2
        delta.entities[germany_uuid_2] = germany2

        link2 = self.create_link(olaf_uuid_2, germany_uuid_2, "CHANCELLOR_OF")
        delta.links[str(link2.uuid)] = link2

        # Act
        merged = merge_ontologies(current, delta)

        # Assert - Links should point to deduplicated entities
        olaf_entities = [e for e in merged.entities.values() if e.name == "Olaf Scholz"]
        germany_entities = [e for e in merged.entities.values() if e.name == "Germany"]

        assert len(olaf_entities) == 1
        assert len(germany_entities) == 1

        olaf_uuid = str(olaf_entities[0].uuid)
        germany_uuid = str(germany_entities[0].uuid)

        # All links should reference the consolidated UUIDs
        for link in merged.links.values():
            assert str(link.source_uuid) == olaf_uuid, (
                f"Link source {link.source_uuid} should be {olaf_uuid}"
            )
            assert str(link.target_uuid) == germany_uuid, (
                f"Link target {link.target_uuid} should be {germany_uuid}"
            )

    def test_mention_deduplication(self):
        """Test that duplicate mentions are not added when deduplicating by name."""
        # Arrange - Using different UUIDs to trigger name-based deduplication
        uuid1 = "550e8400-e29b-41d4-a716-446655440000"
        uuid2 = "550e8400-e29b-41d4-a716-446655440001"

        current = SessionOntology()
        entity1 = self.create_entity("Angela Merkel", "Person", uuid=uuid1)
        mention1 = self.create_mention("Angela Merkel was Chancellor")
        entity1.mentions = [mention1]
        current.entities[uuid1] = entity1

        delta = SessionOntology()
        entity2 = self.create_entity("Angela Merkel", "Person", uuid=uuid2)
        mention1_duplicate = self.create_mention(
            "Angela Merkel was Chancellor"
        )  # Same text
        mention2_new = self.create_mention("She served from 2005 to 2021")
        entity2.mentions = [mention1_duplicate, mention2_new]
        delta.entities[uuid2] = entity2

        # Act
        merged = merge_ontologies(current, delta)

        # Assert - Should have 2 unique mentions (duplicate filtered), not 3
        angela_entities = [
            e for e in merged.entities.values() if e.name == "Angela Merkel"
        ]
        assert len(angela_entities) == 1
        assert len(angela_entities[0].mentions) == 2

    def test_property_merge(self):
        """Test that properties are merged correctly."""
        # Arrange
        uuid = "550e8400-e29b-41d4-a716-446655440000"

        current = SessionOntology()
        entity1 = self.create_entity("Berlin", "Location", uuid=uuid)
        entity1.properties = {"lat": 52.52, "country": "Germany"}
        current.entities[uuid] = entity1

        delta = SessionOntology()
        entity2 = self.create_entity("Berlin", "Location", uuid=uuid)
        entity2.properties = {"lon": 13.40, "population": 3645000}
        delta.entities[uuid] = entity2

        # Act
        merged = merge_ontologies(current, delta)

        # Assert - Should have all properties
        assert merged.entities[uuid].properties["lat"] == 52.52
        assert merged.entities[uuid].properties["lon"] == 13.40
        assert merged.entities[uuid].properties["country"] == "Germany"
        assert merged.entities[uuid].properties["population"] == 3645000

    def test_different_types_not_deduplicated(self):
        """Test that entities with same name but different types are NOT deduplicated."""
        # Arrange - "Georgia" can be a Location (country) or Person (name)
        uuid_location = "550e8400-e29b-41d4-a716-446655440001"
        uuid_person = "550e8400-e29b-41d4-a716-446655440002"

        current = SessionOntology()
        georgia_loc = self.create_entity("Georgia", "Location", uuid=uuid_location)
        current.entities[uuid_location] = georgia_loc

        delta = SessionOntology()
        georgia_person = self.create_entity("Georgia", "Person", uuid=uuid_person)
        delta.entities[uuid_person] = georgia_person

        # Act
        merged = merge_ontologies(current, delta)

        # Assert - Both should exist (homonyms)
        georgia_entities = [e for e in merged.entities.values() if e.name == "Georgia"]
        assert len(georgia_entities) == 2

        types = {e.type for e in georgia_entities}
        assert "Location" in types
        assert "Person" in types

    def test_empty_delta(self):
        """Test merging with empty delta."""
        # Arrange
        current = SessionOntology()
        entity = self.create_entity("Test", "Concept")
        current.entities[str(entity.uuid)] = entity

        delta = SessionOntology()

        # Act
        merged = merge_ontologies(current, delta)

        # Assert
        assert len(merged.entities) == 1
        assert len(merged.links) == 0

    def test_empty_current(self):
        """Test merging into empty current ontology."""
        # Arrange
        current = SessionOntology()

        delta = SessionOntology()
        entity = self.create_entity("Test", "Concept")
        delta.entities[str(entity.uuid)] = entity

        # Act
        merged = merge_ontologies(current, delta)

        # Assert
        assert len(merged.entities) == 1

    def test_case_insensitive_name_matching(self):
        """Test that name matching is case-insensitive."""
        # Arrange
        uuid1 = "550e8400-e29b-41d4-a716-446655440001"
        uuid2 = "550e8400-e29b-41d4-a716-446655440002"

        current = SessionOntology()
        entity1 = self.create_entity("germany", "Location", uuid=uuid1)
        current.entities[uuid1] = entity1

        delta = SessionOntology()
        entity2 = self.create_entity("GERMANY", "Location", uuid=uuid2)
        delta.entities[uuid2] = entity2

        # Act
        merged = merge_ontologies(current, delta)

        # Assert - Should be deduplicated despite case difference
        germany_entities = [
            e for e in merged.entities.values() if e.name.lower() == "germany"
        ]
        assert len(germany_entities) == 1

    # ═══════════════════════════════════════════════════════════════════
    # deduplicate_names=True tests (new in this session)
    # ═══════════════════════════════════════════════════════════════════

    def test_different_types_not_deduplicated_by_default(self):
        """By default, same name + different types = keep both (homonyms)."""
        uuid_location = "550e8400-e29b-41d4-a716-446655440001"
        uuid_person = "550e8400-e29b-41d4-a716-446655440002"

        current = SessionOntology()
        current.entities[uuid_location] = self.create_entity("Georgia", "Location", uuid=uuid_location)

        delta = SessionOntology()
        delta.entities[uuid_person] = self.create_entity("Georgia", "Person", uuid=uuid_person)

        # default: deduplicate_names=False
        merged = merge_ontologies(current, delta)

        georgia_entities = [e for e in merged.entities.values() if e.name == "Georgia"]
        assert len(georgia_entities) == 2
        assert {e.type for e in georgia_entities} == {"Location", "Person"}

    def test_deduplicate_names_merges_different_types(self):
        """With deduplicate_names=True, same name merges regardless of type."""
        uuid_location = "550e8400-e29b-41d4-a716-446655440001"
        uuid_org = "550e8400-e29b-41d4-a716-446655440002"

        current = SessionOntology()
        soviet_loc = self.create_entity("Soviet Union", "Location", uuid=uuid_location)
        soviet_loc.properties = {"lat": 44.56, "lon": 27.35}
        soviet_loc.mentions = [self.create_mention("He ruled the Soviet Union")]
        current.entities[uuid_location] = soviet_loc

        delta = SessionOntology()
        soviet_org = self.create_entity("Soviet Union", "Organization", uuid=uuid_org)
        soviet_org.mentions = [self.create_mention("He served the Soviet Union")]
        delta.entities[uuid_org] = soviet_org

        merged = merge_ontologies(current, delta, deduplicate_names=True)

        soviet_entities = [e for e in merged.entities.values() if e.name == "Soviet Union"]
        assert len(soviet_entities) == 1, f"Expected 1 Soviet Union, got {len(soviet_entities)}"
        # First occurrence (Location) wins
        assert soviet_entities[0].type == "Location"
        # Mentions from both are accumulated
        assert len(soviet_entities[0].mentions) == 2
        # Properties from first are preserved
        assert soviet_entities[0].properties.get("lat") == 44.56

    def test_deduplicate_names_link_remap(self):
        """Links pointing to a deduplicated entity are remapped."""
        uuid_loc = "550e8400-e29b-41d4-a716-446655440001"
        uuid_org = "550e8400-e29b-41d4-a716-446655440002"
        uuid_person = "550e8400-e29b-41d4-a716-446655440003"

        current = SessionOntology()
        current.entities[uuid_loc] = self.create_entity("Soviet Union", "Location", uuid=uuid_loc)
        current.entities[uuid_person] = self.create_entity("Joseph Stalin", "Person", uuid=uuid_person)

        delta = SessionOntology()
        delta.entities[uuid_org] = self.create_entity("Soviet Union", "Organization", uuid=uuid_org)

        link = self.create_link(uuid_person, uuid_org, "RULED")
        delta.links[str(link.uuid)] = link

        merged = merge_ontologies(current, delta, deduplicate_names=True)

        assert len(merged.entities) == 2
        soviet = next(e for e in merged.entities.values() if e.name == "Soviet Union")
        assert str(soviet.uuid) == uuid_loc

        assert len(merged.links) == 1
        link = next(iter(merged.links.values()))
        assert str(link.target_uuid) == uuid_loc

    def test_deduplicate_names_preserves_case(self):
        """Name deduplication is case-insensitive but keeps the first casing."""
        uuid1 = "550e8400-e29b-41d4-a716-446655440001"
        uuid2 = "550e8400-e29b-41d4-a716-446655440002"

        current = SessionOntology()
        current.entities[uuid1] = self.create_entity("soviet union", "Location", uuid=uuid1)

        delta = SessionOntology()
        delta.entities[uuid2] = self.create_entity("Soviet Union", "Organization", uuid=uuid2)

        merged = merge_ontologies(current, delta, deduplicate_names=True)

        soviet_entities = [e for e in merged.entities.values() if e.name.lower() == "soviet union"]
        assert len(soviet_entities) == 1
        assert soviet_entities[0].name == "soviet union"

    def test_deduplicate_names_only_affects_same_name(self):
        """Entities with different names are never merged."""
        uuid1 = "550e8400-e29b-41d4-a716-446655440001"
        uuid2 = "550e8400-e29b-41d4-a716-446655440002"

        current = SessionOntology()
        current.entities[uuid1] = self.create_entity("Stalin", "Person", uuid=uuid1)

        delta = SessionOntology()
        delta.entities[uuid2] = self.create_entity("Khrushchev", "Person", uuid=uuid2)

        merged = merge_ontologies(current, delta, deduplicate_names=True)

        assert len(merged.entities) == 2
