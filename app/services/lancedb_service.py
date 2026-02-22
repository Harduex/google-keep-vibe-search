"""LanceDB vector-database service.

Manages two tables inside a LanceDB database:

* **notes** -- one row per Google Keep note, with a vector embedding of
  ``"{title} {content}"``.
* **chunks** -- one row per chunk produced by the chunking services, with
  a vector embedding of the chunk text plus metadata that allows the UI
  to highlight the matching region inside the original note.

All ``lancedb`` and ``pyarrow`` imports are guarded so the application can
still start when these packages are not installed.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Union

# ---------------------------------------------------------------------------
# Optional imports
# ---------------------------------------------------------------------------

try:
    import lancedb

    _LANCEDB_AVAILABLE = True
except ImportError:
    lancedb = None  # type: ignore[assignment]
    _LANCEDB_AVAILABLE = False
    print(
        "[LanceDBService] lancedb package not found. "
        "Install lancedb to enable vector-database features."
    )

try:
    import pyarrow as pa

    _PYARROW_AVAILABLE = True
except ImportError:
    pa = None  # type: ignore[assignment]
    _PYARROW_AVAILABLE = False
    print(
        "[LanceDBService] pyarrow package not found. "
        "Install pyarrow to enable vector-database features."
    )


class LanceDBService:
    """High-level wrapper around a LanceDB database for note and chunk
    vector search."""

    NOTES_TABLE = "notes"
    CHUNKS_TABLE = "chunks"

    def __init__(self, db_path: str, embed_model: Any) -> None:
        """
        Parameters
        ----------
        db_path:
            Filesystem path for the LanceDB database directory.
        embed_model:
            A LlamaIndex embedding model instance that exposes
            ``get_text_embedding(text)`` and
            ``get_text_embedding_batch(texts)`` methods.
        """
        self.db: Optional[Any] = None
        self.embed_model = embed_model
        self._available: bool = _LANCEDB_AVAILABLE and _PYARROW_AVAILABLE

        if not self._available:
            print("[LanceDBService] Skipping initialisation (imports unavailable).")
            return

        self.db = lancedb.connect(db_path)
        print(f"[LanceDBService] Connected to LanceDB at {db_path}")

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        """Return ``True`` when the database connection is ready."""
        return self._available and self.db is not None

    # ------------------------------------------------------------------
    # Table initialisation
    # ------------------------------------------------------------------

    def initialize_tables(
        self,
        notes: List[Dict[str, Any]],
        chunks: List[Any],
        embed_dimension: int = 384,
    ) -> None:
        """Drop and recreate both the *notes* and *chunks* tables.

        Parameters
        ----------
        notes:
            List of note dictionaries (must contain at least ``id``,
            ``title``, ``content``).
        chunks:
            List of chunk objects -- either ``NoteChunk`` (legacy) or
            ``DoclingNoteChunk`` (Pydantic).  Each must expose a
            ``to_dict()`` method or be a Pydantic model with
            ``model_dump()``.
        embed_dimension:
            Dimensionality of the embedding vectors (default 384 for
            all-MiniLM-L6-v2).
        """
        if not self.available:
            print("[LanceDBService] Cannot initialise tables -- service unavailable.")
            return

        self._initialize_notes_table(notes, embed_dimension)
        self._initialize_chunks_table(chunks, embed_dimension)

    # ----- notes table ------------------------------------------------

    def _initialize_notes_table(
        self, notes: List[Dict[str, Any]], embed_dimension: int
    ) -> None:
        """Build and store the *notes* table."""
        if not notes:
            print("[LanceDBService] No notes provided; skipping notes table.")
            return

        # Drop existing table if present
        if self._table_exists(self.NOTES_TABLE):
            self.db.drop_table(self.NOTES_TABLE)

        # Build texts for embedding
        texts: List[str] = []
        valid_notes: List[Dict[str, Any]] = []
        for note in notes:
            title = note.get("title", "")
            content = note.get("content", "")
            text = f"{title} {content}".strip()
            if not text:
                continue
            texts.append(text)
            valid_notes.append(note)

        if not texts:
            print("[LanceDBService] No non-empty notes; skipping notes table.")
            return

        print(f"[LanceDBService] Embedding {len(texts)} notes...")
        embeddings = self.embed_model.get_text_embedding_batch(texts)

        # Build a PyArrow table
        schema = pa.schema(
            [
                pa.field("note_id", pa.utf8()),
                pa.field("title", pa.utf8()),
                pa.field("content", pa.utf8()),
                pa.field("created", pa.utf8()),
                pa.field("edited", pa.utf8()),
                pa.field("tag", pa.utf8()),
                pa.field("vector", pa.list_(pa.float32(), embed_dimension)),
            ]
        )

        arrays = {
            "note_id": [n.get("id", "") for n in valid_notes],
            "title": [n.get("title", "") for n in valid_notes],
            "content": [n.get("content", "") for n in valid_notes],
            "created": [n.get("created", "") for n in valid_notes],
            "edited": [n.get("edited", "") for n in valid_notes],
            "tag": [n.get("tag", "") for n in valid_notes],
            "vector": [list(e) for e in embeddings],
        }

        table = pa.table(arrays, schema=schema)
        self.db.create_table(self.NOTES_TABLE, table, mode="overwrite")
        print(f"[LanceDBService] Created notes table with {len(valid_notes)} rows.")

    # ----- chunks table -----------------------------------------------

    def _initialize_chunks_table(
        self, chunks: List[Any], embed_dimension: int
    ) -> None:
        """Build and store the *chunks* table."""
        if not chunks:
            print("[LanceDBService] No chunks provided; skipping chunks table.")
            return

        # Drop existing table if present
        if self._table_exists(self.CHUNKS_TABLE):
            self.db.drop_table(self.CHUNKS_TABLE)

        # Normalise each chunk into a flat dict
        chunk_dicts: List[Dict[str, Any]] = []
        texts: List[str] = []
        for chunk in chunks:
            d = self._chunk_to_dict(chunk)
            text = d.get("text", "")
            if not text:
                continue
            chunk_dicts.append(d)
            texts.append(text)

        if not texts:
            print("[LanceDBService] No non-empty chunks; skipping chunks table.")
            return

        print(f"[LanceDBService] Embedding {len(texts)} chunks...")
        embeddings = self.embed_model.get_text_embedding_batch(texts)

        schema = pa.schema(
            [
                pa.field("chunk_id", pa.utf8()),
                pa.field("note_id", pa.utf8()),
                pa.field("chunk_index", pa.int32()),
                pa.field("text", pa.utf8()),
                pa.field("title", pa.utf8()),
                pa.field("start_char_idx", pa.int32()),
                pa.field("end_char_idx", pa.int32()),
                pa.field("heading_trail", pa.utf8()),  # JSON-encoded list
                pa.field("created", pa.utf8()),
                pa.field("edited", pa.utf8()),
                pa.field("tag", pa.utf8()),
                pa.field("vector", pa.list_(pa.float32(), embed_dimension)),
            ]
        )

        arrays = {
            "chunk_id": [
                f"{d['note_id']}_c{d['chunk_index']}" for d in chunk_dicts
            ],
            "note_id": [d.get("note_id", "") for d in chunk_dicts],
            "chunk_index": [d.get("chunk_index", 0) for d in chunk_dicts],
            "text": [d.get("text", "") for d in chunk_dicts],
            "title": [d.get("title", "") for d in chunk_dicts],
            "start_char_idx": [d.get("start_char_idx", 0) for d in chunk_dicts],
            "end_char_idx": [d.get("end_char_idx", 0) for d in chunk_dicts],
            "heading_trail": [
                json.dumps(d.get("heading_trail", [])) for d in chunk_dicts
            ],
            "created": [d.get("created", "") for d in chunk_dicts],
            "edited": [d.get("edited", "") for d in chunk_dicts],
            "tag": [d.get("tag", "") for d in chunk_dicts],
            "vector": [list(e) for e in embeddings],
        }

        table = pa.table(arrays, schema=schema)
        self.db.create_table(self.CHUNKS_TABLE, table, mode="overwrite")
        print(f"[LanceDBService] Created chunks table with {len(chunk_dicts)} rows.")

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search_notes(
        self, query: str, max_results: int = 10
    ) -> List[Dict[str, Any]]:
        """Embed *query* and return the closest notes by vector distance.

        Each result dict contains the stored note columns plus a ``score``
        key (``1 - distance``, higher is better).
        """
        if not self.available:
            return []

        if not self._table_exists(self.NOTES_TABLE):
            print("[LanceDBService] Notes table does not exist.")
            return []

        query_embedding = self.embed_model.get_text_embedding(query)
        table = self.db.open_table(self.NOTES_TABLE)

        raw_results = (
            table.search(query_embedding)
            .limit(max_results)
            .to_list()
        )

        results: List[Dict[str, Any]] = []
        for row in raw_results:
            results.append(
                {
                    "id": row.get("note_id", ""),
                    "title": row.get("title", ""),
                    "content": row.get("content", ""),
                    "created": row.get("created", ""),
                    "edited": row.get("edited", ""),
                    "tag": row.get("tag", ""),
                    "score": 1.0 - row.get("_distance", 0.0),
                }
            )

        return results

    def search_chunks(
        self, query: str, max_results: int = 10
    ) -> List[Dict[str, Any]]:
        """Embed *query* and return the best matching chunk per note.

        A larger number of raw chunk results is retrieved first so that
        grouping by ``note_id`` still yields enough unique notes.  For
        each note the chunk with the highest score is kept.

        Each result dict includes ``start_char_idx``, ``end_char_idx``,
        and ``heading_trail`` so the caller can highlight the matched
        region in the original note.
        """
        if not self.available:
            return []

        if not self._table_exists(self.CHUNKS_TABLE):
            print("[LanceDBService] Chunks table does not exist.")
            return []

        query_embedding = self.embed_model.get_text_embedding(query)
        table = self.db.open_table(self.CHUNKS_TABLE)

        # Fetch extra rows to allow grouping by note_id
        fetch_limit = max(max_results * 5, 50)
        raw_results = (
            table.search(query_embedding)
            .limit(fetch_limit)
            .to_list()
        )

        # Group by note_id, keeping the best (lowest distance) chunk
        best_per_note: Dict[str, Dict[str, Any]] = {}
        for row in raw_results:
            note_id = row.get("note_id", "")
            score = 1.0 - row.get("_distance", 0.0)

            if note_id not in best_per_note or score > best_per_note[note_id]["score"]:
                # Decode heading_trail from JSON string
                heading_trail_raw = row.get("heading_trail", "[]")
                try:
                    heading_trail = json.loads(heading_trail_raw)
                except (json.JSONDecodeError, TypeError):
                    heading_trail = []

                best_per_note[note_id] = {
                    "id": note_id,
                    "title": row.get("title", ""),
                    "matched_chunk": row.get("text", ""),
                    "chunk_index": row.get("chunk_index", 0),
                    "start_char_idx": row.get("start_char_idx", 0),
                    "end_char_idx": row.get("end_char_idx", 0),
                    "heading_trail": heading_trail,
                    "created": row.get("created", ""),
                    "edited": row.get("edited", ""),
                    "tag": row.get("tag", ""),
                    "score": score,
                }

        # Sort by score descending and return top max_results
        ranked = sorted(best_per_note.values(), key=lambda r: r["score"], reverse=True)
        return ranked[:max_results]

    # ------------------------------------------------------------------
    # Upsert
    # ------------------------------------------------------------------

    def upsert_notes(self, notes: List[Dict[str, Any]]) -> None:
        """Embed and add/merge notes into the notes table.

        If the notes table does not exist it will be created.  Otherwise
        rows are appended (LanceDB ``add``).  For a full re-index prefer
        ``initialize_tables`` which drops and recreates.
        """
        if not self.available:
            print("[LanceDBService] Cannot upsert -- service unavailable.")
            return

        if not notes:
            return

        texts: List[str] = []
        valid_notes: List[Dict[str, Any]] = []
        for note in notes:
            title = note.get("title", "")
            content = note.get("content", "")
            text = f"{title} {content}".strip()
            if not text:
                continue
            texts.append(text)
            valid_notes.append(note)

        if not texts:
            return

        print(f"[LanceDBService] Upserting {len(texts)} notes...")
        embeddings = self.embed_model.get_text_embedding_batch(texts)

        rows = [
            {
                "note_id": n.get("id", ""),
                "title": n.get("title", ""),
                "content": n.get("content", ""),
                "created": n.get("created", ""),
                "edited": n.get("edited", ""),
                "tag": n.get("tag", ""),
                "vector": list(e),
            }
            for n, e in zip(valid_notes, embeddings)
        ]

        if self._table_exists(self.NOTES_TABLE):
            table = self.db.open_table(self.NOTES_TABLE)
            table.add(rows)
        else:
            self.db.create_table(self.NOTES_TABLE, rows)

        print(f"[LanceDBService] Upserted {len(rows)} notes.")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _table_exists(self, name: str) -> bool:
        """Check whether a table with *name* exists in the database."""
        if self.db is None:
            return False
        try:
            result = self.db.list_tables()
            # list_tables() may return a ListTablesResponse object with .tables attr
            names = getattr(result, "tables", result)
            return name in names
        except Exception:
            return False

    @staticmethod
    def _chunk_to_dict(chunk: Any) -> Dict[str, Any]:
        """Normalise a chunk (legacy ``NoteChunk`` or Pydantic
        ``DoclingNoteChunk``) into a plain dictionary.

        Legacy ``NoteChunk`` objects lack ``start_char_idx``,
        ``end_char_idx``, ``heading_trail``, and ``source_id`` -- sensible
        defaults are provided for those fields.
        """
        # Pydantic model (DoclingNoteChunk)
        if hasattr(chunk, "model_dump"):
            return chunk.model_dump()

        # Plain object with to_dict (legacy NoteChunk)
        if hasattr(chunk, "to_dict"):
            d = chunk.to_dict()
        else:
            d = dict(chunk) if isinstance(chunk, dict) else {}

        # Ensure fields expected by the chunks table exist
        d.setdefault("start_char_idx", 0)
        d.setdefault("end_char_idx", 0)
        d.setdefault("heading_trail", [])
        d.setdefault("source_id", d.get("note_id", ""))
        return d
