"""GraphRAG service using LlamaIndex's PropertyGraphIndex.

Builds a knowledge graph from notes by extracting entities and relations
using the configured LLM.  Queries can traverse graph relations to answer
complex, multi-hop questions that pure vector search cannot handle.

All LlamaIndex imports are guarded for graceful degradation.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

try:
    from llama_index.core import Document, PropertyGraphIndex, StorageContext
    from llama_index.core.graph_stores import SimplePropertyGraphStore

    _GRAPH_AVAILABLE = True
except ImportError:
    _GRAPH_AVAILABLE = False
    Document = None  # type: ignore[assignment,misc]
    PropertyGraphIndex = None  # type: ignore[assignment,misc]
    SimplePropertyGraphStore = None  # type: ignore[assignment,misc]
    StorageContext = None  # type: ignore[assignment,misc]
    print(
        "[GraphRAGService] LlamaIndex graph modules not found. "
        "Install llama-index-core to enable GraphRAG."
    )


class GraphRAGService:
    """Knowledge-graph retrieval over notes using LlamaIndex PropertyGraphIndex."""

    GRAPH_STORE_FILE = "property_graph_store.json"

    def __init__(self, llm: Any, embed_model: Any, persist_dir: str) -> None:
        self.llm = llm
        self.embed_model = embed_model
        self.persist_dir = persist_dir
        self.graph_store: Optional[Any] = None
        self.index: Optional[Any] = None
        self._available = _GRAPH_AVAILABLE

        if not _GRAPH_AVAILABLE:
            print("[GraphRAGService] Skipping initialisation (imports unavailable).")
            return

        os.makedirs(persist_dir, exist_ok=True)
        self.graph_store = SimplePropertyGraphStore()

    @property
    def is_ready(self) -> bool:
        return self.index is not None

    def build_graph(self, notes: List[Dict[str, Any]]) -> None:
        """Extract entities and relations from notes and build graph index."""
        if not self._available:
            return

        documents = []
        for note in notes:
            note_id = note.get("id", "")
            title = note.get("title", "")
            content = note.get("content", "")
            text = f"{title}\n\n{content}".strip()
            if not text:
                continue
            documents.append(
                Document(
                    text=text,
                    metadata={"note_id": note_id, "title": title},
                )
            )

        if not documents:
            print("[GraphRAGService] No documents to index.")
            return

        print(f"[GraphRAGService] Building graph from {len(documents)} documents...")
        try:
            self.graph_store = SimplePropertyGraphStore()
            self.index = PropertyGraphIndex.from_documents(
                documents,
                property_graph_store=self.graph_store,
                llm=self.llm,
                embed_model=self.embed_model,
                show_progress=True,
            )
            print("[GraphRAGService] Graph index built successfully.")
        except Exception as e:
            print(f"[GraphRAGService] Error building graph: {e}")
            self.index = None

    def query_relations(
        self, query: str, max_results: int = 5
    ) -> List[Dict[str, Any]]:
        """Query the graph for relationship-based information."""
        if not self.is_ready:
            return []

        try:
            retriever = self.index.as_retriever(
                include_text=True,
                similarity_top_k=max_results,
            )
            nodes = retriever.retrieve(query)

            results = []
            for node in nodes[:max_results]:
                note_id = node.metadata.get("note_id", "") if hasattr(node, "metadata") else ""
                title = node.metadata.get("title", "") if hasattr(node, "metadata") else ""
                results.append(
                    {
                        "text": node.text if hasattr(node, "text") else str(node),
                        "score": float(node.score) if hasattr(node, "score") and node.score else 0.5,
                        "source_type": "graphrag",
                        "note_id": note_id,
                        "title": title,
                    }
                )
            return results
        except Exception as e:
            print(f"[GraphRAGService] Error querying graph: {e}")
            return []

    def persist(self) -> None:
        """Save graph store to disk."""
        if not self.is_ready or not self.graph_store:
            return

        try:
            store_path = os.path.join(self.persist_dir, self.GRAPH_STORE_FILE)
            self.graph_store.persist(persist_path=store_path)
            print(f"[GraphRAGService] Graph persisted to {self.persist_dir}")
        except Exception as e:
            print(f"[GraphRAGService] Error persisting graph: {e}")

    def load(self) -> bool:
        """Load persisted graph store and rebuild index."""
        if not self._available:
            return False

        store_path = os.path.join(self.persist_dir, self.GRAPH_STORE_FILE)
        if not os.path.exists(store_path):
            return False

        try:
            self.graph_store = SimplePropertyGraphStore.from_persist_path(store_path)
            self.index = PropertyGraphIndex.from_existing(
                property_graph_store=self.graph_store,
                llm=self.llm,
                embed_model=self.embed_model,
            )
            print(f"[GraphRAGService] Graph loaded from {self.persist_dir}")
            return True
        except Exception as e:
            print(f"[GraphRAGService] Error loading graph: {e}")
            self.index = None
            return False
