"""
Ontology Service Package

Handles ontology operations:
- Merge logic
- Service layer (load/save, lookups)
- Export/Import
"""

from app.services.ontology.merge import merge_ontologies, merge_entity
from app.services.ontology.service import OntologyService
from app.services.ontology.export import OntologyExportService

__all__ = [
    "merge_ontologies",
    "merge_entity",
    "OntologyService",
    "OntologyExportService",
]
