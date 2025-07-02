import os
import json
import time
import requests
from typing import Any, Dict, Optional, List, Set
import numpy as np
import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request, UploadFile, File
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sklearn.decomposition import PCA

from app.config import (
    EMBEDDINGS_CACHE_FILE, 
    ENABLE_IMAGE_SEARCH,
    GOOGLE_KEEP_PATH, 
    HOST, 
    PORT, 
    NOTES_CACHE_FILE, 
    CACHE_DIR,
    LLM_MODEL
)
from app.parser import parse_notes, get_latest_modification_time
from app.search import VibeSearch
from app.chatbot import ChatBot

app = FastAPI(title="Google Keep Vibe Search")


# Initialize search on startup
notes = []
search_engine = None
chatbot = None
note_tags = {}  # Dict[note_id, tag_name]
excluded_tags = set()  # Set[tag_name]

TAGS_CACHE_FILE = os.path.join(CACHE_DIR, "tags.json")
EXCLUDED_TAGS_CACHE_FILE = os.path.join(CACHE_DIR, "excluded_tags.json")


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


def load_tags_from_cache() -> Dict[str, str]:
    """Load note tags from cache file."""
    if os.path.exists(TAGS_CACHE_FILE):
        try:
            with open(TAGS_CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def save_tags_to_cache(tags_data: Dict[str, str]) -> None:
    """Save note tags to cache file."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    try:
        with open(TAGS_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(tags_data, f)
    except IOError:
        pass


def load_excluded_tags_from_cache() -> Set[str]:
    """Load excluded tags from cache file."""
    if os.path.exists(EXCLUDED_TAGS_CACHE_FILE):
        try:
            with open(EXCLUDED_TAGS_CACHE_FILE, 'r', encoding='utf-8') as f:
                return set(json.load(f))
        except (json.JSONDecodeError, IOError):
            pass
    return set()


def save_excluded_tags_to_cache(excluded: Set[str]) -> None:
    """Save excluded tags to cache file."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    try:
        with open(EXCLUDED_TAGS_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(list(excluded), f)
    except IOError:
        pass


def filter_notes_by_excluded_tags(notes_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filter out notes that have excluded tags."""
    global note_tags, excluded_tags
    if not excluded_tags:
        return notes_list
    
    filtered_notes = []
    for note in notes_list:
        note_id = note.get("id")
        note_tag = note_tags.get(note_id)
        if not note_tag or note_tag not in excluded_tags:
            filtered_notes.append(note)
    
    return filtered_notes


@app.on_event("startup")
async def startup_event():
    global notes, search_engine, chatbot, note_tags, excluded_tags
    
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
    
    # Load tags and excluded tags from cache
    note_tags = load_tags_from_cache()
    excluded_tags = load_excluded_tags_from_cache()
    
    # Display image search status
    if ENABLE_IMAGE_SEARCH:
        print("Image search capability is enabled")
    else:
        print("Image search capability is disabled (set ENABLE_IMAGE_SEARCH=true in .env to enable)")
    
    # Initialize the chatbot
    chatbot = ChatBot(search_engine)
    print(f"Initialized chatbot with model: {LLM_MODEL}")
    print(f"Loaded {len(note_tags)} note tags and {len(excluded_tags)} excluded tags")


class SearchRequest(BaseModel):
    query: str


class TagNotesRequest(BaseModel):
    note_ids: List[str]
    tag_name: str


class TagManagementRequest(BaseModel):
    excluded_tags: List[str]


class RemoveTagRequest(BaseModel):
    tag_name: str


@app.get("/api/search")
def search(q: str = ""):
    global search_engine
    if not search_engine:
        return {"error": "Search engine not initialized"}

    results = search_engine.search(q)
    # Filter out notes with excluded tags
    filtered_results = filter_notes_by_excluded_tags(results)
    return {"results": filtered_results}


@app.post("/api/search")
def search_post(request: SearchRequest):
    global search_engine
    if not search_engine:
        return {"error": "Search engine not initialized"}

    results = search_engine.search(request.query)
    # Filter out notes with excluded tags
    filtered_results = filter_notes_by_excluded_tags(results)
    return {"results": filtered_results}


@app.post("/api/search/image")
async def search_by_image(file: UploadFile = File(...)):
    """
    Search notes using an uploaded image as the query.
    
    Args:
        file: The uploaded image file
        
    Returns:
        JSON response with search results
    """
    global search_engine
    
    if not search_engine:
        raise HTTPException(status_code=500, detail="Search engine not initialized")
        
    if not ENABLE_IMAGE_SEARCH:
        raise HTTPException(status_code=400, detail="Image search is not enabled")
        
    if not search_engine.image_processor:
        raise HTTPException(status_code=500, detail="Image processor not initialized")
    
    # Check if the uploaded file is an image
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Uploaded file is not an image")
    
    try:
        # Get file content
        contents = await file.read()
        
        # Create a temporary file for the image processor to read
        temp_file_path = os.path.join(CACHE_DIR, "temp_search_image")
        with open(temp_file_path, "wb") as f:
            f.write(contents)
        
        # Search using the temporary file
        results = search_engine.search_by_image(temp_file_path)
        
        # Clean up the temporary file
        os.remove(temp_file_path)
        
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error searching by image: {str(e)}")


@app.get("/api/all-notes")
def get_all_notes():
    """Return all notes."""
    global notes, note_tags
    all_notes = []
    
    for note in notes:
        # Create a copy of the note data to avoid modifying the original
        note_with_score = note.copy()
        note_with_score["score"] = 1.0  # All notes have full relevance when showing all
        
        # Add tag information if available
        note_id = note_with_score.get("id")
        if note_id and note_id in note_tags:
            note_with_score["tag"] = note_tags[note_id]
        
        # Remove matched_image field if it exists (only relevant for search results)
        if "matched_image" in note_with_score:
            del note_with_score["matched_image"]
            
        all_notes.append(note_with_score)
    
    # Filter out notes with excluded tags
    filtered_notes = filter_notes_by_excluded_tags(all_notes)
    return {"notes": filtered_notes}


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
    global notes, search_engine
    
    image_search_status = {
        "enabled": ENABLE_IMAGE_SEARCH,
        "initialized": search_engine and hasattr(search_engine, "image_processor") and search_engine.image_processor is not None,
        "images_count": len(search_engine.image_note_map) if search_engine and hasattr(search_engine, "image_note_map") else 0
    }
    
    return {
        "total_notes": len(notes),
        "archived_notes": sum(1 for note in notes if note.get("archived", False)),
        "pinned_notes": sum(1 for note in notes if note.get("pinned", False)),
        "using_cached_embeddings": os.path.exists(EMBEDDINGS_CACHE_FILE),
        "image_search": image_search_status
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


# Chat-related models and endpoints
class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    stream: bool = False
    useNotesContext: bool = True
    topic: Optional[str] = None  # Optional topic field for context search


class ChatResponse(BaseModel):
    response: str
    notes: List[Dict[str, Any]]


@app.post("/api/chat")
async def chat(request: ChatRequest):
    """Generate a chat response using Ollama."""
    global chatbot
    if not chatbot:
        raise HTTPException(status_code=500, detail="Chatbot not initialized")

    try:
        # Convert the Pydantic models to dict for the chatbot
        messages = [msg.dict() for msg in request.messages]
        
        if not request.stream:
            # Non-streaming response - return normal JSON
            response_text, relevant_notes = chatbot.generate_chat_completion(
                messages, 
                stream=False,
                use_notes_context=request.useNotesContext,
                topic=request.topic
            )
            
            return ChatResponse(
                response=response_text,
                notes=relevant_notes if request.useNotesContext else []
            )
        else:
            # Streaming response - use StreamingResponse
            return StreamingResponse(
                stream_chat_response(
                    chatbot, 
                    messages, 
                    use_notes_context=request.useNotesContext,
                    topic=request.topic
                ),
                media_type="application/json"
            )
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating chat response: {str(e)}")


async def stream_chat_response(chatbot_instance, messages, use_notes_context=True, topic=None):
    """Stream the chat response from the Ollama API."""
    try:
        # Extract the latest user query for finding relevant notes
        latest_user_message = next((msg["content"] for msg in reversed(messages) 
                                  if msg["role"] == "user"), "")
        
        # Find relevant notes for the latest user query if useNotesContext is True
        relevant_notes = []
        if use_notes_context:
            # Use topic for search if provided, otherwise use latest message
            search_query = topic if topic else latest_user_message
            if search_query:
                relevant_notes = chatbot_instance.get_relevant_notes(search_query)
        
        # Set up Ollama API request with streaming
        response = requests.post(
            f"{chatbot_instance.api_url}/api/chat",
            headers={"Content-Type": "application/json"},
            json={
                "model": chatbot_instance.model,
                "messages": chatbot_instance.prepare_messages_with_context(
                    messages, 
                    relevant_notes if use_notes_context else []
                ),
                "stream": True
            },
            stream=True
        )
        
        response.raise_for_status()
        
        # Stream the response chunks
        accumulated_text = ""
        for line in response.iter_lines():
            if line:
                try:
                    data = json.loads(line)
                    if "message" in data and "content" in data["message"]:
                        chunk = data["message"]["content"]
                        accumulated_text += chunk
                        
                        # Yield the accumulated text and relevant notes
                        yield json.dumps({
                            "response": accumulated_text,
                            "notes": relevant_notes if use_notes_context else []
                        }).encode() + b"\n"
                except json.JSONDecodeError:
                    continue
                    
    except Exception as e:
        # If there's an error, yield it as part of the stream
        yield json.dumps({
            "error": str(e),
            "notes": []
        }).encode() + b"\n"


@app.get("/api/chat/model")
def get_chat_model():
    """Return the current LLM model being used."""
    return {"model": LLM_MODEL}


@app.post("/api/notes/tag")
def tag_notes(request: TagNotesRequest):
    """Tag selected notes with a given tag name."""
    global note_tags
    
    # Validate that all note IDs exist
    valid_note_ids = {note["id"] for note in notes}
    invalid_ids = [note_id for note_id in request.note_ids if note_id not in valid_note_ids]
    
    if invalid_ids:
        raise HTTPException(status_code=400, detail=f"Invalid note IDs: {invalid_ids}")
    
    # Apply tags to notes
    for note_id in request.note_ids:
        note_tags[note_id] = request.tag_name
    
    # Save to cache
    save_tags_to_cache(note_tags)
    
    return {"message": f"Tagged {len(request.note_ids)} notes with '{request.tag_name}'"}


@app.get("/api/tags")
def get_all_tags():
    """Get all available tags and their note counts."""
    global note_tags
    
    tag_counts = {}
    for tag_name in note_tags.values():
        tag_counts[tag_name] = tag_counts.get(tag_name, 0) + 1
    
    tags = [{"name": tag_name, "count": count} for tag_name, count in tag_counts.items()]
    tags.sort(key=lambda x: x["name"])
    
    return {"tags": tags}


@app.get("/api/tags/excluded")
def get_excluded_tags():
    """Get currently excluded tags."""
    global excluded_tags
    return {"excluded_tags": list(excluded_tags)}


@app.post("/api/tags/excluded")
def set_excluded_tags(request: TagManagementRequest):
    """Set which tags should be excluded from search results."""
    global excluded_tags
    
    excluded_tags = set(request.excluded_tags)
    save_excluded_tags_to_cache(excluded_tags)
    
    return {"message": f"Updated excluded tags: {list(excluded_tags)}"}


@app.delete("/api/notes/{note_id}/tag")
def remove_note_tag(note_id: str):
    """Remove tag from a specific note."""
    global note_tags
    
    if note_id not in note_tags:
        raise HTTPException(status_code=404, detail="Note is not tagged")
    
    removed_tag = note_tags.pop(note_id)
    save_tags_to_cache(note_tags)
    
    return {"message": f"Removed tag '{removed_tag}' from note {note_id}"}


@app.post("/api/tags/remove")
def remove_tag_from_all_notes(request: RemoveTagRequest):
    """Remove a specific tag from all notes that have it."""
    global note_tags
    
    # Find all note IDs that have this tag
    notes_to_update = [note_id for note_id, tag_name in note_tags.items() if tag_name == request.tag_name]
    
    if not notes_to_update:
        raise HTTPException(status_code=404, detail=f"No notes found with tag '{request.tag_name}'")
    
    # Remove the tag from all notes that have it
    for note_id in notes_to_update:
        del note_tags[note_id]
    
    # Save to cache
    save_tags_to_cache(note_tags)
    
    return {"message": f"Removed tag '{request.tag_name}' from {len(notes_to_update)} notes"}


if __name__ == "__main__":
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=True)
