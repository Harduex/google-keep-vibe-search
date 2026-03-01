import json
import re
from collections import Counter
from typing import Any, AsyncGenerator, Dict, List

import httpx
import numpy as np

from app.core.config import settings
from app.prompts.system_prompts import TAG_NAMING_PROMPT
from app.services.note_service import NoteService
from app.services.search_service import SearchService


class CategorizationService:
    def __init__(self, search_service: SearchService, note_service: NoteService):
        self.search_service = search_service
        self.note_service = note_service

        headers = {"Content-Type": "application/json"}
        if settings.llm_api_key:
            headers["Authorization"] = f"Bearer {settings.llm_api_key}"

        self.client = httpx.AsyncClient(
            base_url=settings.resolved_api_base_url,
            headers=headers,
            timeout=httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0),
        )

    async def categorize(self, granularity: str = "broad") -> AsyncGenerator[bytes, None]:
        try:
            embeddings = self.search_service.embeddings
            note_indices = self.search_service.note_indices
            notes = self.search_service.notes

            if granularity == "specific":
                umap_components = 15
                umap_neighbors = 10
                min_cluster_size = 3
                min_samples = 2
            else:
                umap_components = 10
                umap_neighbors = 15
                min_cluster_size = 10
                min_samples = 5

            if len(note_indices) < min_cluster_size:
                all_ids = [notes[idx]["id"] for idx in note_indices]
                sample = [
                    self._truncate_note(notes[idx]) for idx in note_indices[:5]
                ]
                proposals = [
                    {
                        "tag_name": "All Notes",
                        "note_ids": all_ids,
                        "note_count": len(all_ids),
                        "sample_notes": sample,
                        "confidence": 1.0,
                    }
                ]
                yield self._line({"type": "proposals", "proposals": proposals})
                yield self._line({"type": "done"})
                return

            # Stage 1: UMAP dimensionality reduction
            yield self._line({
                "type": "progress",
                "stage": "reducing",
                "message": "Analyzing semantic maps...",
                "progress": 0.1,
            })

            import umap

            reducer = umap.UMAP(
                n_components=umap_components,
                n_neighbors=umap_neighbors,
                min_dist=0.0,
                metric="cosine",
                random_state=42,
            )
            reduced = reducer.fit_transform(embeddings)

            yield self._line({
                "type": "progress",
                "stage": "reducing",
                "message": "Analyzing semantic maps...",
                "progress": 0.33,
            })

            # Stage 2: HDBSCAN clustering
            yield self._line({
                "type": "progress",
                "stage": "clustering",
                "message": "Grouping related notes...",
                "progress": 0.4,
            })

            import hdbscan

            clusterer = hdbscan.HDBSCAN(
                min_cluster_size=min_cluster_size,
                min_samples=min_samples,
                metric="euclidean",
                cluster_selection_method="eom",
            )
            labels = clusterer.fit_predict(reduced)
            probabilities = clusterer.probabilities_

            yield self._line({
                "type": "progress",
                "stage": "clustering",
                "message": "Grouping related notes...",
                "progress": 0.66,
            })

            # Group notes by cluster
            clusters: Dict[int, List[int]] = {}
            noise_indices: List[int] = []
            for i, label in enumerate(labels):
                if label == -1:
                    noise_indices.append(i)
                else:
                    clusters.setdefault(label, []).append(i)

            total_clusters = len(clusters)
            if total_clusters == 0:
                all_ids = [
                    notes[note_indices[idx]]["id"]
                    for idx in range(len(note_indices))
                ]
                sample = [
                    self._truncate_note(notes[note_indices[idx]])
                    for idx in range(min(5, len(note_indices)))
                ]
                proposals = [
                    {
                        "tag_name": "Uncategorized",
                        "note_ids": all_ids,
                        "note_count": len(all_ids),
                        "sample_notes": sample,
                        "confidence": 0.0,
                    }
                ]
                yield self._line({"type": "proposals", "proposals": proposals})
                yield self._line({"type": "done"})
                return

            # Stage 3: LLM tag naming
            proposals = []
            seen_names: Dict[str, int] = {}

            for cluster_idx, (cluster_label, member_indices) in enumerate(
                sorted(clusters.items(), key=lambda x: len(x[1]), reverse=True)
            ):
                progress = 0.66 + (cluster_idx / total_clusters) * 0.30
                yield self._line({
                    "type": "progress",
                    "stage": "naming",
                    "message": "Generating tag names...",
                    "progress": round(progress, 2),
                    "current": cluster_idx + 1,
                    "total": total_clusters,
                })

                # Find notes closest to cluster centroid
                cluster_embeddings = reduced[member_indices]
                centroid = cluster_embeddings.mean(axis=0)
                distances = np.linalg.norm(cluster_embeddings - centroid, axis=1)
                closest_order = np.argsort(distances)
                representative_indices = [
                    member_indices[j] for j in closest_order[:5]
                ]

                # Build representative notes text
                rep_notes_text = []
                for ri in representative_indices:
                    note = notes[note_indices[ri]]
                    title = note.get("title", "")
                    content = note.get("content", "")[:300]
                    rep_notes_text.append(f"Title: {title}\n{content}")

                notes_text = "\n---\n".join(rep_notes_text)

                # Try LLM naming
                tag_name = await self._get_llm_tag_name(notes_text)

                # Fallback to keyword extraction
                if not tag_name:
                    cluster_notes = [
                        notes[note_indices[mi]] for mi in member_indices
                    ]
                    tag_name = self._extract_keywords_fallback(cluster_notes)

                # Deduplicate tag names
                tag_name = self._deduplicate_name(tag_name, seen_names)

                # Build note IDs and samples
                cluster_note_ids = [
                    notes[note_indices[mi]]["id"] for mi in member_indices
                ]
                sample_notes = [
                    self._truncate_note(notes[note_indices[member_indices[j]]])
                    for j in closest_order[:5]
                    if j < len(member_indices)
                ]

                # Cluster confidence
                cluster_probs = [probabilities[mi] for mi in member_indices]
                confidence = (
                    float(np.mean(cluster_probs)) if cluster_probs else 0.0
                )

                proposals.append({
                    "tag_name": tag_name,
                    "note_ids": cluster_note_ids,
                    "note_count": len(cluster_note_ids),
                    "sample_notes": sample_notes,
                    "confidence": round(confidence, 2),
                })

            # Add uncategorized group for noise
            if noise_indices:
                noise_ids = [
                    notes[note_indices[ni]]["id"] for ni in noise_indices
                ]
                noise_samples = [
                    self._truncate_note(notes[note_indices[ni]])
                    for ni in noise_indices[:5]
                ]
                proposals.append({
                    "tag_name": "Uncategorized",
                    "note_ids": noise_ids,
                    "note_count": len(noise_ids),
                    "sample_notes": noise_samples,
                    "confidence": 0.0,
                })

            yield self._line({"type": "proposals", "proposals": proposals})
            yield self._line({"type": "done"})

        except Exception as e:
            yield self._line({"type": "error", "error": str(e)})

    async def _get_llm_tag_name(self, notes_text: str) -> str:
        try:
            prompt = TAG_NAMING_PROMPT.format(notes_text=notes_text)
            response = await self.client.post(
                "/chat/completions",
                json={
                    "model": settings.llm_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 20,
                    "temperature": 0.3,
                },
            )
            response.raise_for_status()
            data = response.json()
            raw = data["choices"][0]["message"]["content"].strip()
            cleaned = raw.strip('"\'.').strip()
            if len(cleaned) > 40:
                cleaned = cleaned[:40].rsplit(" ", 1)[0]
            return cleaned if cleaned else ""
        except Exception:
            return ""

    def _extract_keywords_fallback(
        self, cluster_notes: List[Dict[str, Any]]
    ) -> str:
        all_text = " ".join(
            f"{n.get('title', '')} {n.get('content', '')}"
            for n in cluster_notes
        )
        words = re.findall(r"\b[a-zA-Z]{3,}\b", all_text.lower())
        stop = {
            "the", "and", "for", "are", "but", "not", "you", "all", "can",
            "her", "was", "one", "our", "out", "has", "have", "from",
            "this", "that", "with", "they", "been", "will", "would",
            "could", "should", "their", "there", "about", "which", "when",
            "what", "where", "than", "then", "also", "into", "just",
            "more", "some", "very", "like", "http", "https", "www", "com",
        }
        filtered = [w for w in words if w not in stop]
        counts = Counter(filtered)
        top = [word for word, _ in counts.most_common(3)]
        return " ".join(top).title() if top else "Misc"

    def _deduplicate_name(self, name: str, seen: Dict[str, int]) -> str:
        if name not in seen:
            seen[name] = 1
            return name
        seen[name] += 1
        return f"{name} {seen[name]}"

    def _truncate_note(self, note: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": note.get("id", ""),
            "title": note.get("title", ""),
            "content": note.get("content", "")[:200],
        }

    @staticmethod
    def _line(data: dict) -> bytes:
        return (json.dumps(data) + "\n").encode("utf-8")

    async def close(self):
        await self.client.aclose()
