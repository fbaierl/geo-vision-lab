"""
Ontology API Routes

REST endpoints for ontology export/import.
"""

from typing import List
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from app.services.ontology.export import OntologyExportService
from app.core.di import get_ontology_service, get_graph_store

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

        metadata = {"thread_id": thread_id, "exported_from": "GeoVision Lab"}

        json_str = OntologyExportService.export_to_json(ontology, metadata)

        return Response(
            content=json_str,
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="ontology_{thread_id}.json"'
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")


@router.post("/{thread_id}/import")
async def import_ontology(
    thread_id: str, file: UploadFile = File(...), mode: str = "merge"
):
    """
    Import ontology into a thread.

    Args:
        thread_id: Thread ID (used if file doesn't contain thread_id in metadata)
        file: JSON file to import
        mode: "merge" (default) or "replace"

    Returns:
        Import result with statistics
    """
    import logging

    logger = logging.getLogger(__name__)

    logger.info(
        f"[IMPORT] Starting import for thread '{thread_id}', mode={mode}, file={file.filename}"
    )

    if not file.filename.endswith(".json"):
        logger.error(f"[IMPORT] Invalid file type: {file.filename}")
        raise HTTPException(status_code=400, detail="Only JSON files are supported")

    try:
        content = await file.read()
        logger.debug(f"[IMPORT] Read {len(content)} bytes from file")
        imported_ontology = OntologyExportService.import_from_json(
            content.decode("utf-8")
        )
        logger.info(
            f"[IMPORT] Parsed ontology: {len(imported_ontology.entities)} entities, {len(imported_ontology.links)} links"
        )
    except Exception as e:
        logger.error(f"[IMPORT] Failed to parse JSON: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid JSON format: {str(e)}")

    try:
        ontology_service = get_ontology_service()

        # Use thread_id from the imported file's metadata if available
        # This ensures we restore the project to its original thread
        target_thread_id = thread_id
        logger.info(
            f"[IMPORT] Loading current ontology for thread '{target_thread_id}'"
        )
        current_ontology = ontology_service.load_ontology(target_thread_id)
        logger.info(
            f"[IMPORT] Current ontology: {len(current_ontology.entities)} entities, {len(current_ontology.links)} links"
        )

        if mode == "replace":
            logger.info("[IMPORT] Replacing ontology entirely")
            final_ontology = imported_ontology
        else:  # merge
            logger.info("[IMPORT] Merging ontologies")
            final_ontology = OntologyExportService.merge_imported_ontology(
                current_ontology, imported_ontology
            )
            logger.info(
                f"[IMPORT] Merged result: {len(final_ontology.entities)} entities, {len(final_ontology.links)} links"
            )

        logger.info(f"[IMPORT] Saving ontology for thread '{target_thread_id}'")
        ontology_service.save_ontology(target_thread_id, final_ontology)
        logger.info("[IMPORT] Save complete")

        return {
            "status": "success",
            "mode": mode,
            "imported_entities": len(imported_ontology.entities),
            "imported_links": len(imported_ontology.links),
            "total_entities": len(final_ontology.entities),
            "total_links": len(final_ontology.links),
            "thread_id": target_thread_id,
        }
    except Exception as e:
        logger.error(f"[IMPORT] Failed to save ontology: {e}")
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
            "links": [link.model_dump() for link in ontology.links.values()],
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to load ontology: {str(e)}"
        )


class MergeEntitiesRequest(BaseModel):
    entity_uuids: List[str]
    target_name: str = None
    target_type: str = None


@router.post("/{thread_id}/merge-entities")
async def merge_entities(thread_id: str, data: MergeEntitiesRequest):
    """
    Merge multiple similar entities into a single entity.

    The first UUID in the list becomes the primary entity.
    All other entities are deleted and their relationships are rewired to the primary.
    Properties and mentions are merged.

    Args:
        thread_id: Thread ID
        data: MergeEntitiesRequest containing entity UUIDs and optional target name/type

    Returns:
        Merge result with primary UUID and counts
    """
    if not data.entity_uuids or len(data.entity_uuids) < 2:
        raise HTTPException(
            status_code=400, detail="At least 2 entity UUIDs are required for merging"
        )

    try:
        graph_store = get_graph_store()
        result = graph_store.merge_entities(
            entity_uuids=data.entity_uuids,
            target_name=data.target_name,
            target_type=data.target_type,
        )

        if not result:
            raise HTTPException(
                status_code=400, detail="Could not merge entities. Ensure all UUIDs are valid."
            )

        return {
            "status": "success",
            "primary_uuid": result["primary_uuid"],
            "name": result["name"],
            "type": result["type"],
            "merged_entities": result["merged_entities"],
            "deleted_entities": result["deleted_entities"],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to merge entities: {str(e)}"
        )
