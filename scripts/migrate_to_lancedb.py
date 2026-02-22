"""One-time migration: load existing numpy .npz embeddings and notes cache,
then bulk-insert into LanceDB.

Usage:
    python -m scripts.migrate_to_lancedb

The script reads from the configured cache directory and writes into the
configured LanceDB path.  It is safe to re-run (tables are dropped and
recreated).
"""

import json
import os
import sys

# Ensure the project root is on sys.path
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import numpy as np

from app.core.config import settings


def _load_notes():
    """Load notes from the notes_cache.json file."""
    cache_file = settings.notes_cache_file
    if not os.path.exists(cache_file):
        print(f"Notes cache not found at {cache_file}")
        print("Start the server once to build the cache, then re-run this script.")
        sys.exit(1)

    with open(cache_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Handle both formats: bare list or {"timestamp": ..., "notes": [...]}
    if isinstance(data, dict):
        notes = data.get("notes", [])
    else:
        notes = data

    print(f"Loaded {len(notes)} notes from {cache_file}")
    return notes


def _load_embeddings():
    """Load embeddings from the numpy .npz cache."""
    npz_file = settings.embeddings_cache_file
    if not os.path.exists(npz_file):
        print(f"Embeddings cache not found at {npz_file}")
        print("Start the server once to build the cache, then re-run this script.")
        sys.exit(1)

    data = np.load(npz_file)
    embeddings = data["embeddings"]
    note_indices = data["note_indices"]
    print(f"Loaded embeddings: shape={embeddings.shape}, indices={len(note_indices)}")
    return embeddings, note_indices


def _load_chunks():
    """Try to load docling chunks, fall back to legacy chunk cache."""
    # Try Docling chunk cache first
    docling_cache = os.path.join(settings.resolved_cache_dir, "docling_chunk_embeddings.npz")
    if os.path.exists(docling_cache):
        data = np.load(docling_cache, allow_pickle=True)
        if "chunks" in data:
            print(f"Loaded Docling chunks from {docling_cache}")
            return list(data["chunks"])

    # Try legacy chunk cache
    legacy_cache = os.path.join(settings.resolved_cache_dir, "chunk_embeddings.npz")
    if os.path.exists(legacy_cache):
        data = np.load(legacy_cache, allow_pickle=True)
        if "chunks" in data:
            print(f"Loaded legacy chunks from {legacy_cache}")
            return list(data["chunks"])

    print("No chunk cache found. Chunks will be empty in LanceDB.")
    return []


def main():
    print("=" * 60)
    print("  LanceDB Migration Script")
    print("=" * 60)

    # Check LanceDB availability
    try:
        import lancedb
        import pyarrow
    except ImportError as e:
        print(f"Required package not installed: {e}")
        print("Run: pip install lancedb pyarrow")
        sys.exit(1)

    # Initialize LlamaIndex service for embeddings
    from app.services.llama_index_service import LlamaIndexService

    llama_service = LlamaIndexService(settings)
    if not llama_service.available:
        print("LlamaIndex service not available. Cannot proceed.")
        sys.exit(1)

    # Initialize LanceDB service
    from app.services.lancedb_service import LanceDBService

    db_path = settings.lancedb_path or os.path.join(
        settings.resolved_cache_dir, "lancedb"
    )
    lancedb_service = LanceDBService(db_path, llama_service.embed_model)
    if not lancedb_service.available:
        print("LanceDB service not available. Cannot proceed.")
        sys.exit(1)

    # Load data
    notes = _load_notes()
    chunks = _load_chunks()

    # Initialize tables
    print(f"\nMigrating {len(notes)} notes and {len(chunks)} chunks to LanceDB...")
    lancedb_service.initialize_tables(
        notes=notes,
        chunks=chunks,
        embed_dimension=llama_service.embed_dimension,
    )

    # Verify
    print("\nVerification:")
    test_query = "meeting notes"
    note_results = lancedb_service.search_notes(test_query, max_results=3)
    print(f"  search_notes('{test_query}'): {len(note_results)} results")
    for r in note_results:
        print(f"    - {r['title'][:50]} (score={r['score']:.3f})")

    if chunks:
        chunk_results = lancedb_service.search_chunks(test_query, max_results=3)
        print(f"  search_chunks('{test_query}'): {len(chunk_results)} results")
        for r in chunk_results:
            print(f"    - chunk from {r['title'][:50]} (score={r['score']:.3f})")

    print("\nMigration complete.")


if __name__ == "__main__":
    main()
