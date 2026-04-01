"""
Tests for GraphStoreService

Tests Neo4j-backed graph operations using an in-memory Neo4j instance
via testcontainers.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch

from app.services.graph_store import GraphStoreService


class TestGraphStoreService:
    """Test suite for GraphStoreService with mocked Neo4j driver."""

    @pytest.fixture
    def mock_driver(self):
        """Create a mock Neo4j driver."""
        driver = Mock()
        mock_session = MagicMock()
        driver.session.return_value.__enter__ = Mock(return_value=mock_session)
        driver.session.return_value.__exit__ = Mock(return_value=False)
        return driver

    @pytest.fixture
    def graph_store(self, mock_driver):
        """Create a GraphStoreService with mocked driver."""
        with patch.object(GraphStoreService, "_ensure_constraints"):
            store = GraphStoreService(mock_driver)
        return store

    def test_type_to_label_valid(self, graph_store):
        """Test valid type to label conversion."""
        assert graph_store._type_to_label("Person") == "Person"
        assert graph_store._type_to_label("Organization") == "Organization"
        assert graph_store._type_to_label("Location") == "Location"
        assert graph_store._type_to_label("Event") == "Event"

    def test_type_to_label_with_spaces(self, graph_store):
        """Test type with spaces."""
        assert graph_store._type_to_label("Axis powers") == "Axis_powers"

    def test_type_to_label_starts_with_number(self, graph_store):
        """Test type starting with non-alpha character."""
        assert graph_store._type_to_label("1st Division") == "E_1st_Division"

    def test_type_to_rel_type_valid(self, graph_store):
        """Test valid relationship type conversion."""
        assert graph_store._type_to_rel_type("LOCATED_IN") == "LOCATED_IN"
        assert graph_store._type_to_rel_type("AFFILIATED_WITH") == "AFFILIATED_WITH"

    def test_type_to_rel_type_with_spaces(self, graph_store):
        """Test relationship type with spaces."""
        assert graph_store._type_to_rel_type("part of") == "PART_OF"

    def test_type_to_rel_type_with_dashes(self, graph_store):
        """Test relationship type with dashes."""
        assert graph_store._type_to_rel_type("fight-against") == "FIGHT_AGAINST"

    def test_type_to_rel_type_starts_with_number(self, graph_store):
        """Test relationship type starting with non-alpha."""
        assert graph_store._type_to_rel_type("1st-order") == "R_1ST_ORDER"

    def test_get_entity_by_uuid_not_found(self, graph_store):
        """Test getting non-existent entity returns None."""
        graph_store._run = Mock(return_value=[])
        result = graph_store.get_entity_by_uuid("nonexistent")
        assert result is None

    def test_get_entity_by_uuid_found(self, graph_store):
        """Test getting existing entity."""
        mock_node = {
            "uuid": "test-uuid",
            "name": "Germany",
            "type": "Country",
            "properties": '{"lat": 51.16}',
            "mentions": "[]",
        }
        graph_store._run = Mock(return_value=[{"e": mock_node}])
        result = graph_store.get_entity_by_uuid("test-uuid")
        assert result is not None
        assert result["name"] == "Germany"

    def test_get_entities_by_name(self, graph_store):
        """Test finding entities by name."""
        mock_node = {"uuid": "uuid-1", "name": "Germany", "type": "Country"}
        graph_store._run = Mock(return_value=[{"e": mock_node}])
        results = graph_store.get_entities_by_name("Germany")
        assert len(results) == 1
        assert results[0]["name"] == "Germany"

    def test_get_entities_by_name_with_thread(self, graph_store):
        """Test finding entities by name with thread filter."""
        graph_store._run = Mock(return_value=[])
        results = graph_store.get_entities_by_name("Germany", thread_id="thread-1")
        assert len(results) == 0
        call_args = graph_store._run.call_args[0]
        assert "thread_id" in call_args[1]

    def test_get_neighbors(self, graph_store):
        """Test getting neighbors of an entity."""
        mock_node = {"uuid": "neighbor-1", "name": "France", "type": "Country"}
        graph_store._run = Mock(return_value=[{"neighbor": mock_node}])
        results = graph_store.get_neighbors("test-uuid", hops=1)
        assert len(results) == 1
        assert results[0]["name"] == "France"

    def test_get_subgraph_empty(self, graph_store):
        """Test getting subgraph with no results."""
        graph_store._run = Mock(return_value=[])
        result = graph_store.get_subgraph("test-uuid")
        assert result == {"entities": [], "links": []}

    def test_get_subgraph_with_results(self, graph_store):
        """Test getting subgraph with results."""
        nodes = [{"uuid": "n1"}, {"uuid": "n2"}]
        rels = [{"uuid": "r1"}]
        graph_store._run = Mock(return_value=[{"nodes": nodes, "relationships": rels}])
        result = graph_store.get_subgraph("test-uuid")
        assert len(result["entities"]) == 2
        assert len(result["links"]) == 1

    def test_get_context_for_query_empty_names(self, graph_store):
        """Test context generation with empty entity names."""
        result = graph_store.get_context_for_query([])
        assert result == ""

    def test_get_context_for_query_no_related(self, graph_store):
        """Test context generation when no related entities found."""
        graph_store.get_related_entities = Mock(return_value=[])
        result = graph_store.get_context_for_query(["Germany"])
        assert result == ""

    def test_get_context_for_query_with_related(self, graph_store):
        """Test context generation with related entities."""
        graph_store.get_related_entities = Mock(
            return_value=[
                {
                    "name": "France",
                    "type": "Country",
                    "properties": {},
                    "mentions": [],
                }
            ]
        )
        graph_store._get_relationships_between_names = Mock(return_value=[])
        result = graph_store.get_context_for_query(["Germany"])
        assert "KNOWN ONTOLOGY CONTEXT:" in result
        assert "France" in result

    def test_get_context_for_query_with_relationships(self, graph_store):
        """Test context generation includes direct relationships."""
        graph_store.get_related_entities = Mock(return_value=[])
        graph_store._get_relationships_between_names = Mock(
            return_value=[
                {
                    "source_name": "Germany",
                    "target_name": "France",
                    "type": "ALLIES_WITH",
                }
            ]
        )
        result = graph_store.get_context_for_query(["Germany", "France"])
        assert "Germany" in result
        assert "ALLIES_WITH" in result

    def test_get_stats(self, graph_store):
        """Test getting ontology statistics."""
        graph_store._run = Mock(return_value=[{"count": 5}])
        stats = graph_store.get_stats()
        assert stats["entity_count"] == 5
        assert stats["link_count"] == 5

    def test_get_stats_with_thread(self, graph_store):
        """Test getting stats for a specific thread."""
        graph_store._run = Mock(return_value=[{"count": 3}])
        stats = graph_store.get_stats(thread_id="thread-1")
        assert stats["entity_count"] == 3

    def test_get_entities_by_type(self, graph_store):
        """Test getting entities by type."""
        mock_node = {"uuid": "uuid-1", "name": "Germany", "type": "Country"}
        graph_store._run = Mock(return_value=[{"e": mock_node}])
        results = graph_store.get_entities_by_type("Country")
        assert len(results) == 1
        assert results[0]["type"] == "Country"

    def test_search_entities_by_name_pattern(self, graph_store):
        """Test searching entities by name pattern."""
        mock_node = {"uuid": "uuid-1", "name": "Germany", "type": "Country"}
        graph_store._run = Mock(return_value=[{"e": mock_node}])
        results = graph_store.search_entities_by_name_pattern("Ger")
        assert len(results) == 1

    def test_get_related_entities(self, graph_store):
        """Test getting related entities."""
        mock_node = {"uuid": "rel-1", "name": "France", "type": "Country"}
        graph_store._run = Mock(return_value=[{"related": mock_node}])
        results = graph_store.get_related_entities(["Germany"])
        assert len(results) == 1
        assert results[0]["name"] == "France"

    def test_get_all_entities(self, graph_store):
        """Test getting all entities."""
        mock_node = {"uuid": "uuid-1", "name": "Germany", "type": "Country"}
        graph_store._run = Mock(return_value=[{"e": mock_node}])
        results = graph_store.get_all_entities()
        assert len(results) == 1

    def test_get_all_links(self, graph_store):
        """Test getting all links."""
        mock_rel = {
            "r": {"uuid": "link-1", "type": "ALLIES_WITH"},
            "source_name": "Germany",
            "target_name": "France",
        }
        graph_store._run = Mock(return_value=[mock_rel])
        results = graph_store.get_all_links()
        assert len(results) == 1

    def test_get_links_for_entity(self, graph_store):
        """Test getting links for a specific entity."""
        mock_rel = {
            "r": {"uuid": "link-1", "type": "ALLIES_WITH"},
            "other": {"uuid": "france-uuid"},
            "direction": "OUTGOING",
        }
        graph_store._run = Mock(return_value=[mock_rel])
        results = graph_store.get_links_for_entity("germany-uuid")
        assert len(results) == 1
        assert results[0]["direction"] == "OUTGOING"

    def test_clear_thread_ontology(self, graph_store):
        """Test clearing all ontology for a thread."""
        graph_store._run_write = Mock()
        graph_store.clear_thread_ontology("thread-1")
        graph_store._run_write.assert_called_once()
        call_args = graph_store._run_write.call_args[0]
        assert "thread-1" in call_args[1]["thread_id"]
