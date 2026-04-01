"""
Tests for OntologyService (Neo4j-backed)

Tests the OntologyService layer that wraps GraphStoreService.
"""

from unittest.mock import Mock
from uuid import UUID, uuid4

from app.services.ontology.service import OntologyService
from app.models.ontology import OntologyEntity, OntologyLink, SessionOntology


class TestOntologyService:
    """Test suite for Neo4j-backed OntologyService."""

    def create_entity(self, name, type, uuid_str=None, mentions=None, properties=None):
        """Helper to create test entities."""
        entity = OntologyEntity(
            uuid=UUID(uuid_str) if uuid_str else uuid4(),
            name=name,
            type=type,
            properties=properties or {},
            mentions=mentions or [],
            created_by="test",
        )
        return entity

    def create_link(self, source_uuid, target_uuid, type, uuid_str=None):
        """Helper to create test links."""
        link = OntologyLink(
            uuid=UUID(uuid_str) if uuid_str else uuid4(),
            source_uuid=UUID(source_uuid),
            target_uuid=UUID(target_uuid),
            type=type,
            mentions=[],
        )
        return link

    def test_load_ontology_empty(self):
        """Test loading ontology when no data exists."""
        mock_graph_store = Mock()
        mock_graph_store.get_all_entities.return_value = []
        mock_graph_store.get_all_links.return_value = []

        service = OntologyService(mock_graph_store)
        ontology = service.load_ontology("thread-1")

        assert len(ontology.entities) == 0
        assert len(ontology.links) == 0
        mock_graph_store.get_all_entities.assert_called_once_with(thread_id="thread-1")

    def test_load_ontology_with_data(self):
        """Test loading ontology with existing data."""
        mock_graph_store = Mock()
        mock_graph_store.get_all_entities.return_value = [
            {
                "e": {
                    "uuid": "550e8400-e29b-41d4-a716-446655440000",
                    "name": "Germany",
                    "type": "Country",
                    "properties": '{"lat": 51.16}',
                    "mentions": "[]",
                    "created_at": "2026-01-01T00:00:00",
                    "updated_at": "2026-01-01T00:00:00",
                    "created_by": "test",
                }
            }
        ]
        mock_graph_store.get_all_links.return_value = []

        service = OntologyService(mock_graph_store)
        ontology = service.load_ontology("thread-1")

        assert len(ontology.entities) == 1
        assert "550e8400-e29b-41d4-a716-446655440000" in ontology.entities
        assert (
            ontology.entities["550e8400-e29b-41d4-a716-446655440000"].name == "Germany"
        )

    def test_save_ontology(self):
        """Test saving ontology to Neo4j."""
        mock_graph_store = Mock()

        service = OntologyService(mock_graph_store)
        ontology = SessionOntology()
        entity = self.create_entity("Germany", "Country")
        ontology.entities[str(entity.uuid)] = entity

        link = self.create_link(
            str(entity.uuid),
            "550e8400-e29b-41d4-a716-446655440001",
            "LOCATED_IN",
        )
        ontology.links[str(link.uuid)] = link

        service.save_ontology("thread-1", ontology)

        assert mock_graph_store.create_entity.call_count == 1
        assert mock_graph_store.create_link.call_count == 1

    def test_get_entity_by_uuid_found(self):
        """Test getting entity by UUID when it exists."""
        mock_graph_store = Mock()
        mock_graph_store.get_entity_by_uuid.return_value = {
            "uuid": "550e8400-e29b-41d4-a716-446655440000",
            "name": "Germany",
            "type": "Country",
            "properties": "{}",
            "mentions": "[]",
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
            "created_by": "test",
        }

        service = OntologyService(mock_graph_store)
        entity_uuid = UUID("550e8400-e29b-41d4-a716-446655440000")
        entity = service.get_entity_by_uuid("thread-1", entity_uuid)

        assert entity is not None
        assert entity.name == "Germany"

    def test_get_entity_by_uuid_not_found(self):
        """Test getting entity by UUID when it doesn't exist."""
        mock_graph_store = Mock()
        mock_graph_store.get_entity_by_uuid.return_value = None

        service = OntologyService(mock_graph_store)
        entity_uuid = UUID("550e8400-e29b-41d4-a716-446655440000")
        entity = service.get_entity_by_uuid("thread-1", entity_uuid)

        assert entity is None

    def test_get_entity_by_name(self):
        """Test getting entities by name."""
        mock_graph_store = Mock()
        mock_graph_store.get_entities_by_name.return_value = [
            {
                "uuid": "550e8400-e29b-41d4-a716-446655440000",
                "name": "Georgia",
                "type": "Country",
                "properties": "{}",
                "mentions": "[]",
                "created_at": "2026-01-01T00:00:00",
                "updated_at": "2026-01-01T00:00:00",
                "created_by": "test",
            },
            {
                "uuid": "550e8400-e29b-41d4-a716-446655440001",
                "name": "Georgia",
                "type": "Location",
                "properties": "{}",
                "mentions": "[]",
                "created_at": "2026-01-01T00:00:00",
                "updated_at": "2026-01-01T00:00:00",
                "created_by": "test",
            },
        ]

        service = OntologyService(mock_graph_store)
        entities = service.get_entity_by_name("thread-1", "Georgia")

        assert len(entities) == 2

    def test_get_neighbors(self):
        """Test getting neighbors of an entity."""
        mock_graph_store = Mock()
        mock_graph_store.get_neighbors.return_value = [
            {
                "uuid": "550e8400-e29b-41d4-a716-446655440001",
                "name": "France",
                "type": "Country",
                "properties": "{}",
                "mentions": "[]",
                "created_at": "2026-01-01T00:00:00",
                "updated_at": "2026-01-01T00:00:00",
                "created_by": "test",
            }
        ]

        service = OntologyService(mock_graph_store)
        entity_uuid = UUID("550e8400-e29b-41d4-a716-446655440000")
        neighbors = service.get_neighbors("thread-1", entity_uuid, hops=2)

        assert len(neighbors) == 1
        assert neighbors[0].name == "France"

    def test_get_links_for_entity(self):
        """Test getting links for an entity."""
        mock_graph_store = Mock()
        mock_graph_store.get_links_for_entity.return_value = [
            {
                "r": {
                    "uuid": "a1a1a1a1-a1a1-a1a1-a1a1-a1a1a1a1a1a1",
                    "type": "ALLIES_WITH",
                    "properties": "{}",
                    "mentions": "[]",
                    "created_at": "2026-01-01T00:00:00",
                    "updated_at": "2026-01-01T00:00:00",
                },
                "other": {"uuid": "550e8400-e29b-41d4-a716-446655440001"},
                "direction": "OUTGOING",
            }
        ]

        service = OntologyService(mock_graph_store)
        entity_uuid = UUID("550e8400-e29b-41d4-a716-446655440000")
        links = service.get_links_for_entity("thread-1", entity_uuid)

        assert len(links) == 1

    def test_get_entity_graph(self):
        """Test getting subgraph for an entity."""
        mock_graph_store = Mock()
        mock_graph_store.get_subgraph.return_value = {
            "entities": [
                {
                    "uuid": "550e8400-e29b-41d4-a716-446655440000",
                    "name": "Germany",
                    "type": "Country",
                    "properties": "{}",
                    "mentions": "[]",
                    "created_at": "2026-01-01T00:00:00",
                    "updated_at": "2026-01-01T00:00:00",
                    "created_by": "test",
                },
                {
                    "uuid": "550e8400-e29b-41d4-a716-446655440001",
                    "name": "France",
                    "type": "Country",
                    "properties": "{}",
                    "mentions": "[]",
                    "created_at": "2026-01-01T00:00:00",
                    "updated_at": "2026-01-01T00:00:00",
                    "created_by": "test",
                },
            ],
            "links": [
                {
                    "r": {
                        "uuid": "a1a1a1a1-a1a1-a1a1-a1a1-a1a1a1a1a1a1",
                        "type": "ALLIES_WITH",
                        "properties": "{}",
                        "mentions": "[]",
                        "created_at": "2026-01-01T00:00:00",
                        "updated_at": "2026-01-01T00:00:00",
                    },
                    "other": {"uuid": "550e8400-e29b-41d4-a716-446655440001"},
                    "direction": "OUTGOING",
                }
            ],
        }

        service = OntologyService(mock_graph_store)
        entity_uuid = UUID("550e8400-e29b-41d4-a716-446655440000")
        subgraph = service.get_entity_graph("thread-1", entity_uuid, hops=2)

        assert len(subgraph.entities) == 2
        assert len(subgraph.links) == 1

    def test_get_context_for_query(self):
        """Test getting context for RAG query."""
        mock_graph_store = Mock()
        mock_graph_store.get_context_for_query.return_value = (
            "KNOWN ONTOLOGY CONTEXT:\n- France (Country)"
        )

        service = OntologyService(mock_graph_store)
        context = service.get_context_for_query(["Germany"], thread_id="thread-1")

        assert "KNOWN ONTOLOGY CONTEXT" in context
        mock_graph_store.get_context_for_query.assert_called_once_with(
            ["Germany"], thread_id="thread-1"
        )

    def test_get_stats(self):
        """Test getting ontology statistics."""
        mock_graph_store = Mock()
        mock_graph_store.get_stats.return_value = {
            "entity_count": 10,
            "link_count": 15,
        }

        service = OntologyService(mock_graph_store)
        stats = service.get_stats(thread_id="thread-1")

        assert stats["entity_count"] == 10
        assert stats["link_count"] == 15
