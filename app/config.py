import os

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Path to the Google Keep export folder
GOOGLE_KEEP_PATH = os.getenv(
    "GOOGLE_KEEP_PATH", "D:\\Takeout\\Keep"
)  # Path to the Keep folder from Google Takeout

# Search settings
MAX_RESULTS = int(os.getenv("MAX_RESULTS", 20))  # Maximum number of results to return
SEARCH_THRESHOLD = float(os.getenv("SEARCH_THRESHOLD", 0.0))  # Minimum relevance score (0.0 - 1.0) for search results
IMAGE_SEARCH_THRESHOLD = float(os.getenv("IMAGE_SEARCH_THRESHOLD", 0.2))  # Minimum relevance score for image matches
IMAGE_SEARCH_WEIGHT = float(os.getenv("IMAGE_SEARCH_WEIGHT", 0.3))  # Weight for image search results in combined score

# Clustering settings
DEFAULT_NUM_CLUSTERS = int(os.getenv("DEFAULT_NUM_CLUSTERS", 8))  # Default number of clusters

# Server settings
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", 8000))

# Ollama settings
OLLAMA_API_URL = os.getenv("OLLAMA_API_URL", "http://localhost:11434")
LLM_MODEL = os.getenv("LLM_MODEL", "llama3")
CHAT_CONTEXT_NOTES = int(os.getenv("CHAT_CONTEXT_NOTES", 5))  # Number of notes to use for context

# AI Agent settings
ENABLE_AI_AGENT_MODE = os.getenv("ENABLE_AI_AGENT_MODE", "true").lower() == "true"  # Enable/disable AI Agent mode
MAX_AGENT_SEARCHES = int(os.getenv("MAX_AGENT_SEARCHES", 2))  # Maximum number of additional searches the agent can perform
AGENT_SEARCH_TIMEOUT = int(os.getenv("AGENT_SEARCH_TIMEOUT", 15))  # Timeout in seconds for agent operations
AI_AGENT_LOG_FILE = os.getenv("AI_AGENT_LOG_FILE", "agent_debug.log")  # Path to log file for agent operations

# Cache settings
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(APP_DIR, "cache")
EMBEDDINGS_CACHE_FILE = os.path.join(CACHE_DIR, "embeddings.npz")
NOTES_HASH_FILE = os.path.join(CACHE_DIR, "notes_hash.json")
NOTES_CACHE_FILE = os.path.join(CACHE_DIR, "notes_cache.json")

# Image embeddings cache
IMAGE_EMBEDDINGS_CACHE_FILE = os.path.join(CACHE_DIR, "image_embeddings.npz")
IMAGE_HASH_FILE = os.path.join(CACHE_DIR, "image_hashes.json")

# Enable/disable image search
ENABLE_IMAGE_SEARCH = os.getenv("ENABLE_IMAGE_SEARCH", "true").lower() == "true"
