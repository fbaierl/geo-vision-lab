import uuid
import json
from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse, StreamingResponse
from app.agents.graph import process_query, process_query_stream

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

    async def event_generator():
        # Send session metadata first
        meta = json.dumps({"type": "meta", "thread_id": session_id})
        yield f"data: {meta}\n\n"

        try:
            async for evt in process_query_stream(query, thread_id=session_id):
                data = json.dumps(evt)
                yield f"data: {data}\n\n"
        except Exception as e:
            print(f"[ERROR] Stream failed: {e}")
            err = json.dumps({"type": "error", "content": str(e)})
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
