import os
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    google_keep_path: str = ""

    # Search
    max_results: int = 300
    search_threshold: float = 0.3
    embedding_model: str = "paraphrase-multilingual-MiniLM-L12-v2"
    image_search_threshold: float = 0.2

    # LLM (OpenAI-compatible API)
    llm_api_base_url: str = "http://localhost:11434"
    llm_api_key: str = ""
    llm_model: str = "ornith-1.0-9b"
    llm_provider: str = "ollama"
    llm_temperature: float = 0.1
    llm_max_tokens: int = 2048
    chat_context_notes: int = 10

    # Agent mode
    enable_agent_mode: bool = False
    agent_max_steps: int = 5

    # Image search
    enable_image_search: bool = False

    # Cache
    cache_dir: str = ""

    # Conversation
    chat_max_recent_messages: int = 6
    chat_summarization_threshold: int = 12

    # Cache control
    force_cache_refresh: bool = False

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
        return self.llm_api_base_url.rstrip("/")

    @property
    def resolved_litellm_model(self) -> str:
        """Build the LiteLLM model string based on provider."""
        provider = self.llm_provider.lower()
        if provider == "ollama":
            return f"ollama_chat/{self.llm_model}"
        if provider == "openai":
            return f"openai/{self.llm_model}"
        return f"{provider}/{self.llm_model}"

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
