"""
Tests for entity deduplication: merging same-name Location and Country entities.

Issue #80: Countries were created as both Location and Country entities.
The merge logic should detect same-name Location↔Country pairs and merge
them into a single Country entity with combined properties.
"""

from app.services.ontology.merge import merge_ontologies
from app.models.ontology import SessionOntology, OntologyEntity, OntologyLink, Mention


def _make_entity(name, etype, props=None, mentions=None, uuid_str=None):
    from uuid import UUID, uuid4

    if uuid_str:
        try:
            u = UUID(uuid_str)
        except ValueError:
            u = uuid4()
    else:
        u = uuid4()
    return OntologyEntity(
        uuid=u,
        name=name,
        type=etype,
        properties=props or {},
        mentions=mentions or [],
    )


def _make_link(source_uuid, target_uuid, ltype, uuid_str=None):
    from uuid import UUID, uuid4

    try:
        link_uuid = UUID(uuid_str) if uuid_str else uuid4()
    except ValueError:
        link_uuid = uuid4()
    return OntologyLink(
        uuid=link_uuid,
        source_uuid=source_uuid,
        target_uuid=target_uuid,
        type=ltype,
    )


# ---------------------------------------------------------------------------
# Test: merge Location + Country with same name → single Country
# ---------------------------------------------------------------------------


def test_merge_location_and_country():
    """When a country exists as both Location and Country, they should merge
    into a single Country entity with combined properties."""
    loc_uuid = "4579881c-c75f-4b0e-9054-884c148275d3"
    country_uuid = "ac21f410-cfea-4b85-994d-7ef754578e3a"

    current = SessionOntology()
    current.entities[loc_uuid] = _make_entity(
        "Germany",
        "Location",
        props={"lat": 51.16, "lon": 10.45},
        uuid_str=loc_uuid,
    )

    delta = SessionOntology()
    delta.entities[country_uuid] = _make_entity(
        "Germany",
        "Country",
        mentions=[Mention(source_text="Germany fought against the Allies")],
        uuid_str=country_uuid,
    )
    delta.links["link1"] = _make_link(
        source_uuid=country_uuid,
        target_uuid="6e7bb5e8-c70c-4402-93e2-b275da686c5e",
        ltype="FIGHTS_AGAINST",
        uuid_str="link1",
    )

    merged = merge_ontologies(current, delta)

    # Only one Germany entity should exist
    germany_entities = [e for e in merged.entities.values() if e.name == "Germany"]
    assert len(germany_entities) == 1

    germany = germany_entities[0]
    assert germany.type == "Country"
    assert germany.properties.get("lat") == 51.16
    assert germany.properties.get("lon") == 10.45
    assert len(germany.mentions) == 1

    # Link should point to the surviving Country UUID
    link = merged.links["link1"]
    assert str(link.source_uuid) == country_uuid


# ---------------------------------------------------------------------------
# Test: Country type priority over Location
# ---------------------------------------------------------------------------


def test_country_type_priority():
    """Merged entities should use Country type, not Location."""
    current = SessionOntology()
    current.entities["loc-uuid"] = _make_entity(
        "France",
        "Location",
        props={"lat": 46.6, "lon": 2.2},
    )

    delta = SessionOntology()
    delta.entities["country-uuid"] = _make_entity(
        "France",
        "Country",
    )

    merged = merge_ontologies(current, delta)

    france = [e for e in merged.entities.values() if e.name == "France"][0]
    assert france.type == "Country"


# ---------------------------------------------------------------------------
# Test: entity count after merge (15 unique entities)
# ---------------------------------------------------------------------------


