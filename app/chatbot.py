"""
Chatbot functionality for interacting with Ollama to answer queries about notes.
"""

import json
import requests
from typing import Dict, List, Any, Optional, Tuple

from app.config import OLLAMA_API_URL, LLM_MODEL, CHAT_CONTEXT_NOTES
from app.search import VibeSearch


class ChatBot:
    """A chatbot that uses Ollama to generate responses based on user notes."""

    def __init__(self, search_engine: VibeSearch):
        """Initialize the chatbot with a search engine."""
        self.search_engine = search_engine
        self.api_url = OLLAMA_API_URL
        self.model = LLM_MODEL

    def get_relevant_notes(self, query: str, max_notes: int = CHAT_CONTEXT_NOTES) -> List[Dict[str, Any]]:
        """Find notes relevant to the query."""
        return self.search_engine.search(query, max_results=max_notes)

    def format_notes_for_context(self, notes: List[Dict[str, Any]]) -> str:
        """Format notes into a string to use as context for the LLM."""
        formatted_notes = []
        
        for i, note in enumerate(notes):
            title = note.get("title", "Untitled Note")
            content = note.get("content", "")
            formatted_notes.append(f"Note {i+1}: {title}\n{content}\n")
        
        return "\n".join(formatted_notes)

    def prepare_messages_with_context(self, messages: List[Dict[str, str]], relevant_notes: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        """Prepare messages with context from relevant notes."""
        # Create a copy of messages to avoid modifying the original
        prepared_messages = messages.copy()
        
        # Add context from relevant notes to the system message
        if relevant_notes:
            notes_context = self.format_notes_for_context(relevant_notes)
            
            # Add or update the system message with notes context
            system_message = {
                "role": "system",
                "content": (
                    "You are a helpful assistant that answers questions based on the user's notes. "
                    "Use the following notes as context for answering the user's question. "
                    "Only use this information to inform your answers. "
                    f"\n\n{notes_context}"
                )
            }
            
            # Insert or replace system message at the beginning of the conversation
            if prepared_messages and prepared_messages[0]["role"] == "system":
                prepared_messages[0] = system_message
            else:
                prepared_messages.insert(0, system_message)
        else:
            # Add a generic system message if no notes context is provided
            system_message = {
                "role": "system",
                "content": (
                    "You are a helpful assistant that answers questions based on your general knowledge. "
                    "You don't have access to specific notes or personal information unless provided in the conversation."
                )
            }
            
            # Insert or replace system message at the beginning of the conversation
            if prepared_messages and prepared_messages[0]["role"] == "system":
                prepared_messages[0] = system_message
            else:
                prepared_messages.insert(0, system_message)
                
        return prepared_messages

    def generate_chat_completion(
        self, 
        messages: List[Dict[str, str]], 
        stream: bool = False,
        use_notes_context: bool = True,
        topic: Optional[str] = None
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """Generate a chat completion using Ollama API."""
        relevant_notes = []
        
        if use_notes_context:
            # Extract the latest user query
            latest_user_message = next((msg["content"] for msg in reversed(messages) 
                                      if msg["role"] == "user"), "")
            
            # Use topic for search if provided, otherwise use latest message
            search_query = topic if topic else latest_user_message
            
            if search_query:
                # Find relevant notes for the search query if notes context is enabled
                relevant_notes = self.get_relevant_notes(search_query)
            
        # Prepare messages with context
        prepared_messages = self.prepare_messages_with_context(messages, relevant_notes if use_notes_context else [])
        
        # Prepare the API request payload
        payload = {
            "model": self.model,
            "messages": prepared_messages,
            "stream": stream
        }
        
        # Make the API request
        try:
            response = requests.post(
                f"{self.api_url}/api/chat",
                headers={"Content-Type": "application/json"},
                json=payload,
                stream=stream
            )
            
            response.raise_for_status()
            
            if stream:
                return self._handle_streaming_response(response), relevant_notes
            else:
                response_data = response.json()
                return response_data.get("message", {}).get("content", ""), relevant_notes
                
        except requests.RequestException as e:
            error_message = f"Error calling Ollama API: {str(e)}"
            return error_message, relevant_notes
    
    def _handle_streaming_response(self, response) -> str:
        """Handle a streaming response from the Ollama API."""
        # This is a placeholder for handling streaming responses
        # In a real implementation, you'd return a generator or async response
        # For simplicity, we're concatenating the stream and returning a string
        full_response = ""
        
        for line in response.iter_lines():
            if line:
                data = json.loads(line)
                if "message" in data and "content" in data["message"]:
                    full_response += data["message"]["content"]
        
        return full_response