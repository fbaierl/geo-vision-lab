import uuid

from fastapi import FastAPI, Form, Cookie
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import os

# Import our custom LangGraph agent workflow
from agent import process_query

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
    """Accepts a query from the frontend and passes it to the LangGraph agent.

    The thread_id groups messages into a conversational session so the agent
    can handle follow-up questions contextually.  If not supplied, a new
    thread is created.
    """
    if not query or query.strip() == "":
        return JSONResponse({"answer": "Empty transmission. Please provide a valid query."}, status_code=400)

    # Use the provided thread_id or generate a new one
    session_id = thread_id if thread_id else str(uuid.uuid4())

    try:
        # Run the agent processing with conversational memory
        response_text = process_query(query, thread_id=session_id)
        return {"answer": response_text, "thread_id": session_id}
    except Exception as e:
        print(f"[ERROR] Agent execution failed: {e}")
        return JSONResponse({"answer": f"System error during analysis: {str(e)}"}, status_code=500)

if __name__ == "__main__":
    import uvicorn
    # When run directly (useful for local testing outside Docker)
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
