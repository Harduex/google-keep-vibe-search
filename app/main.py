import os
from typing import Any, Dict

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.config import EMBEDDINGS_CACHE_FILE, GOOGLE_KEEP_PATH, HOST, PORT
from app.parser import parse_notes
from app.search import VibeSearch

app = FastAPI(title="Google Keep Vibe Search")


# Initialize search on startup
notes = []
search_engine = None


@app.on_event("startup")
async def startup_event():
    global notes, search_engine
    notes = parse_notes()
    search_engine = VibeSearch(notes)
    print(f"Loaded {len(notes)} notes from Google Keep export")


class SearchRequest(BaseModel):
    query: str


@app.get("/api/search")
def search(q: str = ""):
    global search_engine
    if not search_engine:
        return {"error": "Search engine not initialized"}

    results = search_engine.search(q)
    return {"results": results}


@app.post("/api/search")
def search_post(request: SearchRequest):
    global search_engine
    if not search_engine:
        return {"error": "Search engine not initialized"}

    results = search_engine.search(request.query)
    return {"results": results}


@app.get("/api/stats")
def stats():
    global notes
    return {
        "total_notes": len(notes),
        "archived_notes": sum(1 for note in notes if note.get("archived", False)),
        "pinned_notes": sum(1 for note in notes if note.get("pinned", False)),
        "using_cached_embeddings": os.path.exists(EMBEDDINGS_CACHE_FILE),
    }


@app.get("/api/image/{image_path:path}")
async def get_image(image_path: str):
    """Serve image attachments from Google Keep directory."""
    full_path = os.path.join(GOOGLE_KEEP_PATH, image_path)

    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="Image not found")

    return FileResponse(full_path)


if __name__ == "__main__":
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=True)
