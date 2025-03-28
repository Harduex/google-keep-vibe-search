import os
import json
import time
from typing import Any, Dict, Optional, List

import numpy as np
import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sklearn.decomposition import PCA

from app.config import EMBEDDINGS_CACHE_FILE, GOOGLE_KEEP_PATH, HOST, PORT, NOTES_CACHE_FILE, CACHE_DIR
from app.parser import parse_notes, get_latest_modification_time
from app.search import VibeSearch

app = FastAPI(title="Google Keep Vibe Search")


# Initialize search on startup
notes = []
search_engine = None


def save_notes_to_cache(notes_data: List[Dict[str, Any]]) -> None:
    """Save notes data to cache file."""
    # Ensure cache directory exists
    os.makedirs(CACHE_DIR, exist_ok=True)
    
    cache_data = {
        "timestamp": time.time(),
        "notes": notes_data
    }
    
    try:
        with open(NOTES_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f)
        print(f"Notes cached to {NOTES_CACHE_FILE}")
    except Exception as e:
        print(f"Error caching notes: {e}")


def load_notes_from_cache() -> List[Dict[str, Any]]:
    """Load notes data from cache if available and valid."""
    if not os.path.exists(NOTES_CACHE_FILE):
        return None
        
    try:
        with open(NOTES_CACHE_FILE, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
            
        cache_timestamp = cache_data.get("timestamp", 0)
        notes_data = cache_data.get("notes", [])
        
        # Check if source data is newer than cache
        latest_mod_time = get_latest_modification_time(GOOGLE_KEEP_PATH)
        
        if latest_mod_time > cache_timestamp:
            print("Source notes modified since last cache, will re-parse")
            return None
            
        return notes_data
    except Exception as e:
        print(f"Error loading notes from cache: {e}")
        return None


@app.on_event("startup")
async def startup_event():
    global notes, search_engine
    
    # Try to load notes from cache first
    cached_notes = load_notes_from_cache()
    
    if cached_notes:
        notes = cached_notes
        print(f"Loaded {len(notes)} notes from cache")
    else:
        # Parse notes from source files
        notes = parse_notes()
        print(f"Parsed {len(notes)} notes from Google Keep export")
        
        # Cache the parsed notes for future use
        save_notes_to_cache(notes)
    
    # Initialize the search engine
    search_engine = VibeSearch(notes)


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


@app.get("/api/all-notes")
def get_all_notes():
    """Return all notes."""
    global notes
    if not notes:
        raise HTTPException(status_code=500, detail="Notes not loaded")
    
    # Add a default score of 0 to each note to match the search results format
    all_notes = []
    for note in notes:
        note_with_score = note.copy()
        note_with_score["score"] = 0.0
        all_notes.append(note_with_score)
        
    return {"notes": all_notes}


@app.get("/api/clusters")
def get_clusters(num_clusters: Optional[int] = None):
    """Return clustered notes."""
    global search_engine
    if not search_engine:
        raise HTTPException(status_code=500, detail="Search engine not initialized")

    try:
        clusters = search_engine.get_clusters(num_clusters)
        return {"clusters": clusters}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error clustering notes: {str(e)}")


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


@app.get("/api/embeddings")
def get_embeddings():
    """Return embeddings for visualization with dimensionality reduction."""
    global search_engine
    if not search_engine:
        raise HTTPException(status_code=500, detail="Search engine not initialized")

    try:
        # Get embeddings and corresponding note indices from the search engine
        embeddings = search_engine.embeddings
        note_indices = search_engine.note_indices

        # Apply PCA to reduce dimensions to 3D for visualization
        pca = PCA(n_components=3)
        embeddings_3d = pca.fit_transform(embeddings)

        # Convert to list for JSON serialization
        embeddings_data = []
        for i, note_idx in enumerate(note_indices):
            embeddings_data.append(
                {
                    "id": search_engine.notes[note_idx]["id"],
                    "title": search_engine.notes[note_idx]["title"],
                    "content": search_engine.notes[note_idx]["content"],
                    "coordinates": embeddings_3d[i].tolist(),
                }
            )

        return {"embeddings": embeddings_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating embeddings: {str(e)}")


if __name__ == "__main__":
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=True)
