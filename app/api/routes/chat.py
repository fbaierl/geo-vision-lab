import uuid
import json
from datetime import datetime
from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse, StreamingResponse
from app.agents.graph import process_query, process_query_stream


class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles datetime objects."""
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


def json_dumps(obj):
    """Serialize object to JSON, handling datetime objects."""
    return json.dumps(obj, cls=DateTimeEncoder)


router = APIRouter()


@router.post("/chat")
async def chat_endpoint(
    query: str = Form(...),
    thread_id: str = Form(None),
):
    """Non-streaming chat endpoint (kept for backwards compatibility)."""
    if not query or query.strip() == "":
        return JSONResponse({"answer": "Empty transmission."}, status_code=400)

    session_id = thread_id if thread_id else str(uuid.uuid4())

    try:
        response_text = process_query(query, thread_id=session_id)
        return {"answer": response_text, "thread_id": session_id}
    except Exception as e:
        print(f"[ERROR] Agent execution failed: {e}")
        return JSONResponse(
            {"answer": f"System error during analysis: {str(e)}"}, status_code=500
        )


@router.post("/chat/stream")
async def chat_stream_endpoint(
    query: str = Form(...),
    thread_id: str = Form(None),
):
    """Streaming chat endpoint using Server-Sent Events (SSE)."""
    if not query or query.strip() == "":
        return JSONResponse({"answer": "Empty transmission."}, status_code=400)

    session_id = thread_id if thread_id else str(uuid.uuid4())
    
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"[CHAT_STREAM] >>> Starting stream endpoint (query='{query[:50]}...', thread={session_id})")

    async def event_generator():
        # Send session metadata first
        meta = json_dumps({"type": "meta", "thread_id": session_id})
        logger.info(f"[CHAT_STREAM] Sending metadata: thread_id={session_id}")
        yield f"data: {meta}\n\n"

        try:
            logger.info(f"[CHAT_STREAM] >>> Starting event generator loop")
            event_count = 0
            async for evt in process_query_stream(query, thread_id=session_id):
                event_count += 1
                evt_type = evt.get("type", "unknown")
                logger.info(f"[CHAT_STREAM] Event #{event_count}: type={evt_type}")
                data = json_dumps(evt)
                yield f"data: {data}\n\n"
            logger.info(f"[CHAT_STREAM] <<< Event generator complete ({event_count} events)")
        except Exception as e:
            logger.error(f"[CHAT_STREAM] ✗ Stream failed: {e}")
            logger.exception("[CHAT_STREAM] Full stack trace:")
            err = json_dumps({"type": "error", "content": str(e)})
            yield f"data: {err}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
