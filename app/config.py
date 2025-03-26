import os

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Path to the Google Keep export folder
GOOGLE_KEEP_PATH = os.getenv(
    "GOOGLE_KEEP_PATH", "D:\\Takeout\\Keep"
)  # Path to the Keep folder from Google Takeout

# Search settings
SEMANTIC_SEARCH_WEIGHT = float(
    os.getenv("SEMANTIC_SEARCH_WEIGHT", 0.7)
)  # Weight for semantic search results (0-1)
KEYWORD_SEARCH_WEIGHT = float(
    os.getenv("KEYWORD_SEARCH_WEIGHT", 0.3)
)  # Weight for keyword search results (0-1)
MAX_RESULTS = int(os.getenv("MAX_RESULTS", 20))  # Maximum number of results to return

# Clustering settings
DEFAULT_NUM_CLUSTERS = int(os.getenv("DEFAULT_NUM_CLUSTERS", 8))  # Default number of clusters

# Server settings
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", 8000))

# Cache settings
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(APP_DIR, "cache")
EMBEDDINGS_CACHE_FILE = os.path.join(CACHE_DIR, "embeddings.npz")
NOTES_HASH_FILE = os.path.join(CACHE_DIR, "notes_hash.json")
