import os

# Path to the Google Keep export folder
GOOGLE_KEEP_PATH = 'D:\\Takeout\\Keep'  # Example path to the Keep folder from Google Takeout

# Search settings
SEMANTIC_SEARCH_WEIGHT = 0.7  # Weight for semantic search results (0-1)
KEYWORD_SEARCH_WEIGHT = 0.3   # Weight for keyword search results (0-1)
MAX_RESULTS = 20             # Maximum number of results to return

# Server settings
HOST = "127.0.0.1"
PORT = 8000