def test_entity_count_after_merge():
    """After merging all Location+Country duplicates, expect 15 entities."""
    data = {
        "entities": [
            {
                "uuid": "6e7bb5e8-c70c-4402-93e2-b275da686c5e",
                "name": "Allies",
                "type": "Concept",
                "properties": {},
                "mentions": [
                    {
                        "source_text": "Allies mentioned",
                        "extracted_at": "2026-03-31T17:13:18.443954",
                        "confidence": 1,
                        "thread_id": "default",
                    }
                ],
                "created_at": "2026-03-31T17:13:18.443968",
                "updated_at": "2026-03-31T17:13:18.443968",
                "created_by": "llm_extractor",
            },
            {
                "uuid": "9911282e-c9b8-471d-b81f-5445fc81e6d8",
                "name": "Axis powers",
                "type": "Concept",
                "properties": {},
                "mentions": [
                    {
                        "source_text": "Axis mentioned",
                        "extracted_at": "2026-03-31T17:13:18.444022",
                        "confidence": 1,
                        "thread_id": "default",
                    }
                ],
                "created_at": "2026-03-31T17:13:18.444025",
                "updated_at": "2026-03-31T17:13:18.444025",
                "created_by": "llm_extractor",
            },
            {
                "uuid": "48bb85da-1565-44ce-bb9c-847590d82a2f",
                "name": "United States",
                "type": "Location",
                "properties": {"lat": 39.78, "lon": -100.44},
                "mentions": [
                    {
                        "source_text": "US location",
                        "extracted_at": "2026-03-31T17:13:18.797860",
                        "confidence": 1,
                        "thread_id": "default",
                    }
                ],
                "created_at": "2026-03-31T17:13:18.797874",
                "updated_at": "2026-03-31T17:13:18.797875",
                "created_by": "llm_extractor",
            },
            {
                "uuid": "b099cd76-05f0-49bc-b026-5882d12b475e",
                "name": "United Kingdom",
                "type": "Location",
                "properties": {"lat": 54.70, "lon": -3.27},
                "mentions": [
                    {
                        "source_text": "UK location",
                        "extracted_at": "2026-03-31T17:13:19.106456",
                        "confidence": 1,
                        "thread_id": "default",
                    }
                ],
                "created_at": "2026-03-31T17:13:19.106471",
                "updated_at": "2026-03-31T17:13:19.106472",
                "created_by": "llm_extractor",
            },
            {
                "uuid": "485f9452-e195-4776-ae66-b8a48ee857e2",
                "name": "Soviet Union",
                "type": "Location",
                "properties": {"lat": 44.56, "lon": 27.35},
                "mentions": [
                    {
                        "source_text": "SU location",
                        "extracted_at": "2026-03-31T17:13:19.311662",
                        "confidence": 1,
                        "thread_id": "default",
                    }
                ],
                "created_at": "2026-03-31T17:13:19.311676",
                "updated_at": "2026-03-31T17:13:19.311676",
                "created_by": "llm_extractor",
            },
            {
                "uuid": "4579881c-c75f-4b0e-9054-884c148275d3",
                "name": "Germany",
                "type": "Location",
                "properties": {"lat": 51.16, "lon": 10.44},
                "mentions": [
                    {
                        "source_text": "Germany location",
                        "extracted_at": "2026-03-31T17:13:19.617425",
                        "confidence": 1,
                        "thread_id": "default",
                    }
                ],
                "created_at": "2026-03-31T17:13:19.617455",
                "updated_at": "2026-03-31T17:13:19.617455",
                "created_by": "llm_extractor",
            },
            {
                "uuid": "86d826cc-7afe-44da-ae5e-0b05b23812c3",
                "name": "Italy",
                "type": "Location",
                "properties": {"lat": 42.63, "lon": 12.67},
                "mentions": [
                    {
                        "source_text": "Italy location",
                        "extracted_at": "2026-03-31T17:13:19.757218",
                        "confidence": 1,
                        "thread_id": "default",
                    }
                ],
                "created_at": "2026-03-31T17:13:19.757249",
                "updated_at": "2026-03-31T17:13:19.757250",
                "created_by": "llm_extractor",
            },
            {
                "uuid": "c45fe14d-e517-48bc-a431-33f0a5665e52",
                "name": "Japan",
                "type": "Location",
                "properties": {"lat": 36.57, "lon": 139.23},
                "mentions": [
                    {
                        "source_text": "Japan location",
                        "extracted_at": "2026-03-31T17:13:20.334325",
                        "confidence": 1,
                        "thread_id": "default",
                    }
                ],
                "created_at": "2026-03-31T17:13:20.334339",
                "updated_at": "2026-03-31T17:13:20.334340",
                "created_by": "llm_extractor",
            },
            {
                "uuid": "c8522b2f-6248-43c9-856d-42d029882672",
                "name": "World War 2",
                "type": "Event",
                "properties": {},
                "mentions": [
                    {
                        "source_text": "WW2",
                        "extracted_at": "2026-03-31T17:13:20.334406",
                        "confidence": 1,
                        "thread_id": "default",
                    }
                ],
                "created_at": "2026-03-31T17:13:20.334409",
                "updated_at": "2026-03-31T17:13:20.334410",
                "created_by": "llm_extractor",
            },
            {
                "uuid": "c95b80ca-d048-40a6-acbc-78a452b67656",
                "name": "Japan",
                "type": "Country",
                "properties": {},
                "mentions": [
                    {
                        "source_text": "Japan fought",
                        "extracted_at": "2026-03-31T17:14:10.338692",
                        "confidence": 1,
                        "thread_id": "default",
                    }
                ],
                "created_at": "2026-03-31T17:14:10.338699",
                "updated_at": "2026-03-31T17:14:10.338700",
                "created_by": "llm_extractor",
            },
            {
                "uuid": "ac21f410-cfea-4b85-994d-7ef754578e3a",
                "name": "Germany",
                "type": "Country",
                "properties": {},
                "mentions": [
                    {
                        "source_text": "Germany fought",
                        "extracted_at": "2026-03-31T17:14:10.338739",
                        "confidence": 1,
                        "thread_id": "default",
                    }
                ],
                "created_at": "2026-03-31T17:14:10.338741",
                "updated_at": "2026-03-31T17:14:10.338741",
                "created_by": "llm_extractor",
            },
            {
                "uuid": "4baccee2-a9a3-4120-91cf-5f471e0aae0a",
                "name": "Italy",
                "type": "Country",
                "properties": {},
                "mentions": [
                    {
                        "source_text": "Italy fought",
                        "extracted_at": "2026-03-31T17:14:10.338773",
                        "confidence": 1,
                        "thread_id": "default",
                    }
                ],
                "created_at": "2026-03-31T17:14:10.338775",
                "updated_at": "2026-03-31T17:14:10.338775",
                "created_by": "llm_extractor",
            },
            {
                "uuid": "a11a818e-6470-4a68-8ee6-5ed6b5d307f7",
                "name": "United States",
                "type": "Country",
                "properties": {},
                "mentions": [
                    {
                        "source_text": "US fought",
                        "extracted_at": "2026-03-31T17:14:10.338804",
                        "confidence": 1,
                        "thread_id": "default",
                    }
                ],
                "created_at": "2026-03-31T17:14:10.338806",
                "updated_at": "2026-03-31T17:14:10.338806",
                "created_by": "llm_extractor",
            },
            {
                "uuid": "7e58efde-2301-4cb3-80e2-a26c8f1bf92f",
                "name": "United Kingdom",
                "type": "Country",
                "properties": {},
                "mentions": [
                    {
                        "source_text": "UK fought",
                        "extracted_at": "2026-03-31T17:14:10.338840",
                        "confidence": 1,
                        "thread_id": "default",
                    }
                ],
                "created_at": "2026-03-31T17:14:10.338843",
                "updated_at": "2026-03-31T17:14:10.338843",
                "created_by": "llm_extractor",
            },
            {
                "uuid": "cca971a2-acad-44ff-85e8-4080d4765768",
                "name": "Soviet Union",
                "type": "Country",
                "properties": {},
                "mentions": [
                    {
                        "source_text": "SU fought",
                        "extracted_at": "2026-03-31T17:14:10.338873",
                        "confidence": 1,
                        "thread_id": "default",
                    }
                ],
                "created_at": "2026-03-31T17:14:10.338875",
                "updated_at": "2026-03-31T17:14:10.338876",
                "created_by": "llm_extractor",
            },
            {
                "uuid": "bca098b5-d56e-40d9-a5ea-8a956177a05e",
                "name": "China",
                "type": "Country",
                "properties": {},
                "mentions": [
                    {
                        "source_text": "China fought",
                        "extracted_at": "2026-03-31T17:14:10.338909",
                        "confidence": 1,
                        "thread_id": "default",
                    }
                ],
                "created_at": "2026-03-31T17:14:10.338910",
                "updated_at": "2026-03-31T17:14:10.338911",
                "created_by": "llm_extractor",
            },
            {
                "uuid": "a74f2619-7e80-4f75-b9c9-bcee2f9edf32",
                "name": "France",
                "type": "Country",
                "properties": {},
                "mentions": [
                    {
                        "source_text": "France fought",
                        "extracted_at": "2026-03-31T17:14:10.338938",
                        "confidence": 1,
                        "thread_id": "default",
                    }
                ],
                "created_at": "2026-03-31T17:14:10.338940",
                "updated_at": "2026-03-31T17:14:10.338940",
                "created_by": "llm_extractor",
            },
            {
                "uuid": "e6eaee1c-7b7c-49c9-9dfc-20650ef41c0e",
                "name": "Poland",
                "type": "Country",
                "properties": {},
                "mentions": [
                    {
                        "source_text": "Poland fought",
                        "extracted_at": "2026-03-31T17:14:10.338985",
                        "confidence": 1,
                        "thread_id": "default",
                    }
                ],
                "created_at": "2026-03-31T17:14:10.338989",
                "updated_at": "2026-03-31T17:14:10.338989",
                "created_by": "llm_extractor",
            },
            {
                "uuid": "d89ff9cf-587b-4eaf-b7a1-a6f2c301c977",
                "name": "Australia",
                "type": "Country",
                "properties": {},
                "mentions": [
                    {
                        "source_text": "Australia fought",
                        "extracted_at": "2026-03-31T17:14:10.339044",
                        "confidence": 1,
                        "thread_id": "default",
                    }
                ],
                "created_at": "2026-03-31T17:14:10.339048",
                "updated_at": "2026-03-31T17:14:10.339048",
                "created_by": "llm_extractor",
            },
            {
                "uuid": "8f6a4f71-f720-40a2-90af-d6707b94e323",
                "name": "Greece",
                "type": "Country",
                "properties": {},
                "mentions": [
                    {
                        "source_text": "Greece fought",
                        "extracted_at": "2026-03-31T17:14:10.339100",
                        "confidence": 1,
                        "thread_id": "default",
                    }
                ],
                "created_at": "2026-03-31T17:14:10.339103",
                "updated_at": "2026-03-31T17:14:10.339104",
                "created_by": "llm_extractor",
            },
            {
                "uuid": "88e0cab9-8ca1-492e-a3dd-87efa092aedb",
                "name": "Ethiopia",
                "type": "Country",
                "properties": {},
                "mentions": [
                    {
                        "source_text": "Ethiopia fought",
                        "extracted_at": "2026-03-31T17:14:10.339156",
                        "confidence": 1,
                        "thread_id": "default",
                    }
                ],
                "created_at": "2026-03-31T17:14:10.339160",
                "updated_at": "2026-03-31T17:14:10.339160",
                "created_by": "llm_extractor",
            },
        ],
        "links": [],
    }

    # Build SessionOntology directly from data arrays
    ontology = SessionOntology()
    for e_data in data["entities"]:
        entity = OntologyEntity.model_validate(e_data)
        ontology.entities[str(entity.uuid)] = entity
    for l_data in data.get("links", []):
        link = OntologyLink.model_validate(l_data)
        ontology.links[str(link.uuid)] = link

    empty = SessionOntology()
    merged = merge_ontologies(empty, ontology)

    assert len(merged.entities) == 15

    # Verify merged countries have lat/lon
    for name in [
        "Germany",
        "Italy",
        "Japan",
        "United States",
        "United Kingdom",
        "Soviet Union",
    ]:
        ents = [e for e in merged.entities.values() if e.name == name]
        assert len(ents) == 1, f"Expected 1 entity for {name}, got {len(ents)}"
        assert ents[0].type == "Country"
        assert "lat" in ents[0].properties, f"{name} missing lat"
        assert "lon" in ents[0].properties, f"{name} missing lon"


