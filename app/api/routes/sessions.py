"""
Session API Routes

REST endpoints for session management (list, create, update, delete).
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import uuid4

from app.core.di_database import get_database
from app.core.di_graph import get_graph_store
from app.core.di import get_ontology_service
from app.services.ontology.merge import merge_ontologies
from app.models.ontology import SessionOntology
from app.services.relationship_discovery import discover_relationships
from app.core.di_services import get_vector_store

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


class SessionCreate(BaseModel):
    title: Optional[str] = None


class SessionUpdate(BaseModel):
    title: Optional[str] = None
    messages: Optional[List[Dict[str, Any]]] = None


class SessionSave(BaseModel):
    messages: List[Dict[str, Any]] = Field(default_factory=list)
    pending_ontology: Optional[Dict[str, Any]] = None


class IntelLogEntry(BaseModel):
    query: str
    timestamp: int
    response: str = ""
    tools: List[Dict[str, Any]] = Field(default_factory=list)
    prompt: Optional[str] = None


class SessionListResponse(BaseModel):
    thread_id: str
    title: str
    updated_at: str
    message_count: int


@router.get("")
async def list_sessions():
    """
    List all sessions sorted by updated_at (most recent first).

    Returns minimal info for sidebar display.
    """
    db = get_database()

    # Get all sessions
    sessions_cursor = db.sessions.find(
        {},
        {
            "_id": 0,
            "thread_id": 1,
            "title": 1,
            "updated_at": 1,
            "messages": 1,  # Get full messages array, we'll count it
        },
    ).sort("updated_at", -1)

    sessions = []
    for session in sessions_cursor:
        messages = session.get("messages", [])
        sessions.append(
            {
                "thread_id": session.get("thread_id", ""),
                "title": session.get("title", "Untitled"),
                "updated_at": session.get("updated_at", "").isoformat()
                if isinstance(session.get("updated_at"), datetime)
                else str(session.get("updated_at", "")),
                "message_count": len(messages) if isinstance(messages, list) else 0,
            }
        )

    return sessions


@router.post("")
async def create_session(data: SessionCreate):
    """
    Create a new session.

    Returns thread_id for use in subsequent requests.
    Note: Session is created empty - title is set on first save.
    """
    db = get_database()

    thread_id = str(uuid4())
    title = data.title or "New Session"  # Temporary title until first query
    now = datetime.utcnow()

    session_doc = {
        "thread_id": thread_id,
        "title": title,
        "created_at": now,
        "updated_at": now,
        "messages": [],
    }

    db.sessions.insert_one(session_doc)

    return {"thread_id": thread_id, "created_at": now.isoformat(), "title": title}


@router.get("/{thread_id}")
async def get_session(thread_id: str):
    """
    Get full session data including messages and ontology.
    """
    db = get_database()

    session = db.sessions.find_one({"thread_id": thread_id})

    if not session:
        # Return empty session structure
        return {
            "thread_id": thread_id,
            "title": "Untitled",
            "created_at": None,
            "updated_at": None,
            "messages": [],
            "ontology": {"entities": {}, "links": {}},
            "intel_log": [],
        }

    # Load ontology from Neo4j (abstracted from frontend)
    try:
        ontology_service = get_ontology_service()
        ontology = ontology_service.load_ontology(thread_id)
        ontology_data = {
            "entities": {
                str(entity.uuid): entity.model_dump()
                for entity in ontology.entities.values()
            },
            "links": {
                str(link.uuid): link.model_dump()
                for link in ontology.links.values()
            },
        }
        import logging
        logging.getLogger("agent_flow").info(
            f"[SESSION_GET] Loaded ontology from Neo4j: {len(ontology_data['entities'])} entities, "
            f"{len(ontology_data['links'])} links for thread {thread_id}"
        )
    except Exception as e:
        import logging
        logging.getLogger("agent_flow").warning(
            f"[SESSION_GET] Failed to load ontology from Neo4j: {e}"
        )
        ontology_data = {"entities": {}, "links": {}}

    return {
        "thread_id": session.get("thread_id", thread_id),
        "title": session.get("title", "Untitled"),
        "created_at": session.get("created_at"),
        "updated_at": session.get("updated_at"),
        "messages": session.get("messages", []),
        "ontology": ontology_data,
        "pending_ontology": session.get("pending_ontology", {"entities": {}, "links": {}}),
        "intel_log": session.get("intel_log", []),
    }


@router.put("/{thread_id}")
async def update_session(thread_id: str, data: SessionUpdate):
    """
    Update session title or messages.
    """
    db = get_database()

    update_fields = {}
    if data.title is not None:
        update_fields["title"] = data.title
    if data.messages is not None:
        update_fields["messages"] = data.messages

    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    update_fields["updated_at"] = datetime.utcnow()

    result = db.sessions.update_one(
        {"thread_id": thread_id}, {"$set": update_fields}, upsert=True
    )

    return {
        "status": "success",
        "updated": result.modified_count > 0 or result.upserted_id is not None,
    }


@router.delete("")
async def delete_all_sessions():
    """
    Delete all sessions (bulk operation).

    Returns the count of deleted sessions.
    Also clears all Neo4j ontology data.
    """
    db = get_database()

    result = db.sessions.delete_many({})

    # Clear all Neo4j ontology data
    try:
        graph_store = get_graph_store()
        graph_store.clear_all_ontology()
    except Exception as e:
        import logging

        logging.getLogger("agent_flow").warning(
            f"[SESSION_DELETE] Failed to clear Neo4j ontology: {e}"
        )

    return {"status": "success", "deleted": True, "deleted_count": result.deleted_count}


@router.delete("/{thread_id}")
async def delete_session(thread_id: str):
    """
    Delete a session (instant, no confirmation).
    Also clears all Neo4j ontology data for this thread.
    """
    db = get_database()

    result = db.sessions.delete_one({"thread_id": thread_id})

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail=f"Session {thread_id} not found")

    # Clear Neo4j ontology data for this thread
    try:
        graph_store = get_graph_store()
        graph_store.clear_thread_ontology(thread_id)
    except Exception as e:
        # Log but don't fail the request if Neo4j cleanup fails
        import logging

        logging.getLogger("agent_flow").warning(
            f"[SESSION_DELETE] Failed to clear Neo4j ontology for thread {thread_id}: {e}"
        )

    return {"status": "success", "deleted": True}


@router.post("/{thread_id}/save")
async def save_session(thread_id: str, data: SessionSave):
    """
    Auto-save session after each query.

    Upserts session with current messages.
    """
    db = get_database()

    now = datetime.utcnow()

    # Generate title from first user message if not set
    title = "Untitled"
    if data.messages:
        for msg in data.messages:
            if msg.get("role") == "user":
                content = msg.get("content", "")
                words = content.split()[:6]
                title = " ".join(words)
                if len(content.split()) > 6:
                    title += "..."
                break

    session_doc = {
        "thread_id": thread_id,
        "title": title,
        "created_at": now,
        "updated_at": now,
        "messages": data.messages,
        "pending_ontology": data.pending_ontology or {"entities": {}, "links": {}},
    }

    # Try to find existing session first
    existing = db.sessions.find_one({"thread_id": thread_id})

    if existing:
        update_fields = {
            "messages": data.messages,
            "updated_at": now,
            "title": title,
        }
        if data.pending_ontology is not None:
            update_fields["pending_ontology"] = data.pending_ontology
        db.sessions.update_one(
            {"thread_id": thread_id},
            {"$set": update_fields},
        )
    else:
        # Create new session
        db.sessions.insert_one(session_doc)

    return {
        "status": "success",
        "thread_id": thread_id,
        "message_count": len(data.messages),
    }


@router.post("/{thread_id}/intel-log")
async def append_intel_log(thread_id: str, data: IntelLogEntry):
    """
    Append an entry to the session's intelligence log.
    """
    db = get_database()

    entry = data.model_dump()

    result = db.sessions.update_one(
        {"thread_id": thread_id},
        {
            "$push": {"intel_log": entry},
            "$set": {"updated_at": datetime.utcnow()},
        },
        upsert=True,
    )

    return {"status": "success", "appended": True}


@router.get("/{thread_id}/pending-ontology")
async def get_pending_ontology(thread_id: str):
    """
    Get pending ontology changes for a session.

    Returns unreviewed ontology changes that have been extracted but not yet committed to Neo4j.
    """
    db = get_database()

    session = db.sessions.find_one({"thread_id": thread_id})
    if not session:
        return {
            "thread_id": thread_id,
            "entities": {},
            "links": {},
            "entity_count": 0,
            "link_count": 0,
        }

    pending = session.get("pending_ontology", {"entities": {}, "links": {}})

    return {
        "thread_id": thread_id,
        "entities": pending.get("entities", {}),
        "links": pending.get("links", {}),
        "entity_count": len(pending.get("entities", {})),
        "link_count": len(pending.get("links", {})),
    }


@router.post("/{thread_id}/pending-ontology/approve")
async def approve_pending_ontology(thread_id: str, data: Optional[Dict[str, Any]] = None):
    """
    Approve pending ontology changes and merge them into Neo4j.

    Optionally, specific entity/link UUIDs can be provided to approve only selected changes.
    If no UUIDs provided, all pending changes are approved.
    """
    db = get_database()

    session = db.sessions.find_one({"thread_id": thread_id})
    if session:
        pending = session.get("pending_ontology", {"entities": {}, "links": {}})
    else:
        # Session not yet saved to MongoDB; try to read pending from LangGraph state
        try:
            from app.agents.graph import app_graph
            config = {"configurable": {"thread_id": thread_id}}
            current_state = app_graph.get_state(config)
            pending_state = current_state.values.get("pending_ontology")
            if pending_state and hasattr(pending_state, "model_dump"):
                pending = pending_state.model_dump(mode="json")
            elif pending_state and isinstance(pending_state, dict):
                pending = pending_state
            else:
                pending = {"entities": {}, "links": {}}
        except Exception:
            pending = {"entities": {}, "links": {}}

    pending_entities = pending.get("entities", {})
    pending_links = pending.get("links", {})

    if not pending_entities and not pending_links:
        return {
            "status": "success",
            "message": "No pending changes to approve",
            "approved_entities": 0,
            "approved_links": 0,
        }

    # Filter by selected UUIDs if provided
    selected_entity_uuids = None
    selected_link_uuids = None
    if data:
        selected_entity_uuids = data.get("entity_uuids")
        selected_link_uuids = data.get("link_uuids")

    if selected_entity_uuids:
        pending_entities = {k: v for k, v in pending_entities.items() if k in selected_entity_uuids}
    if selected_link_uuids:
        pending_links = {k: v for k, v in pending_links.items() if k in selected_link_uuids}

    # Build SessionOntology from pending changes
    delta = SessionOntology(
        entities={k: _dict_to_entity(v) for k, v in pending_entities.items()},
        links={k: _dict_to_link(v) for k, v in pending_links.items()},
    )

    # Load existing ontology from Neo4j and merge
    try:
        ontology_service = get_ontology_service()
        existing_ontology = ontology_service.load_ontology(thread_id)
        merged_ontology = merge_ontologies(existing_ontology, delta)
        ontology_service.save_ontology(thread_id, merged_ontology)
    except Exception as e:
        import logging
        logging.getLogger("agent_flow").error(f"[APPROVE] Failed to merge ontology: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to merge ontology: {str(e)}")

    # Remove approved changes from pending
    remaining_entities = {k: v for k, v in pending.get("entities", {}).items() if k not in pending_entities}
    remaining_links = {k: v for k, v in pending.get("links", {}).items() if k not in pending_links}

    db.sessions.update_one(
        {"thread_id": thread_id},
        {"$set": {
            "pending_ontology": {
                "entities": remaining_entities,
                "links": remaining_links,
            },
            "updated_at": datetime.utcnow(),
        }},
        upsert=True,
    )

    # Sync remaining pending back to LangGraph checkpointer
    try:
        from app.agents.graph import update_graph_pending_ontology
        update_graph_pending_ontology(thread_id, {
            "entities": remaining_entities,
            "links": remaining_links,
        })
    except Exception as sync_err:
        import logging
        logging.getLogger("agent_flow").warning(f"[APPROVE] Failed to sync graph state: {sync_err}")

    return {
        "status": "success",
        "approved_entities": len(pending_entities),
        "approved_links": len(pending_links),
        "remaining_entities": len(remaining_entities),
        "remaining_links": len(remaining_links),
    }


@router.post("/{thread_id}/pending-ontology/reject")
async def reject_pending_ontology(thread_id: str, data: Optional[Dict[str, Any]] = None):
    """
    Reject pending ontology changes (discard them).

    Optionally, specific entity/link UUIDs can be provided to reject only selected changes.
    If no UUIDs provided, all pending changes are rejected.
    """
    db = get_database()

    session = db.sessions.find_one({"thread_id": thread_id})
    if session:
        pending = session.get("pending_ontology", {"entities": {}, "links": {}})
    else:
        # Session not yet saved to MongoDB; try to read pending from LangGraph state
        try:
            from app.agents.graph import app_graph
            config = {"configurable": {"thread_id": thread_id}}
            current_state = app_graph.get_state(config)
            pending_state = current_state.values.get("pending_ontology")
            if pending_state and hasattr(pending_state, "model_dump"):
                pending = pending_state.model_dump(mode="json")
            elif pending_state and isinstance(pending_state, dict):
                pending = pending_state
            else:
                pending = {"entities": {}, "links": {}}
        except Exception:
            pending = {"entities": {}, "links": {}}

    pending_entities = pending.get("entities", {})
    pending_links = pending.get("links", {})

    if not pending_entities and not pending_links:
        return {
            "status": "success",
            "message": "No pending changes to reject",
            "rejected_entities": 0,
            "rejected_links": 0,
        }

    # Filter by selected UUIDs if provided
    selected_entity_uuids = None
    selected_link_uuids = None
    if data:
        selected_entity_uuids = data.get("entity_uuids")
        selected_link_uuids = data.get("link_uuids")

    if selected_entity_uuids:
        remaining_entities = {k: v for k, v in pending_entities.items() if k not in selected_entity_uuids}
    else:
        remaining_entities = {}

    if selected_link_uuids:
        remaining_links = {k: v for k, v in pending_links.items() if k not in selected_link_uuids}
    else:
        remaining_links = {}

    rejected_entity_count = len(pending_entities) - len(remaining_entities)
    rejected_link_count = len(pending_links) - len(remaining_links)

    db.sessions.update_one(
        {"thread_id": thread_id},
        {"$set": {
            "pending_ontology": {
                "entities": remaining_entities,
                "links": remaining_links,
            },
            "updated_at": datetime.utcnow(),
        }},
        upsert=True,
    )

    # Sync remaining pending back to LangGraph checkpointer
    try:
        from app.agents.graph import update_graph_pending_ontology
        update_graph_pending_ontology(thread_id, {
            "entities": remaining_entities,
            "links": remaining_links,
        })
    except Exception as sync_err:
        import logging
        logging.getLogger("agent_flow").warning(f"[REJECT] Failed to sync graph state: {sync_err}")

    return {
        "status": "success",
        "rejected_entities": rejected_entity_count,
        "rejected_links": rejected_link_count,
        "remaining_entities": len(remaining_entities),
        "remaining_links": len(remaining_links),
    }


@router.post("/{thread_id}/ontology/build")
async def build_ontology_from_conversation(thread_id: str):
    """
    Manual trigger: extract ontology from full conversation history.

    Re-runs ontology extraction on all messages in the session and adds to pending.
    """
    import logging
    logger = logging.getLogger("agent_flow")

    db = get_database()
    session = db.sessions.find_one({"thread_id": thread_id})
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {thread_id} not found")

    messages = session.get("messages", [])
    if not messages:
        return {
            "status": "success",
            "message": "No messages in session to process",
            "entities_extracted": 0,
            "links_extracted": 0,
        }

    # Build conversation context
    conversation_parts = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if role == "user":
            conversation_parts.append(f"User: {content}")
        elif role == "assistant":
            conversation_parts.append(f"Assistant: {content}")

    full_context = "\n\n".join(conversation_parts)

    try:
        from app.agents.ontology_subgraph import ontology_subgraph

        subgraph_input = {
            "user_query": full_context,
            "assistant_response": "",
            "query_id": thread_id,
        }

        subgraph_result = ontology_subgraph.invoke(subgraph_input)
        delta = subgraph_result.get("extracted_delta")

        if not delta or (not delta.entities and not delta.links):
            return {
                "status": "success",
                "message": "No new ontology extracted from conversation",
                "entities_extracted": 0,
                "links_extracted": 0,
            }

        # Serialize delta
        def serialize_entity(e):
            return e.model_dump(mode="json") if hasattr(e, "model_dump") else e

        def serialize_link(link):
            return link.model_dump(mode="json") if hasattr(link, "model_dump") else link

        new_entities = {str(k): serialize_entity(v) for k, v in delta.entities.items()}
        new_links = {str(k): serialize_link(v) for k, v in delta.links.items()}

        # Merge with existing pending
        existing_pending = session.get("pending_ontology", {"entities": {}, "links": {}})
        existing_pending["entities"].update(new_entities)
        existing_pending["links"].update(new_links)

        db.sessions.update_one(
            {"thread_id": thread_id},
            {"$set": {
                "pending_ontology": existing_pending,
                "updated_at": datetime.utcnow(),
            }},
        )

        logger.info(f"[ONTOLOGY_BUILD] Extracted {len(new_entities)} entities, {len(new_links)} links from conversation")

        return {
            "status": "success",
            "entities_extracted": len(new_entities),
            "links_extracted": len(new_links),
            "total_pending_entities": len(existing_pending["entities"]),
            "total_pending_links": len(existing_pending["links"]),
        }

    except Exception as e:
        logger.error(f"[ONTOLOGY_BUILD] Failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to build ontology: {str(e)}")


@router.post("/{thread_id}/discover-relationships")
async def discover_relationships_endpoint(thread_id: str, data: Dict[str, Any]):
    """
    Discover relationships between selected entities using LLM analysis.

    Analyzes existing ontology, conversation history, and source documents
    to find new relationships and intermediary entities.

    Discovered entities and links are added to pending ontology for review.
    """
    import logging
    logger = logging.getLogger("agent_flow")

    db = get_database()
    session = db.sessions.find_one({"thread_id": thread_id})
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {thread_id} not found")

    selected_uuids = data.get("entity_uuids", [])
    if not selected_uuids or len(selected_uuids) < 2:
        raise HTTPException(status_code=400, detail="At least 2 entities must be selected")

    messages = session.get("messages", [])
    pending = session.get("pending_ontology", {"entities": {}, "links": {}})

    try:
        graph_store = get_graph_store()
        vector_store = get_vector_store()

        discovered, prompt_text = discover_relationships(
            thread_id=thread_id,
            selected_uuids=selected_uuids,
            graph_store=graph_store,
            vector_store=vector_store,
            session_messages=messages,
            pending_ontology=pending,
        )

        if not discovered.entities and not discovered.links:
            return {
                "status": "success",
                "message": "No new relationships discovered",
                "entities_discovered": 0,
                "links_discovered": 0,
                "prompt": prompt_text,
            }

        # Serialize discovered ontology
        def serialize_entity(e):
            return e.model_dump(mode="json") if hasattr(e, "model_dump") else e

        def serialize_link(link):
            return link.model_dump(mode="json") if hasattr(link, "model_dump") else link

        new_entities = {str(k): serialize_entity(v) for k, v in discovered.entities.items()}
        new_links = {str(k): serialize_link(v) for k, v in discovered.links.items()}

        # Merge with existing pending
        existing_pending = session.get("pending_ontology", {"entities": {}, "links": {}})
        existing_pending["entities"].update(new_entities)
        existing_pending["links"].update(new_links)

        db.sessions.update_one(
            {"thread_id": thread_id},
            {"$set": {
                "pending_ontology": existing_pending,
                "updated_at": datetime.utcnow(),
            }},
        )

        logger.info(
            f"[DISCOVER_RELATIONSHIPS] Discovered {len(new_entities)} entities, {len(new_links)} links"
        )

        return {
            "status": "success",
            "entities_discovered": len(new_entities),
            "links_discovered": len(new_links),
            "total_pending_entities": len(existing_pending["entities"]),
            "total_pending_links": len(existing_pending["links"]),
            "discovered_entities": new_entities,
            "discovered_links": new_links,
            "prompt": prompt_text,
        }

    except Exception as e:
        logger.error(f"[DISCOVER_RELATIONSHIPS] Failed: {e}")
        raise HTTPException(status_code=500, detail=f"Relationship discovery failed: {str(e)}")


@router.get("/{thread_id}/documents")
async def list_session_documents(thread_id: str):
    """
    List ingested documents for a session.

    Returns documents that have been uploaded/ingested and are available for RAG.
    """
    import os
    import glob

    documents_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "documents")

    if not os.path.exists(documents_dir):
        return {
            "thread_id": thread_id,
            "documents": [],
            "count": 0,
        }

    documents = []
    for filepath in glob.glob(os.path.join(documents_dir, "**/*"), recursive=True):
        if os.path.isfile(filepath):
            rel_path = os.path.relpath(filepath, documents_dir)
            stat = os.stat(filepath)
            documents.append({
                "name": os.path.basename(filepath),
                "path": rel_path,
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })

    documents.sort(key=lambda d: d["modified"], reverse=True)

    return {
        "thread_id": thread_id,
        "documents": documents,
        "count": len(documents),
    }


def _dict_to_entity(data: dict):
    """Convert dict to OntologyEntity."""
    from app.models.ontology import OntologyEntity, Mention
    from uuid import UUID

    mentions = []
    for m in data.get("mentions", []):
        if isinstance(m, dict):
            mentions.append(Mention(
                source_text=m.get("source_text", ""),
                extracted_at=datetime.fromisoformat(m.get("extracted_at", datetime.utcnow().isoformat())),
                confidence=m.get("confidence", 1.0),
                thread_id=m.get("thread_id"),
            ))

    properties = data.get("properties", {})
    if isinstance(properties, str):
        import json
        try:
            properties = json.loads(properties)
        except (json.JSONDecodeError, ValueError):
            properties = {}

    created_at_str = data.get("created_at", datetime.utcnow().isoformat())
    updated_at_str = data.get("updated_at", datetime.utcnow().isoformat())

    try:
        created_at = datetime.fromisoformat(created_at_str)
    except (ValueError, TypeError):
        created_at = datetime.utcnow()

    try:
        updated_at = datetime.fromisoformat(updated_at_str)
    except (ValueError, TypeError):
        updated_at = datetime.utcnow()

    return OntologyEntity(
        uuid=UUID(data.get("uuid")),
        name=data.get("name", ""),
        type=data.get("type", ""),
        properties=properties,
        mentions=mentions,
        created_at=created_at,
        updated_at=updated_at,
        created_by=data.get("created_by", "llm_extractor"),
    )


def _dict_to_link(data: dict):
    """Convert dict to OntologyLink."""
    from app.models.ontology import OntologyLink, Mention
    from uuid import UUID

    mentions = []
    for m in data.get("mentions", []):
        if isinstance(m, dict):
            mentions.append(Mention(
                source_text=m.get("source_text", ""),
                extracted_at=datetime.fromisoformat(m.get("extracted_at", datetime.utcnow().isoformat())),
                confidence=m.get("confidence", 1.0),
                thread_id=m.get("thread_id"),
            ))

    properties = data.get("properties", {})
    if isinstance(properties, str):
        import json
        try:
            properties = json.loads(properties)
        except (json.JSONDecodeError, ValueError):
            properties = {}

    created_at_str = data.get("created_at", datetime.utcnow().isoformat())
    updated_at_str = data.get("updated_at", datetime.utcnow().isoformat())

    try:
        created_at = datetime.fromisoformat(created_at_str)
    except (ValueError, TypeError):
        created_at = datetime.utcnow()

    try:
        updated_at = datetime.fromisoformat(updated_at_str)
    except (ValueError, TypeError):
        updated_at = datetime.utcnow()

    return OntologyLink(
        uuid=UUID(data.get("uuid")),
        source_uuid=UUID(data.get("source_uuid")),
        target_uuid=UUID(data.get("target_uuid")),
        type=data.get("type", ""),
        properties=properties,
        mentions=mentions,
        created_at=created_at,
        updated_at=updated_at,
    )
