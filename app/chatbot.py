"""
Chatbot functionality for interacting with Ollama to answer queries about notes.
"""

import json
import logging
import requests
from typing import Dict, List, Any, Optional, Tuple

from app.config import OLLAMA_API_URL, LLM_MODEL, CHAT_CONTEXT_NOTES, ENABLE_AI_AGENT_MODE
from app.search import VibeSearch
from app.agent import AIAgent

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("chatbot")

class ChatBot:
    """A chatbot that uses Ollama to generate responses based on user notes."""

    def __init__(self, search_engine: VibeSearch):
        """Initialize the chatbot with a search engine."""
        self.search_engine = search_engine
        self.api_url = OLLAMA_API_URL
        self.model = LLM_MODEL
        self.agent = AIAgent(search_engine) if ENABLE_AI_AGENT_MODE else None
        logger.info(f"Initialized ChatBot with API URL: {self.api_url} and model: {self.model}")

    def get_relevant_notes(self, query: str, max_notes: int = CHAT_CONTEXT_NOTES) -> List[Dict[str, Any]]:
        """Find notes relevant to the query."""
        logger.debug(f"Searching for notes with query: '{query}', max_notes: {max_notes}")
        results = self.search_engine.search(query, max_results=max_notes)
        logger.debug(f"Found {len(results)} relevant notes")
        return results

    def format_notes_for_context(self, notes: List[Dict[str, Any]]) -> str:
        """Format notes into a string to use as context for the LLM."""
        formatted_notes = []
        
        for i, note in enumerate(notes):
            title = note.get("title", "Untitled Note")
            content = note.get("content", "")
            # Add a tag if this note was added by the AI Agent
            added_by_agent = note.get("added_by_agent", False)
            agent_tag = " [Added by AI Agent] " if added_by_agent else ""
            
            formatted_notes.append(f"Note {i+1}{agent_tag}: {title}\n{content}\n")
        
        formatted_context = "\n".join(formatted_notes)
        logger.debug(f"Formatted {len(notes)} notes into a context of {len(formatted_context)} characters")
        return formatted_context

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
        topic: Optional[str] = None,
        use_agent_mode: bool = True
    ) -> Tuple[str, List[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """Generate a chat completion using Ollama API."""
        logger.info(f"Generating chat completion: stream={stream}, use_notes_context={use_notes_context}, agentMode={use_agent_mode}")
        relevant_notes = []
        agent_info = None
        agent_actions = []
        
        if use_notes_context:
            # Extract the latest user query
            latest_user_message = next((msg["content"] for msg in reversed(messages) 
                                      if msg["role"] == "user"), "")
            
            # Use topic for search if provided, otherwise use latest message
            search_query = topic if topic else latest_user_message
            logger.debug(f"Using search query: '{search_query}'")
            
            if search_query:
                if self.agent and use_agent_mode:
                    # When AI Agent mode is enabled, let the agent find all notes from scratch
                    # without providing any initial context
                    logger.info("Using agent mode for chat completion")
                    logger.info(f"Generating agent response for query: '{search_query}'")
                    
                    # Process the query with the AI Agent - now returns actions too
                    relevant_notes, agent_actions = self.agent.process_query(search_query, [])
                    
                    # Create agent info object with action details
                    agent_info = {
                        "enabled": True,
                        "active": True,
                        "notes_added": sum(1 for note in relevant_notes if note.get("added_by_agent", False)),
                        "actions": agent_actions  # Include the agent's actions
                    }
                    
                    # Log if no notes were returned
                    if not relevant_notes:
                        logger.warning("AI Agent didn't find any relevant notes for the query")
                        if agent_info:
                            agent_info["error"] = "No relevant notes found"
                else:
                    # If agent mode is not enabled, use the standard search
                    logger.debug(f"Using standard search for '{search_query}'")
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
                return self._handle_streaming_response(response), relevant_notes, agent_info
            else:
                response_data = response.json()
                return response_data.get("message", {}).get("content", ""), relevant_notes, agent_info
                
        except requests.RequestException as e:
            error_message = f"Error calling Ollama API: {str(e)}"
            logger.error(error_message)
            return error_message, relevant_notes, agent_info
    
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