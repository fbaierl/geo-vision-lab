import uuid
import json
import logging
from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse, StreamingResponse
from app.agents.graph import process_query, process_query_stream

logger = logging.getLogger("geovision_api")

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
    
    logger.info(f"▸ QUERY RECEIVED: '{query[:100]}{'...' if len(query) > 100 else ''}' [thread={session_id}]")

    async def event_generator():
        # Send session metadata first
        meta = json.dumps({"type": "meta", "thread_id": session_id})
        yield f"data: {meta}\n\n"

        try:
            async for evt in process_query_stream(query, thread_id=session_id):
                # Log events for visibility in Dozzle
                event_type = evt.get("type", "unknown")
                
                if event_type == "status":
                    phase = evt.get("phase", "unknown")
                    model = evt.get("model", "")
                    tool = evt.get("tool", "")
                    query_used = evt.get("query", "")
                    
                    if phase in ["reasoning", "reviewing", "revising"]:
                        logger.info(f"  ┝━ [{phase.upper()}] LLM: {model}")
                    elif phase in ["vector_search", "online_search"]:
                        logger.info(f"  ┝━ [{phase.upper()}] Tool: {tool} | Query: '{query_used[:50]}{'...' if len(query_used) > 50 else ''}'")
                    elif phase == "streaming":
                        logger.debug("  ┝━ [STREAMING] Sending response to client...")
                
                elif event_type == "tool_result":
                    tool_name = evt.get("tool", "unknown")
                    summary = evt.get("summary", "")
                    citations = evt.get("citations", [])
                    citation_info = ""
                    if citations:
                        citation_info = f" | Citations: {len(citations)}"
                    logger.info(f"  ┝━ [TOOL RESULT] {tool_name}: {summary}{citation_info}")
                
                elif event_type == "token":
                    # Only log first token to avoid spam
                    pass  # Tokens are logged in aggregate below
                
                data = json.dumps(evt)
                yield f"data: {data}\n\n"
            
            logger.info(f"▸ RESPONSE COMPLETE [thread={session_id}]")
            
        except Exception as e:
            logger.error(f"▸ STREAM ERROR: {e}")
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
