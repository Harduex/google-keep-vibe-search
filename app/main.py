import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from typing import Dict, Any
import os

from app.parser import parse_notes
from app.search import VibeSearch
from app.config import HOST, PORT, EMBEDDINGS_CACHE_FILE, GOOGLE_KEEP_PATH

app = FastAPI(title="Google Keep Vibe Search")

# Setup static file serving and templates
script_dir = os.path.dirname(os.path.realpath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(script_dir, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(script_dir, "templates"))

# Initialize search on startup
notes = []
search_engine = None

@app.on_event("startup")
async def startup_event():
    global notes, search_engine
    notes = parse_notes()
    search_engine = VibeSearch(notes)
    print(f"Loaded {len(notes)} notes from Google Keep export")

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/search")
def search(q: str = ""):
    global search_engine
    if not search_engine:
        return {"error": "Search engine not initialized"}
    
    results = search_engine.search(q)
    return {"results": results}

@app.get("/api/stats")
def stats():
    global notes
    return {
        "total_notes": len(notes),
        "archived_notes": sum(1 for note in notes if note.get("archived", False)),
        "pinned_notes": sum(1 for note in notes if note.get("pinned", False)),
        "using_cached_embeddings": os.path.exists(EMBEDDINGS_CACHE_FILE)
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