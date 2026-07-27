"""Entity resolution service for improving search via named entity matching."""

import hashlib
import json
import os
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx

from app.core.config import settings
from app.domain import ChangeSet, Document


class EntityService:
    """Extracts entities from notes, clusters aliases, and provides entity-based retrieval signal.

    Two ways to populate the index:

    - The legacy constructor takes a list of note dicts and rebuilds the
      entity index from scratch, caching it to ``entity_index.json`` keyed by
      a whole-corpus hash.
    - The :meth:`build` / :meth:`apply` interface takes content-addressed
      :class:`~app.domain.model.Document` objects. :meth:`apply` extracts
      entities only from ``added ∪ updated`` documents, drops ``removed``
      document ids from the index, and leaves ``unchanged`` entries alone —
      so one edited note does not re-extract the whole corpus.
    """

    ENTITY_LABELS = {"PERSON", "GPE", "ORG", "PRODUCT"}
    INDEX_NAME = "entity_index"

    def __init__(self, notes: List[Dict[str, Any]], cache_dir: Optional[str] = None):
        import spacy

        try:
            self.nlp = spacy.load("en_core_web_sm")
        except OSError:
            print("[entity] Downloading spaCy model 'en_core_web_sm'...")
            spacy.cli.download("en_core_web_sm")
            self.nlp = spacy.load("en_core_web_sm")
        self.cache_dir = cache_dir or settings.resolved_cache_dir
        self.entity_index: Dict[str, Set[str]] = {}  # canonical → note IDs
        self.alias_map: Dict[str, str] = {}  # surface form → canonical
        self.sqlite_store = None

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
        print(
            f"[entities] Built entity index: {len(self.entity_index)} entities from {len(notes)} notes"
        )

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

    # ------------------------------------------------------------------ #
    # Store-backed incremental interface (build / apply)
    # ------------------------------------------------------------------ #

    def build(
        self,
        documents: List[Document],
        sqlite_store=None,
    ) -> None:
        """Full rebuild from content-addressed documents.

        Entity extraction is the only per-document cost here (there are no
        dense vectors), so :meth:`build` is what today's constructor does; the
        value of the new interface is :meth:`apply`'s incremental extraction.
        """
        if sqlite_store is not None:
            self.sqlite_store = sqlite_store
        notes = [_doc_to_note_dict(d) for d in documents]
        self.entity_index = {}
        self.alias_map = {}
        raw_entities = self._extract_entities(notes)
        self._cluster_entities(raw_entities)
        if self.sqlite_store is not None:
            self._record_index_state(len(documents))

    def apply(
        self,
        change_set: ChangeSet,
        sqlite_store=None,
    ) -> None:
        """Incremental update: extract entities only from ``added ∪ updated``
        documents, drop ``removed`` document ids, leave ``unchanged`` entries.

        Newly-extracted surface forms are clustered among themselves and merged
        into the existing index; surface forms already aliased are folded into
        their existing canonical. This is approximate (a global re-cluster may
        find more aliases) but never touches the ``unchanged`` set.
        """
        if sqlite_store is not None:
            self.sqlite_store = sqlite_store

        # Drop removed and stale-updated doc ids from the index.
        for doc in change_set.removed:
            self._purge_doc_id(doc.id)
        for doc in change_set.updated:
            self._purge_doc_id(doc.id)

        changed = list(change_set.added) + list(change_set.updated)
        if changed:
            notes = [_doc_to_note_dict(d) for d in changed]
            raw = self._extract_entities(notes)
            self._merge_entities(raw)

        if self.sqlite_store is not None:
            live_doc_count = len({nid for ids in self.entity_index.values() for nid in ids})
            self._record_index_state(live_doc_count)

    def _purge_doc_id(self, doc_id: str) -> None:
        """Remove every mention of ``doc_id`` from the entity index."""
        if not doc_id:
            return
        for canonical in list(self.entity_index.keys()):
            ids = self.entity_index[canonical]
            if doc_id in ids:
                ids.discard(doc_id)
                if not ids:
                    del self.entity_index[canonical]

    def _merge_entities(self, raw_entities: Dict[str, List[Tuple[str, str]]]) -> None:
        """Merge newly-extracted entities into the existing index.

        For each new surface form, if its lowercase is already aliased, add the
        note id to that canonical's set; otherwise cluster it against existing
        canonicals of the same label (Jaro-Winkler ≥ 0.75) or create a fresh
        canonical.
        """
        import jellyfish

        # Group new mentions by label.
        mention_notes: Dict[str, Dict[str, Set[str]]] = {}
        for note_id, entities in raw_entities.items():
            for surface, label in entities:
                mention_notes.setdefault(label, {}).setdefault(surface, set()).add(note_id)

        # Existing surface forms, by label, for blocking.
        existing_by_label: Dict[str, List[str]] = {}
        for surface, canonical in self.alias_map.items():
            label = self._canonical_label(canonical)
            existing_by_label.setdefault(label, []).append(surface)

        for label, surfaces_dict in mention_notes.items():
            for surface, note_ids in surfaces_dict.items():
                key = surface.lower()
                canonical = self.alias_map.get(key)
                if canonical is None:
                    # Try to cluster against an existing surface of the same label.
                    bucket = existing_by_label.get(label, [])
                    for other in bucket:
                        if (
                            jellyfish.jaro_winkler_similarity(surface.lower(), other.lower())
                            >= 0.75
                        ):
                            canonical = self.alias_map[other.lower()]
                            break
                    if canonical is None:
                        canonical = surface
                    self.alias_map[key] = canonical
                    existing_by_label.setdefault(label, []).append(surface)
                self.entity_index.setdefault(canonical, set()).update(note_ids)

    def _canonical_label(self, canonical: str) -> str:
        """Heuristic reverse-lookup of a canonical's label.

        The index does not store labels, so we re-extract from the canonical's
        own text. This is cheap (one NLP call per merge) and only used to gate
        blocking during incremental merges.
        """
        doc = self.nlp(canonical)
        for ent in doc.ents:
            if ent.label_ in self.ENTITY_LABELS:
                return ent.label_
        return ""

    def _record_index_state(self, doc_count: int) -> None:
        if self.sqlite_store is None:
            return
        corpus_hash = hashlib.blake2s(
            "\n".join(sorted(self.entity_index.keys())).encode("utf-8"),
            digest_size=16,
        ).hexdigest()
        self.sqlite_store.set_index_state(
            self.INDEX_NAME,
            content_hash=corpus_hash,
            row_count=len(self.entity_index),
        )

    def _extract_entities(self, notes: List[Dict[str, Any]]) -> Dict[str, List[Tuple[str, str]]]:
        """Extract entities from notes. Returns {note_id: [(text, label), ...]}."""
        results: Dict[str, List[Tuple[str, str]]] = {}
        total = len(notes)
        for i, note in enumerate(notes):
            if i % 500 == 0:
                print(f"  [entity] Processing notes: {i}/{total} ({i * 100 // total}%)")
            text = (note.get("title", "") + " " + note.get("content", ""))[:5000]
            doc = self.nlp(text)
            entities = [
                (ent.text, ent.label_) for ent in doc.ents if ent.label_ in self.ENTITY_LABELS
            ]
            if entities:
                results[note.get("id", "")] = entities
        print(f"  [entity] Processing notes: {total}/{total} (100%)")
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


def _doc_to_note_dict(doc: Document) -> Dict[str, Any]:
    """Convert a Document to the dict shape the legacy extractor expects."""
    return {
        "id": doc.id,
        "title": doc.title or "",
        "content": doc.body or "",
    }
