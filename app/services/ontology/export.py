"""
Ontology Export/Import Service

Handles JSON export and import of ontologies.
"""

import json
from datetime import datetime
from typing import Optional
from app.models.ontology import SessionOntology
from app.services.ontology.merge import merge_ontologies


class OntologyExportService:
    """Service for ontology export/import operations."""
    
    @staticmethod
    def export_to_json(
        ontology: SessionOntology, 
        metadata: Optional[dict] = None
    ) -> str:
        """
        Export ontology to JSON string.
        
        Args:
            ontology: Ontology to export
            metadata: Optional metadata (thread_id, name, description, etc.)
        
        Returns:
            JSON string
        """
        if metadata is None:
            metadata = {}
        
        export_data = ontology.to_export_format({
            **metadata,
            "exported_at": datetime.utcnow().isoformat(),
            "entity_count": len(ontology.entities),
            "link_count": len(ontology.links)
        })
        
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
        
        Args:
            json_str: JSON string
        
        Returns:
            SessionOntology object
        """
        data = json.loads(json_str)
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
