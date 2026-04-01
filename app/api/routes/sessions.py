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

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


class SessionCreate(BaseModel):
    title: Optional[str] = None


class SessionUpdate(BaseModel):
    title: Optional[str] = None
    ontology: Optional[Dict[str, Any]] = None
    messages: Optional[List[Dict[str, Any]]] = None


class SessionSave(BaseModel):
    messages: List[Dict[str, Any]] = Field(default_factory=list)
    ontology: Dict[str, Any] = Field(default_factory=dict)


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
        "ontology": {"entities": {}, "links": {}},
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
        }

    return {
        "thread_id": session.get("thread_id", thread_id),
        "title": session.get("title", "Untitled"),
        "created_at": session.get("created_at"),
        "updated_at": session.get("updated_at"),
        "messages": session.get("messages", []),
        "ontology": session.get("ontology", {"entities": {}, "links": {}}),
    }


@router.put("/{thread_id}")
async def update_session(thread_id: str, data: SessionUpdate):
    """
    Update session title, ontology, or messages.
    """
    db = get_database()

    update_fields = {}
    if data.title is not None:
        update_fields["title"] = data.title
    if data.ontology is not None:
        update_fields["ontology"] = data.ontology
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

    Upserts session with current messages and ontology.
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
        "ontology": data.ontology,
    }

    # Try to find existing session first
    existing = db.sessions.find_one({"thread_id": thread_id})

    if existing:
        # Update existing session
        db.sessions.update_one(
            {"thread_id": thread_id},
            {
                "$set": {
                    "messages": data.messages,
                    "ontology": data.ontology,
                    "updated_at": now,
                    "title": title,  # Keep title updated from latest query
                }
            },
        )
    else:
        # Create new session
        db.sessions.insert_one(session_doc)

    return {
        "status": "success",
        "thread_id": thread_id,
        "message_count": len(data.messages),
        "entity_count": len(data.ontology.get("entities", {})),
        "link_count": len(data.ontology.get("links", {})),
    }
