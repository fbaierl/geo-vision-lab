import uuid

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import os

# Import our custom LangGraph agent workflow
from agent import process_query, process_query_stream

app = FastAPI(title="GeoVision Lab API")

# Ensure static directories exist
os.makedirs("static", exist_ok=True)

# Mount static files to serve the frontend
app.mount("/ui", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def read_root():
    """Serve the main tactical interface on root."""
    try:
        with open("static/index.html", "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"<h1>GeoVision Lab UI not found.</h1><p>Please ensure static/index.html exists.</p>"

@app.post("/chat")
async def chat_endpoint(
    query: str = Form(...),
    thread_id: str = Form(None),
):
    """Non-streaming chat endpoint (kept for backwards compatibility)."""
    if not query or query.strip() == "":
        return JSONResponse({"answer": "Empty transmission. Please provide a valid query."}, status_code=400)

    session_id = thread_id if thread_id else str(uuid.uuid4())

    try:
        response_text = process_query(query, thread_id=session_id)
        return {"answer": response_text, "thread_id": session_id}
    except Exception as e:
        print(f"[ERROR] Agent execution failed: {e}")
        return JSONResponse({"answer": f"System error during analysis: {str(e)}"}, status_code=500)


@app.post("/chat/stream")
async def chat_stream_endpoint(
    query: str = Form(...),
    thread_id: str = Form(None),
):
    """Streaming chat endpoint using Server-Sent Events (SSE).

    Streams individual text chunks as they arrive from the LLM,
    enabling a live typewriter effect in the frontend.
    """
    if not query or query.strip() == "":
        return JSONResponse({"answer": "Empty transmission."}, status_code=400)

    session_id = thread_id if thread_id else str(uuid.uuid4())

    async def event_generator():
        # First, send the session thread_id so the frontend can track it
        yield f"data: {{\\"type\\": \\"meta\\", \\"thread_id\\": \\"{session_id}\\"}}\n\n"

        try:
            async for token in process_query_stream(query, thread_id=session_id):
                # Escape newlines for SSE (each data: line must be single-line)
                escaped = token.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
                yield f"data: {{\\"type\\": \\"token\\", \\"content\\": \\"{escaped}\\"}}\n\n"

            yield f"data: {{\\"type\\": \\"done\\"}}\n\n"
        except Exception as e:
            print(f"[ERROR] Stream failed: {e}")
            escaped_err = str(e).replace('"', '\\"')
            yield f"data: {{\\"type\\": \\"error\\", \\"content\\": \\"{escaped_err}\\"}}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
