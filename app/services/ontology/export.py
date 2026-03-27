"""
Ontology Export/Import Service

Handles JSON export and import of ontologies.
"""

import json
from datetime import datetime
from typing import Optional
from app.models.ontology import SessionOntology
from app.services.ontology.merge import merge_ontologies


# GeoVision Lab Ontology Format Version
ONTOLOGY_FORMAT_VERSION = "1.0"
ONTOLOGY_SCHEMA_URL = "https://geo-vision-lab.dev/ontology-v1.schema.json"


class OntologyExportService:
    """Service for ontology export/import operations."""

    @staticmethod
    def export_to_json(
        ontology: SessionOntology,
        metadata: Optional[dict] = None
    ) -> str:
        """
        Export ontology to JSON string using GeoVision Lab format v1.0.

        Format structure:
        {
            "$schema": "https://geo-vision-lab.dev/ontology-v1.schema.json",
            "version": "1.0",
            "metadata": {
                "thread_id": "...",
                "exported_at": "...",
                "entity_count": 0,
                "link_count": 0
            },
            "entities": [...],
            "links": [...]
        }

        Args:
            ontology: Ontology to export
            metadata: Optional metadata (thread_id, name, description, etc.)

        Returns:
            JSON string
        """
        if metadata is None:
            metadata = {}

        export_data = {
            "$schema": ONTOLOGY_SCHEMA_URL,
            "version": ONTOLOGY_FORMAT_VERSION,
            "metadata": {
                **metadata,
                "exported_at": datetime.utcnow().isoformat() + "Z",
                "entity_count": len(ontology.entities),
                "link_count": len(ontology.links)
            },
            "entities": [e.model_dump(mode='json') for e in ontology.entities.values()],
            "links": [l.model_dump(mode='json') for l in ontology.links.values()]
        }

        return json.dumps(export_data, indent=2, default=str)

    @staticmethod
    def export_to_file(
        ontology: SessionOntology,
        filepath: str,
        metadata: Optional[dict] = None
    ):
        """
        Export ontology to JSON file.

        Args:
            ontology: Ontology to export
            filepath: Path to output file
            metadata: Optional metadata
        """
        json_str = OntologyExportService.export_to_json(ontology, metadata)
        with open(filepath, 'w') as f:
            f.write(json_str)

    @staticmethod
    def import_from_json(json_str: str) -> SessionOntology:
        """
        Import ontology from JSON string.

        Supports both:
        - GeoVision Lab format v1.0 (with $schema, version, metadata)
        - Legacy format (direct entities/links arrays)

        Args:
            json_str: JSON string

        Returns:
            SessionOntology object
        """
        data = json.loads(json_str)
        
        # Check if it's GeoVision Lab format v1.0
        if "$schema" in data or "version" in data:
            # New format - extract entities and links from the structure
            entities_data = data.get("entities", [])
            links_data = data.get("links", [])
            
            # Reconstruct SessionOntology from arrays
            ontology = SessionOntology()
            for e in entities_data:
                from app.models.ontology import OntologyEntity
                entity = OntologyEntity.model_validate(e)
                ontology.entities[str(entity.uuid)] = entity
            
            for l in links_data:
                from app.models.ontology import OntologyLink
                link = OntologyLink.model_validate(l)
                ontology.links[str(link.uuid)] = link
            
            return ontology
        else:
            # Legacy format - use existing from_export_format
            return SessionOntology.from_export_format(data)

    @staticmethod
    def import_from_file(filepath: str) -> SessionOntology:
        """
        Import ontology from JSON file.

        Args:
            filepath: Path to JSON file

        Returns:
            SessionOntology object
        """
        with open(filepath, 'r') as f:
            json_str = f.read()
        return OntologyExportService.import_from_json(json_str)

    @staticmethod
    def merge_imported_ontology(
        current: SessionOntology,
        imported: SessionOntology
    ) -> SessionOntology:
        """
        Merge imported ontology with current session ontology.

        - Entities with matching UUIDs are merged
        - Entities with different UUIDs are added (even if same name - homonyms)
        - Links are merged by UUID

        Args:
            current: Current session ontology
            imported: Imported ontology

        Returns:
            Merged ontology
        """
        return merge_ontologies(current, imported)
