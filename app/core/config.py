import os
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    google_keep_path: str = ""

    # Search
    max_results: int = 20
    search_threshold: float = 0.0
    image_search_threshold: float = 0.2
    image_search_weight: float = 0.3

    # Clustering
    default_num_clusters: int = 8

    # Server
    host: str = "127.0.0.1"
    port: int = 8000

    # LLM (OpenAI-compatible API)
    llm_api_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = "llama3"
    chat_context_notes: int = 15

    # Legacy Ollama (used as fallback for llm_api_base_url)
    ollama_api_url: str = "http://localhost:11434"

    # Image search
    enable_image_search: bool = True

    # Chunking
    chunking_strategy: str = "docling"  # "docling" or "legacy"

    # LanceDB
    lancedb_path: str = ""  # defaults to cache_dir/lancedb

    # GraphRAG (opt-in)
    enable_graphrag: bool = False
    graph_persist_dir: str = ""  # defaults to cache_dir/graph

    # RAPTOR (opt-in)
    enable_raptor: bool = False
    raptor_persist_dir: str = ""  # defaults to cache_dir/raptor

    # Cache
    cache_dir: str = ""

    # Conversation
    chat_max_recent_messages: int = 6
    chat_summarization_threshold: int = 12

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    @field_validator("google_keep_path")
    @classmethod
    def validate_google_keep_path(cls, v: str) -> str:
        if not v:
            raise ValueError(
                "GOOGLE_KEEP_PATH must be set in .env file. "
                "Point it to your Google Takeout Keep export folder."
            )
        path = Path(v)
        if not path.exists():
            raise ValueError(f"GOOGLE_KEEP_PATH does not exist: {v}")
        return v

    @property
    def resolved_api_base_url(self) -> str:
        if self.llm_api_base_url:
            return self.llm_api_base_url.rstrip("/") + "/"
        return f"{self.ollama_api_url}/v1/"

    @property
    def resolved_cache_dir(self) -> str:
        if self.cache_dir:
            return self.cache_dir
        return os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "cache",
        )

    @property
    def embeddings_cache_file(self) -> str:
        return os.path.join(self.resolved_cache_dir, "embeddings.npz")

    @property
    def notes_hash_file(self) -> str:
        return os.path.join(self.resolved_cache_dir, "notes_hash.json")

    @property
    def notes_cache_file(self) -> str:
        return os.path.join(self.resolved_cache_dir, "notes_cache.json")

    @property
    def image_embeddings_cache_file(self) -> str:
        return os.path.join(self.resolved_cache_dir, "image_embeddings.npz")

    @property
    def image_hash_file(self) -> str:
        return os.path.join(self.resolved_cache_dir, "image_hashes.json")

    @property
    def tags_cache_file(self) -> str:
        return os.path.join(self.resolved_cache_dir, "tags.json")

    @property
    def excluded_tags_cache_file(self) -> str:
        return os.path.join(self.resolved_cache_dir, "excluded_tags.json")

    @property
    def chat_sessions_dir(self) -> str:
        return os.path.join(self.resolved_cache_dir, "chat_sessions")


settings = Settings()
