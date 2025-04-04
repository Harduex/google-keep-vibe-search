import os
import json
import time
import requests
from typing import Any, Dict, Optional, List
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
    ENABLE_AI_AGENT_MODE,
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
    global notes, search_engine, chatbot
    
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
    
    # Display image search status
    if ENABLE_IMAGE_SEARCH:
        print("Image search capability is enabled")
    else:
        print("Image search capability is disabled (set ENABLE_IMAGE_SEARCH=true in .env to enable)")
    
    # Initialize the chatbot
    chatbot = ChatBot(search_engine)
    print(f"Initialized chatbot with model: {LLM_MODEL}")
    
    # Display AI agent status
    if ENABLE_AI_AGENT_MODE:
        print("AI Agent mode is enabled")
    else:
        print("AI Agent mode is disabled (set ENABLE_AI_AGENT_MODE=true in .env to enable)")


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
    global notes
    if not notes:
        raise HTTPException(status_code=500, detail="Notes not loaded")
    
    # Add a default score of 0 to each note to match the search results format
    # and remove any image matching flags from previous searches
    all_notes = []
    for note in notes:
        note_with_score = note.copy()
        note_with_score["score"] = 0.0
        
        # Clear any image matching flags that might be present from previous searches
        if "has_matching_images" in note_with_score:
            del note_with_score["has_matching_images"]
        if "matched_image" in note_with_score:
            del note_with_score["matched_image"]
            
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
    global notes, search_engine
    
    image_search_status = {
        "enabled": ENABLE_IMAGE_SEARCH,
        "initialized": search_engine and hasattr(search_engine, "image_processor") and search_engine.image_processor is not None,
        "images_count": len(search_engine.image_note_map) if search_engine and hasattr(search_engine, "image_note_map") else 0
    }
    
    ai_agent_status = {
        "enabled": ENABLE_AI_AGENT_MODE,
        "initialized": chatbot and hasattr(chatbot, "agent") and chatbot.agent is not None
    }
    
    return {
        "total_notes": len(notes),
        "archived_notes": sum(1 for note in notes if note.get("archived", False)),
        "pinned_notes": sum(1 for note in notes if note.get("pinned", False)),
        "using_cached_embeddings": os.path.exists(EMBEDDINGS_CACHE_FILE),
        "image_search": image_search_status,
        "ai_agent": ai_agent_status
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
    useAgentMode: bool = True  # Toggle for AI Agent mode


class ChatResponse(BaseModel):
    response: str
    notes: List[Dict[str, Any]]
    agent_info: Optional[Dict[str, Any]] = None


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
            response_text, relevant_notes, agent_info = chatbot.generate_chat_completion(
                messages, 
                stream=False,
                use_notes_context=request.useNotesContext,
                topic=request.topic,
                use_agent_mode=request.useAgentMode
            )
            
            return ChatResponse(
                response=response_text,
                notes=relevant_notes if request.useNotesContext else [],
                agent_info=agent_info
            )
        else:
            # Streaming response - use StreamingResponse
            return StreamingResponse(
                stream_chat_response(
                    chatbot, 
                    messages, 
                    use_notes_context=request.useNotesContext,
                    topic=request.topic,
                    use_agent_mode=request.useAgentMode
                ),
                media_type="application/json"
            )
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating chat response: {str(e)}")


async def stream_chat_response(chatbot_instance, messages, use_notes_context=True, topic=None, use_agent_mode=True):
    """Stream the chat response from the Ollama API."""
    try:
        # Extract the latest user query for finding relevant notes
        latest_user_message = next((msg["content"] for msg in reversed(messages) 
                                  if msg["role"] == "user"), "")
        
        # Find relevant notes for the latest user query if useNotesContext is True
        relevant_notes = []
        agent_info = None
        
        if use_notes_context:
            # Use topic for search if provided, otherwise use latest message
            search_query = topic if topic else latest_user_message
            
            if search_query:
                if chatbot_instance.agent and use_agent_mode:
                    # When AI Agent mode is enabled, let the agent find all notes from scratch
                    # Process the query with the AI Agent - now returns actions too
                    relevant_notes, agent_actions = chatbot_instance.agent.process_query(search_query, [])
                    
                    # Create agent info object with action details
                    agent_info = {
                        "enabled": True,
                        "active": True,
                        "notes_added": sum(1 for note in relevant_notes if note.get("added_by_agent", False)),
                        "actions": agent_actions  # Include the agent's actions in the response
                    }
                    
                    # Log if no notes were found
                    if not relevant_notes:
                        if agent_info:
                            agent_info["error"] = "No relevant notes found"
                else:
                    # Use standard search when agent mode is disabled
                    relevant_notes = chatbot_instance.get_relevant_notes(search_query)
                    agent_info = {
                        "enabled": ENABLE_AI_AGENT_MODE,
                        "active": False
                    }
        
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
                        
                        # Yield the accumulated text, relevant notes, and agent info
                        yield json.dumps({
                            "response": accumulated_text,
                            "notes": relevant_notes if use_notes_context else [],
                            "agent_info": agent_info
                        }).encode() + b"\n"
                except json.JSONDecodeError:
                    continue
                    
    except Exception as e:
        # If there's an error, yield it as part of the stream
        yield json.dumps({
            "error": str(e),
            "notes": [],
            "agent_info": {"enabled": ENABLE_AI_AGENT_MODE, "active": False, "error": str(e)}
        }).encode() + b"\n"


@app.get("/api/chat/model")
def get_chat_model():
    """Return the current LLM model being used and agent status."""
    return {
        "model": LLM_MODEL,
        "agent_mode_enabled": ENABLE_AI_AGENT_MODE
    }


if __name__ == "__main__":
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=True)
