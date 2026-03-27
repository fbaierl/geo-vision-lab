"""
Ontology API Routes

REST endpoints for ontology export/import.
"""

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import Response, JSONResponse
from app.models.ontology import SessionOntology
from app.services.ontology.export import OntologyExportService
from app.services.ontology.service import OntologyService
from app.core.di import get_ontology_service

router = APIRouter(prefix="/api/ontology", tags=["ontology"])


@router.get("/{thread_id}/export")
async def export_ontology(thread_id: str):
    """
    Export ontology for a thread.

    Args:
        thread_id: Thread ID

    Returns:
        JSON file download
    """
    try:
        ontology_service = get_ontology_service()
        ontology = ontology_service.load_ontology(thread_id)

        metadata = {
            "thread_id": thread_id,
            "exported_from": "GeoVision Lab"
        }

        json_str = OntologyExportService.export_to_json(ontology, metadata)

        return Response(
            content=json_str,
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="ontology_{thread_id}.json"'
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")


@router.post("/{thread_id}/import")
async def import_ontology(
    thread_id: str,
    file: UploadFile = File(...),
    mode: str = "merge"
):
    """
    Import ontology into a thread.

    Args:
        thread_id: Thread ID
        file: JSON file to import
        mode: "merge" (default) or "replace"

    Returns:
        Import result with statistics
    """
    if not file.filename.endswith('.json'):
        raise HTTPException(status_code=400, detail="Only JSON files are supported")

    try:
        content = await file.read()
        imported_ontology = OntologyExportService.import_from_json(content.decode('utf-8'))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON format: {str(e)}")

    try:
        ontology_service = get_ontology_service()
        current_ontology = ontology_service.load_ontology(thread_id)

        if mode == "replace":
            final_ontology = imported_ontology
        else:  # merge
            final_ontology = OntologyExportService.merge_imported_ontology(
                current_ontology,
                imported_ontology
            )

        ontology_service.save_ontology(thread_id, final_ontology)

        return {
            "status": "success",
            "mode": mode,
            "imported_entities": len(imported_ontology.entities),
            "imported_links": len(imported_ontology.links),
            "total_entities": len(final_ontology.entities),
            "total_links": len(final_ontology.links)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")


@router.get("/{thread_id}")
async def get_ontology(thread_id: str):
    """
    Get current ontology for a thread.

    Args:
        thread_id: Thread ID

    Returns:
        Ontology data with entity and link counts
    """
    try:
        ontology_service = get_ontology_service()
        ontology = ontology_service.load_ontology(thread_id)

        return {
            "thread_id": thread_id,
            "entity_count": len(ontology.entities),
            "link_count": len(ontology.links),
            "entities": [e.model_dump() for e in ontology.entities.values()],
            "links": [l.model_dump() for l in ontology.links.values()]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load ontology: {str(e)}")