# ---------------------------------------------------------------------------
# Test: link integrity after merge
# ---------------------------------------------------------------------------


def test_link_integrity_after_merge():
    """All links should reference valid entity UUIDs after deduplication."""
    loc_uuid = "4579881c-c75f-4b0e-9054-884c148275d3"
    country_uuid = "ac21f410-cfea-4b85-994d-7ef754578e3a"
    allies_uuid = "6e7bb5e8-c70c-4402-93e2-b275da686c5e"

    current = SessionOntology()
    current.entities[loc_uuid] = _make_entity("Germany", "Location", uuid_str=loc_uuid)
    current.entities[allies_uuid] = _make_entity(
        "Allies", "Concept", uuid_str=allies_uuid
    )
    current.links["l1"] = _make_link(
        loc_uuid,
        allies_uuid,
        "INCLUDED",
        uuid_str="11111111-1111-1111-1111-111111111111",
    )

    delta = SessionOntology()
    delta.entities[country_uuid] = _make_entity(
        "Germany", "Country", uuid_str=country_uuid
    )
    delta.links["l2"] = _make_link(
        country_uuid,
        allies_uuid,
        "FIGHTS_AGAINST",
        uuid_str="22222222-2222-2222-2222-222222222222",
    )

    merged = merge_ontologies(current, delta)

    all_entity_uuids = set(merged.entities.keys())
    for link in merged.links.values():
        assert str(link.source_uuid) in all_entity_uuids
        assert str(link.target_uuid) in all_entity_uuids


def test_post_merge_cross_type_dedup():
    """If current already has both Location and Country for same name,
    they should be merged even without a new delta."""
    loc_uuid = "11111111-1111-1111-1111-111111111111"
    country_uuid = "22222222-2222-2222-2222-222222222222"

    current = SessionOntology()
    current.entities[loc_uuid] = _make_entity(
        "Japan",
        "Location",
        props={"lat": 36.0, "lon": 138.0},
        uuid_str=loc_uuid,
    )
    current.entities[country_uuid] = _make_entity(
        "Japan",
        "Country",
        uuid_str=country_uuid,
    )

    delta = SessionOntology()
    delta.entities["33333333-3333-3333-3333-333333333333"] = _make_entity(
        "Tokyo", "Location", uuid_str="33333333-3333-3333-3333-333333333333"
    )

    merged = merge_ontologies(current, delta)

    japan_ents = [e for e in merged.entities.values() if e.name == "Japan"]
    assert len(japan_ents) == 1
    assert japan_ents[0].type == "Country"
    assert japan_ents[0].properties.get("lat") == 36.0
