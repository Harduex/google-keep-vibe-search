"""LlamaIndex service for embedding and LLM configuration.

Provides a centralized wrapper around LlamaIndex's embedding model and
LLM, configured from the application's Settings object.  All llama_index
imports are guarded so the rest of the application can still load even
when the llama-index packages are not installed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from app.core.config import Settings

# ---------------------------------------------------------------------------
# Optional llama_index imports
# ---------------------------------------------------------------------------

try:
    from llama_index.core import Settings as LlamaSettings
    from llama_index.core.embeddings import BaseEmbedding
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding
    from llama_index.llms.openai_like import OpenAILike

    _LLAMA_INDEX_AVAILABLE = True
except ImportError:
    LlamaSettings = None  # type: ignore[assignment,misc]
    BaseEmbedding = None  # type: ignore[assignment,misc]
    HuggingFaceEmbedding = None  # type: ignore[assignment,misc]
    OpenAILike = None  # type: ignore[assignment,misc]
    _LLAMA_INDEX_AVAILABLE = False
    print(
        "[LlamaIndexService] llama-index packages not found. "
        "Install llama-index-core, llama-index-embeddings-huggingface, "
        "and llama-index-llms-openai-like to enable this service."
    )


class LlamaIndexService:
    """Thin wrapper that initialises a HuggingFace embedding model and an
    OpenAI-compatible LLM via LlamaIndex, then exposes them as instance
    attributes and registers them in LlamaIndex's global ``Settings``."""

    # The all-MiniLM-L6-v2 model produces 384-dimensional embeddings.
    EMBED_MODEL_NAME: str = "all-MiniLM-L6-v2"
    EMBED_DIMENSION: int = 384

    def __init__(self, settings: "Settings") -> None:
        self.embed_model: Optional[object] = None
        self.llm: Optional[object] = None
        self._available: bool = _LLAMA_INDEX_AVAILABLE

        if not _LLAMA_INDEX_AVAILABLE:
            print("[LlamaIndexService] Skipping initialisation (imports unavailable).")
            return

        # ----- Embedding model ------------------------------------------------
        print(f"[LlamaIndexService] Loading embedding model: {self.EMBED_MODEL_NAME}")
        self.embed_model = HuggingFaceEmbedding(model_name=self.EMBED_MODEL_NAME)

        # ----- LLM -----------------------------------------------------------
        api_base = settings.resolved_api_base_url
        api_key = settings.llm_api_key if settings.llm_api_key else "not-needed"
        model_name = settings.llm_model

        print(
            f"[LlamaIndexService] Configuring LLM: model={model_name}, "
            f"api_base={api_base}"
        )
        self.llm = OpenAILike(
            api_base=api_base,
            api_key=api_key,
            model=model_name,
            is_chat_model=True,
        )

        # ----- Register globally with LlamaIndex -----------------------------
        LlamaSettings.embed_model = self.embed_model
        LlamaSettings.llm = self.llm

        print("[LlamaIndexService] Initialisation complete.")

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        """Return ``True`` when all llama_index dependencies loaded."""
        return self._available

    @property
    def embed_dimension(self) -> int:
        """Dimensionality of the configured embedding model."""
        return self.EMBED_DIMENSION
