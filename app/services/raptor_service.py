"""RAPTOR service -- Recursive Abstractive Processing for Tree-Organized Retrieval.

Implements the RAPTOR algorithm:
1. Cluster leaf chunks by embedding similarity
2. Summarize each cluster with the LLM
3. Embed the summaries
4. Recurse: cluster summaries, summarize again, etc.
5. At query time, search all levels of the tree

This is computationally expensive (requires many LLM calls at build time).
The tree is persisted to disk and loaded on subsequent startups.
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Any, Dict, List, Optional

import numpy as np
from pydantic import BaseModel

try:
    from sklearn.cluster import KMeans
    from sklearn.metrics.pairwise import cosine_similarity

    _SKLEARN_AVAILABLE = True
except ImportError:
    _SKLEARN_AVAILABLE = False


class TreeNode(BaseModel):
    id: str
    text: str
    embedding: List[float]
    level: int
    children: List[str] = []
    note_ids: List[str] = []


RAPTOR_SUMMARY_PROMPT = """Summarize the following texts into a single coherent paragraph.
Focus on the key themes, facts, and relationships. Be concise but comprehensive.

Texts:
{texts}

Summary:"""


class RAPTORService:
    """Recursive Abstractive Processing for Tree-Organized Retrieval."""

    TREE_FILE = "raptor_tree.json"
    MAX_LEVELS = 3
    TARGET_CLUSTER_SIZE = 7

    def __init__(self, llm: Any, embed_model: Any, persist_dir: str) -> None:
        self.llm = llm
        self.embed_model = embed_model
        self.persist_dir = persist_dir
        self.tree_nodes: Dict[str, TreeNode] = {}

        os.makedirs(persist_dir, exist_ok=True)

    @property
    def is_ready(self) -> bool:
        return len(self.tree_nodes) > 0

    def build_tree(self, chunks: List[Any]) -> None:
        """Build the RAPTOR summary tree from chunks.

        Parameters
        ----------
        chunks:
            List of chunk objects (DoclingNoteChunk or NoteChunk) or dicts.
        """
        if not _SKLEARN_AVAILABLE:
            print("[RAPTORService] scikit-learn not available; cannot build tree.")
            return

        chunk_dicts = []
        for chunk in chunks:
            if hasattr(chunk, "model_dump"):
                d = chunk.model_dump()
            elif hasattr(chunk, "to_dict"):
                d = chunk.to_dict()
            elif isinstance(chunk, dict):
                d = chunk
            else:
                continue
            if d.get("text"):
                chunk_dicts.append(d)

        if not chunk_dicts:
            print("[RAPTORService] No chunks to process.")
            return

        print(f"[RAPTORService] Building tree from {len(chunk_dicts)} chunks...")

        # Level 0: create leaf nodes
        texts = [d["text"] for d in chunk_dicts]
        print(f"[RAPTORService] Embedding {len(texts)} leaf nodes...")
        embeddings = self.embed_model.get_text_embedding_batch(texts)

        current_level_nodes = []
        for i, d in enumerate(chunk_dicts):
            node = TreeNode(
                id=str(uuid.uuid4()),
                text=d["text"],
                embedding=list(embeddings[i]),
                level=0,
                children=[],
                note_ids=[d.get("note_id", d.get("source_id", ""))],
            )
            self.tree_nodes[node.id] = node
            current_level_nodes.append(node)

        print(f"[RAPTORService] Level 0: {len(current_level_nodes)} leaf nodes")

        # Build higher levels
        for level in range(1, self.MAX_LEVELS + 1):
            if len(current_level_nodes) <= 1:
                print(f"[RAPTORService] Stopping at level {level} (only {len(current_level_nodes)} nodes)")
                break

            num_clusters = max(1, len(current_level_nodes) // self.TARGET_CLUSTER_SIZE)
            if num_clusters >= len(current_level_nodes):
                num_clusters = max(1, len(current_level_nodes) // 2)

            print(f"[RAPTORService] Level {level}: clustering {len(current_level_nodes)} nodes into {num_clusters} clusters...")

            level_embeddings = np.array([n.embedding for n in current_level_nodes])
            kmeans = KMeans(n_clusters=num_clusters, random_state=42, n_init=10)
            cluster_labels = kmeans.fit_predict(level_embeddings)

            clusters: Dict[int, List[TreeNode]] = {}
            for i, label in enumerate(cluster_labels):
                clusters.setdefault(int(label), []).append(current_level_nodes[i])

            next_level_nodes = []
            for cluster_id, cluster_nodes in clusters.items():
                cluster_texts = "\n\n---\n\n".join(n.text for n in cluster_nodes)
                cluster_note_ids = []
                child_ids = []
                for n in cluster_nodes:
                    child_ids.append(n.id)
                    cluster_note_ids.extend(n.note_ids)
                cluster_note_ids = list(set(cluster_note_ids))

                # Summarize with LLM
                try:
                    prompt = RAPTOR_SUMMARY_PROMPT.format(texts=cluster_texts[:4000])
                    summary_response = self.llm.complete(prompt)
                    summary_text = str(summary_response).strip()
                except Exception as e:
                    print(f"[RAPTORService] LLM summarization failed for cluster {cluster_id}: {e}")
                    summary_text = cluster_texts[:500]

                # Embed summary
                summary_embedding = self.embed_model.get_text_embedding(summary_text)

                parent_node = TreeNode(
                    id=str(uuid.uuid4()),
                    text=summary_text,
                    embedding=list(summary_embedding),
                    level=level,
                    children=child_ids,
                    note_ids=cluster_note_ids,
                )
                self.tree_nodes[parent_node.id] = parent_node
                next_level_nodes.append(parent_node)

            print(f"[RAPTORService] Level {level}: created {len(next_level_nodes)} summary nodes")
            current_level_nodes = next_level_nodes

        print(f"[RAPTORService] Tree built: {len(self.tree_nodes)} total nodes")

    def query_summaries(
        self, query: str, max_results: int = 5
    ) -> List[Dict[str, Any]]:
        """Search all levels of the summary tree for relevant content."""
        if not self.is_ready:
            return []

        query_embedding = np.array(self.embed_model.get_text_embedding(query)).reshape(1, -1)

        all_nodes = list(self.tree_nodes.values())
        all_embeddings = np.array([n.embedding for n in all_nodes])

        similarities = cosine_similarity(query_embedding, all_embeddings)[0]

        scored = sorted(
            zip(all_nodes, similarities),
            key=lambda x: x[1],
            reverse=True,
        )

        results = []
        for node, score in scored[:max_results]:
            results.append(
                {
                    "text": node.text,
                    "score": float(score),
                    "level": node.level,
                    "note_ids": node.note_ids,
                    "source_type": "raptor",
                }
            )

        return results

    def persist(self) -> None:
        """Save the tree to disk as JSON."""
        if not self.tree_nodes:
            return

        tree_path = os.path.join(self.persist_dir, self.TREE_FILE)
        data = {nid: node.model_dump() for nid, node in self.tree_nodes.items()}
        with open(tree_path, "w") as f:
            json.dump(data, f)
        print(f"[RAPTORService] Tree persisted to {tree_path} ({len(self.tree_nodes)} nodes)")

    def load(self) -> bool:
        """Load the tree from disk."""
        tree_path = os.path.join(self.persist_dir, self.TREE_FILE)
        if not os.path.exists(tree_path):
            return False

        try:
            with open(tree_path, "r") as f:
                data = json.load(f)
            self.tree_nodes = {nid: TreeNode(**node_data) for nid, node_data in data.items()}
            print(f"[RAPTORService] Tree loaded from {tree_path} ({len(self.tree_nodes)} nodes)")
            return True
        except Exception as e:
            print(f"[RAPTORService] Error loading tree: {e}")
            return False
