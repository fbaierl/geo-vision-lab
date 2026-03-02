from fastapi import FastAPI, Form
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
async def chat_endpoint(query: str = Form(...)):
    """Accepts a query from the frontend and passes it to the LangGraph agent."""
    if not query or query.strip() == "":
        return JSONResponse({"answer": "Empty transmission. Please provide a valid query."}, status_code=400)
    
    try:
        # Run the agent processing
        response_text = process_query(query)
        return {"answer": response_text}
    except Exception as e:
        print(f"[ERROR] Agent execution failed: {e}")
        return JSONResponse({"answer": f"System error during analysis: {str(e)}"}, status_code=500)

if __name__ == "__main__":
    import uvicorn
    # When run directly (useful for local testing outside Docker)
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
