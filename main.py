import uuid
import json
import os

import httpx
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

# Import our custom LangGraph agent workflow
from agent import process_query, process_query_stream

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://geovision-ollama:11434")

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
    except Exception:
        return "<h1>GeoVision Lab UI not found.</h1><p>Please ensure static/index.html exists.</p>"


@app.get("/system/status")
async def system_status():
    """Return system status including GPU engagement from Ollama."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{OLLAMA_HOST}/api/ps")
            data = resp.json()
            models = data.get("models", [])
            if models:
                model_info = models[0]
                vram_bytes = model_info.get("size_vram", 0)
                return {
                    "gpu_engaged": vram_bytes > 0,
                    "model": model_info.get("name", "unknown"),
                    "vram_bytes": vram_bytes,
                }
            return {"gpu_engaged": False, "model": None, "reason": "no model loaded"}
    except Exception as e:
        return {"gpu_engaged": False, "model": None, "reason": str(e)}


@app.post("/chat")
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


@app.post("/chat/stream")
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
            async for token in process_query_stream(query, thread_id=session_id):
                data = json.dumps({"type": "token", "content": token})
                yield f"data: {data}\n\n"

            done = json.dumps({"type": "done"})
            yield f"data: {done}\n\n"
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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
