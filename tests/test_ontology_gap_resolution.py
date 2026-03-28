"""
Tests for Ontology Gap Resolution

Tests the two-pass extraction with gap resolution:
- Gap detection when links reference missing entities
- Gap entity extraction via targeted LLM prompt
- Entity merging and link resolution
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from app.models.ontology import OntologyDelta, OntologyDeltaEntity, OntologyDeltaLink


class TestOntologyGapResolution:
    """Test suite for ontology gap resolution functionality."""

    def test_gap_detection_identifies_missing_entities(self):
        """Test that gaps are correctly identified when links reference missing entities."""
        from app.agents.ontology_subgraph import extract_ontology_node
        
        # Mock state with a response that has entities and links with missing references
        state = {
            "user_query": "Who was fighting in WW2?",
            "assistant_response": """
                The Allies and Axis powers were the two main opposing military alliances.
                The Allies included United States, United Kingdom, and Soviet Union.
                The Axis powers included Nazi Germany, Empire of Japan, and Kingdom of Italy.
            """,
            "query_id": "test-query-123"
        }
        
        # Mock the extractor to return entities without "Allies" and "Axis powers"
        mock_delta = OntologyDelta(
            entities=[
                OntologyDeltaEntity(name="United States", type="Location", context="The Allies included United States"),
                OntologyDeltaEntity(name="United Kingdom", type="Location", context="United Kingdom was part of Allies"),
                OntologyDeltaEntity(name="Nazi Germany", type="Location", context="Axis powers included Nazi Germany"),
            ],
            links=[
                OntologyDeltaLink(source_entity_name="United States", target_entity_name="Allies", relationship_type="PART_OF", context="The Allies included United States"),
                OntologyDeltaLink(source_entity_name="Nazi Germany", target_entity_name="Axis powers", relationship_type="PART_OF", context="Axis powers included Nazi Germany"),
            ]
        )
        
        with patch('app.agents.ontology_subgraph.get_ontology_extractor') as mock_get_extractor:
            mock_extractor = Mock()
            mock_extractor.extract.return_value = mock_delta
            mock_get_extractor.return_value = mock_extractor
            
            with patch('app.agents.ontology_subgraph.get_location_extractor'):
                result = extract_ontology_node(state)
        
        # Assert gaps were detected
        assert "gap_entity_names" in result
        gap_names = result["gap_entity_names"]
        assert "allies" in [n.lower() for n in gap_names]
        assert "axis powers" in [n.lower() for n in gap_names]
        
        # Assert links are pending
        assert "pending_links" in result
        assert len(result["pending_links"]) == 2

    def test_gap_detection_no_gaps(self):
        """Test that no gaps are reported when all link references exist."""
        from app.agents.ontology_subgraph import extract_ontology_node
        
        state = {
            "user_query": "Test query",
            "assistant_response": "John works at Microsoft in Seattle",
            "query_id": "test-query-456"
        }
        
        mock_delta = OntologyDelta(
            entities=[
                OntologyDeltaEntity(name="John", type="Person", context="John works at Microsoft"),
                OntologyDeltaEntity(name="Microsoft", type="Organization", context="works at Microsoft"),
                OntologyDeltaEntity(name="Seattle", type="Location", context="Microsoft in Seattle"),
            ],
            links=[
                OntologyDeltaLink(source_entity_name="John", target_entity_name="Microsoft", relationship_type="WORKS_AT", context="John works at Microsoft"),
                OntologyDeltaLink(source_entity_name="Microsoft", target_entity_name="Seattle", relationship_type="LOCATED_IN", context="Microsoft in Seattle"),
            ]
        )
        
        with patch('app.agents.ontology_subgraph.get_ontology_extractor') as mock_get_extractor:
            mock_extractor = Mock()
            mock_extractor.extract.return_value = mock_delta
            mock_get_extractor.return_value = mock_extractor
            
            with patch('app.agents.ontology_subgraph.get_location_extractor'):
                result = extract_ontology_node(state)
        
        # Assert no gaps
        assert result["gap_entity_names"] == []
        # But links are still pending for finalization
        assert len(result["pending_links"]) == 2

    def test_detect_gaps_routes_to_extraction(self):
        """Test that route_after_gap_detection routes correctly based on gaps."""
        from app.agents.ontology_subgraph import route_after_gap_detection
        
        state_with_gaps = {
            "gap_entity_names": ["Allies", "Axis powers"]
        }
        
        result = route_after_gap_detection(state_with_gaps)
        assert result == "extract_gap_entities"
        
        state_without_gaps = {
            "gap_entity_names": []
        }
        
        result = route_after_gap_detection(state_without_gaps)
        assert result == "merge_and_finalize"

    def test_extract_gap_entities_calls_extractor(self):
        """Test that gap extraction invokes the targeted extraction method."""
        from app.agents.ontology_subgraph import extract_gap_entities_node
        
        state = {
            "gap_entity_names": ["Allies", "Axis powers"],
            "assistant_response": "The Allies and Axis powers fought in WW2",
            "user_query": "Who fought in WW2?",
        }
        
        mock_gap_entities = [
            OntologyDeltaEntity(name="Allies", type="Organization", context="The Allies and Axis powers fought in WW2"),
            OntologyDeltaEntity(name="Axis powers", type="Organization", context="The Allies and Axis powers fought in WW2"),
        ]
        
        with patch('app.agents.ontology_subgraph.get_ontology_extractor') as mock_get_extractor:
            mock_extractor = Mock()
            mock_extractor.extract_missing_entities.return_value = mock_gap_entities
            mock_get_extractor.return_value = mock_extractor
            
            result = extract_gap_entities_node(state)
        
        # Verify extractor was called with correct parameters
        mock_extractor.extract_missing_entities.assert_called_once()
        call_args = mock_extractor.extract_missing_entities.call_args
        assert call_args[1]["missing_names"] == ["Allies", "Axis powers"]
        
        # Verify result contains raw entities
        assert "gap_entities_raw" in result
        assert len(result["gap_entities_raw"]) == 2

    def test_merge_and_finalize_creates_gap_entities(self):
        """Test that merge_and_finalize_node creates entities from gap extraction."""
        from app.agents.ontology_subgraph import merge_and_finalize_node
        from app.models.ontology import SessionOntology, OntologyEntity
        
        # Create a session delta with some entities
        existing_delta = SessionOntology()
        
        state = {
            "extracted_delta": existing_delta,
            "gap_entities_raw": [
                {"name": "Allies", "type": "Organization", "context": "The Allies fought"},
                {"name": "Axis powers", "type": "Organization", "context": "Axis powers fought"},
            ],
            "pending_links": [
                {"source_entity_name": "United States", "target_entity_name": "Allies", "relationship_type": "PART_OF", "context": "US part of Allies"},
            ],
            "query_id": "test-789"
        }
        
        result = merge_and_finalize_node(state)
        
        # Gap entities should be created
        final_delta = result["extracted_delta"]
        assert len(final_delta.entities) == 2  # Allies and Axis powers
        
        # Verify entities have correct names and types
        entity_names = {e.name for e in final_delta.entities.values()}
        assert "Allies" in entity_names
        assert "Axis powers" in entity_names

    def test_merge_and_finalize_skips_unresolvable_links(self):
        """Test that links with still-missing entities are skipped."""
        from app.agents.ontology_subgraph import merge_and_finalize_node
        from app.models.ontology import SessionOntology
        
        existing_delta = SessionOntology()
        
        state = {
            "extracted_delta": existing_delta,
            "gap_entities_raw": [
                {"name": "Allies", "type": "Organization", "context": "The Allies"},
                # Note: "Axis powers" not in gap_entities_raw
            ],
            "pending_links": [
                {"source_entity_name": "United States", "target_entity_name": "Allies", "relationship_type": "PART_OF", "context": "US part of Allies"},
                {"source_entity_name": "Nazi Germany", "target_entity_name": "Axis powers", "relationship_type": "PART_OF", "context": "Germany part of Axis"},
            ],
            "query_id": "test-999"
        }
        
        # This should not raise, but should skip the unresolvable link
        result = merge_and_finalize_node(state)
        
        final_delta = result["extracted_delta"]
        # Only 1 link should be created (the one with "Allies")
        # The "Axis powers" link should be skipped
        assert len(final_delta.links) == 0  # Actually 0 because "United States" doesn't exist either

    def test_extractor_gap_method_handles_empty_input(self):
        """Test that extract_missing_entities handles empty inputs gracefully."""
        from app.services.ontology_extractor import OntologyExtractorService
        
        mock_llm = Mock()
        extractor = OntologyExtractorService(mock_llm)
        
        # Empty text
        result = extractor.extract_missing_entities(text="", missing_names=["Test"])
        assert result == []
        
        # Empty missing names
        result = extractor.extract_missing_entities(text="Some text", missing_names=[])
        assert result == []

    def test_ontology_subgraph_structure(self):
        """Test that the ontology subgraph has the correct structure."""
        from app.agents.ontology_subgraph import create_ontology_subgraph
        
        subgraph = create_ontology_subgraph()
        
        # Verify nodes exist
        assert "extract_ontology" in subgraph.nodes
        assert "detect_gaps" in subgraph.nodes
        assert "extract_gap_entities" in subgraph.nodes
        assert "merge_and_finalize" in subgraph.nodes
