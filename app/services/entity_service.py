"""Entity resolution service for improving search via named entity matching."""

import hashlib
import json
import os
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx

from app.core.config import settings


class EntityService:
    """Extracts entities from notes, clusters aliases, and provides entity-based retrieval signal."""

    ENTITY_LABELS = {"PERSON", "GPE", "ORG", "PRODUCT"}

    def __init__(self, notes: List[Dict[str, Any]], cache_dir: Optional[str] = None):
        import spacy

        self.nlp = spacy.load("en_core_web_sm")
        self.cache_dir = cache_dir or settings.resolved_cache_dir
        self.entity_index: Dict[str, Set[str]] = {}  # canonical → note IDs
        self.alias_map: Dict[str, str] = {}  # surface form → canonical

        self._build_index(notes)

    def _build_index(self, notes: List[Dict[str, Any]]):
        """Build entity index from notes, using cache if valid."""
        current_hash = self._compute_hash(notes)
        cache_file = os.path.join(self.cache_dir, "entity_index.json")

        if self._is_cache_valid(cache_file, current_hash):
            self._load_from_cache(cache_file)
            print(f"[entities] Loaded entity index from cache ({len(self.entity_index)} entities)")
            return

        # Extract entities from all notes
        raw_entities = self._extract_entities(notes)

        # Cluster aliases
        self._cluster_entities(raw_entities)

        # Save to cache
        self._save_to_cache(cache_file, current_hash)
        print(f"[entities] Built entity index: {len(self.entity_index)} entities from {len(notes)} notes")

    def _compute_hash(self, notes: List[Dict[str, Any]]) -> str:
        h = hashlib.md5()
        for note in notes:
            h.update(note.get("id", "").encode("utf-8"))
            h.update(note.get("content", "")[:200].encode("utf-8"))
        return h.hexdigest()

    def _is_cache_valid(self, cache_file: str, current_hash: str) -> bool:
        meta_file = cache_file + ".meta"
        if not os.path.exists(cache_file) or not os.path.exists(meta_file):
            return False
        try:
            with open(meta_file, "r") as f:
                meta = json.load(f)
            return meta.get("hash") == current_hash
        except Exception:
            return False

    def _load_from_cache(self, cache_file: str):
        with open(cache_file, "r") as f:
            data = json.load(f)
        self.entity_index = {k: set(v) for k, v in data["entity_index"].items()}
        self.alias_map = data["alias_map"]

    def _save_to_cache(self, cache_file: str, current_hash: str):
        os.makedirs(os.path.dirname(cache_file), exist_ok=True)
        data = {
            "entity_index": {k: list(v) for k, v in self.entity_index.items()},
            "alias_map": self.alias_map,
        }
        with open(cache_file, "w") as f:
            json.dump(data, f)
        with open(cache_file + ".meta", "w") as f:
            json.dump({"hash": current_hash}, f)

    def _extract_entities(self, notes: List[Dict[str, Any]]) -> Dict[str, List[Tuple[str, str]]]:
        """Extract entities from notes. Returns {note_id: [(text, label), ...]}."""
        results: Dict[str, List[Tuple[str, str]]] = {}
        for note in notes:
            text = (note.get("title", "") + " " + note.get("content", ""))[:5000]
            doc = self.nlp(text)
            entities = [
                (ent.text, ent.label_)
                for ent in doc.ents
                if ent.label_ in self.ENTITY_LABELS
            ]
            if entities:
                results[note.get("id", "")] = entities
        return results

    def _cluster_entities(self, raw_entities: Dict[str, List[Tuple[str, str]]]):
        """Cluster entity mentions into canonical groups using string similarity."""
        import jellyfish

        # Collect all unique (surface_form, label) pairs with their note IDs
        mention_notes: Dict[str, Dict[str, Set[str]]] = {}  # label → {surface → note_ids}
        for note_id, entities in raw_entities.items():
            for surface, label in entities:
                if label not in mention_notes:
                    mention_notes[label] = {}
                if surface not in mention_notes[label]:
                    mention_notes[label][surface] = set()
                mention_notes[label][surface].add(note_id)

        # For each label type, build similarity graph and find connected components
        for label, surfaces_dict in mention_notes.items():
            surfaces = list(surfaces_dict.keys())
            if len(surfaces) <= 1:
                # Single mention — just add directly
                for surface, note_ids in surfaces_dict.items():
                    canonical = surface
                    self.entity_index[canonical] = note_ids
                    self.alias_map[surface.lower()] = canonical
                continue

            # Token-prefix blocking: only compare entities sharing first 3 chars
            blocks: Dict[str, List[str]] = {}
            for s in surfaces:
                prefix = s.lower()[:3]
                if prefix not in blocks:
                    blocks[prefix] = []
                blocks[prefix].append(s)

            G = nx.Graph()
            G.add_nodes_from(surfaces)

            for block_surfaces in blocks.values():
                for i in range(len(block_surfaces)):
                    for j in range(i + 1, len(block_surfaces)):
                        a, b = block_surfaces[i], block_surfaces[j]
                        score = jellyfish.jaro_winkler_similarity(a.lower(), b.lower())
                        if score >= 0.75:
                            G.add_edge(a, b)

            for component in nx.connected_components(G):
                # Canonical name = most frequent surface form
                sorted_by_freq = sorted(
                    component,
                    key=lambda s: len(surfaces_dict[s]),
                    reverse=True,
                )
                canonical = sorted_by_freq[0]
                all_note_ids: Set[str] = set()
                for surface in component:
                    all_note_ids.update(surfaces_dict[surface])
                    self.alias_map[surface.lower()] = canonical
                self.entity_index[canonical] = all_note_ids

    def extract_from_query(self, query: str) -> List[str]:
        """Extract entity canonical names from a query string."""
        doc = self.nlp(query)
        canonicals = []
        for ent in doc.ents:
            if ent.label_ in self.ENTITY_LABELS:
                canonical = self.alias_map.get(ent.text.lower())
                if canonical:
                    canonicals.append(canonical)
        return canonicals

    def find_notes(self, canonical_entities: List[str]) -> Set[str]:
        """Find note IDs containing any of the given canonical entities."""
        result: Set[str] = set()
        for canonical in canonical_entities:
            if canonical in self.entity_index:
                result.update(self.entity_index[canonical])
        return result

    def get_entity_signal(self, query: str) -> List[Tuple[str, float]]:
        """Return (note_id, score) pairs for entity-matched notes."""
        canonicals = self.extract_from_query(query)
        if not canonicals:
            return []
        note_ids = self.find_notes(canonicals)
        # All entity-matched notes get a uniform score (boosted via RRF position)
        return [(nid, 1.0) for nid in note_ids]
