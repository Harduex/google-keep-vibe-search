import os
import sys
import time
import warnings
from typing import Dict, List, Set, Tuple

# Privacy/Safety check
if os.environ.get("GOOGLE_KEEP_PATH") != ".":
    print("ERROR: GOOGLE_KEEP_PATH must be set to '.' to prevent touching real data.")
    sys.exit(1)

# Disable image search for eval to keep it fast and deterministic
os.environ["ENABLE_IMAGE_SEARCH"] = "false"
warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sentence_transformers import SentenceTransformer

from app.search import VibeSearch
from app.services.chunking_service import ChunkingService
from app.services.entity_service import EntityService
from app.services.reranker_service import RerankerService
from bench.metrics import mrr, recall_at_k
from tests.fixtures.notes import generate_synthetic_notes

GOLDEN_QUERIES: List[Tuple[str, Set[str]]] = [
    # Checklists
    ("Item 1", {"note_01.json", "note_02.json", "note_03.json", "note_04.json", "note_05.json"}),
    ("Checklist 3", {"note_03.json"}),
    # Labels
    ("Label6", {"note_06.json"}),
    ("Label7", {"note_07.json"}),
    # Bulgarian
    ("тестов бележник", {"note_09.json"}),
    ("сирене", {"note_10.json"}),
    ("мляко", {"note_10.json"}),
    ("Среща с екипа", {"note_11.json"}),
    ("сметката за ток", {"note_12.json"}),
    ("Резервация ресторант", {"note_13.json"}),
    ("Проектът петък", {"note_14.json"}),
    # Mixed
    ("български text", {"note_15.json"}),
    ("mixed with English", {"note_15.json"}),
    # Chunking
    ("long text to test chunking", {"note_16.json"}),
    # Duplicates / similar
    ("quick brown fox", {"note_17.json", "note_18.json"}),
    ("lazy dog project update", {"note_17.json", "note_18.json"}),
    # Entities
    ("Tim Cook Apple", {"note_19.json"}),
    ("California", {"note_19.json"}),
    ("Eiffel Tower Paris", {"note_20.json"}),
    ("France", {"note_20.json"}),
    # System fields
    ("archived", {"note_21.json"}),
    ("pinned", {"note_22.json"}),
    ("picture", {"note_25.json"}),
    # Standard notes
    ("Standard Note 26", {"note_26.json"}),
    ("regular content 27", {"note_27.json"}),
    ("Standard Note 28", {"note_28.json"}),
    ("regular content 29", {"note_29.json"}),
    ("Standard Note 30", {"note_30.json"}),
    ("regular content 30", {"note_30.json"}),
    ("Checklist 5", {"note_05.json"}),
]


def format_note_for_search(fid: str, n_dict: dict) -> dict:
    note = n_dict.copy()
    note["id"] = fid
    # Ensure text exists
    note["text"] = note.get("title", "") + " " + note.get("textContent", "")
    if "listContent" in note:
        for item in note["listContent"]:
            note["text"] += " " + item.get("text", "")
    return note


def main():
    t0 = time.time()

    # 1. Prepare corpus
    raw_notes = generate_synthetic_notes()
    # Filter out trashed.
    notes = [format_note_for_search(fid, n) for fid, n in raw_notes if not n.get("isTrashed")]

    print(f"Loaded {len(notes)} fixture notes.")

    # 2. Init components
    os.environ["EMBEDDING_MODEL"] = "all-MiniLM-L6-v2"
    os.environ["CACHE_DIR"] = "/tmp/fake_cache"
    os.makedirs("/tmp/fake_cache", exist_ok=True)

    engine = VibeSearch(notes, force_refresh=True)
    entity_service = EntityService(notes, cache_dir="/tmp/fake_cache")
    chunk_service = ChunkingService(engine.model)
    chunk_service.build_chunks(notes)
    chunk_service.load_or_compute_embeddings()
    reranker = RerankerService("cross-encoder/ms-marco-MiniLM-L6-v2")

    print("Evaluating signals...")

    results = {}

    def evaluate(name: str, get_ranked_list):
        r1, r5, r10, m = 0.0, 0.0, 0.0, 0.0
        n_q = len(GOLDEN_QUERIES)
        for q, expected in GOLDEN_QUERIES:
            ranked_ids = get_ranked_list(q)
            r1 += recall_at_k(expected, ranked_ids, 1)
            r5 += recall_at_k(expected, ranked_ids, 5)
            r10 += recall_at_k(expected, ranked_ids, 10)
            m += mrr(expected, ranked_ids)
        r1 /= n_q
        r5 /= n_q
        r10 /= n_q
        m /= n_q
        results[name] = (r1, r5, r10, m)

    # dense only
    def _dense(q: str):
        scores = engine._semantic_search(q)
        ranked = sorted(
            [(engine.note_indices[i], s) for i, s in enumerate(scores)],
            key=lambda x: x[1],
            reverse=True,
        )
        return [engine.notes[i]["id"] for i, _ in ranked]

    evaluate("dense only", _dense)

    # dense+BM25
    def _dense_bm25(q: str):
        semantic = [
            (engine.note_indices[i], float(engine._semantic_search(q)[i]))
            for i in range(len(engine.note_indices))
        ]
        bm25 = engine._keyword_search(q)
        fused = engine.rrf_fuse([semantic, bm25])
        ranked = sorted(fused.items(), key=lambda x: x[1], reverse=True)
        return [engine.notes[i]["id"] for i, _ in ranked]

    evaluate("dense+BM25", _dense_bm25)

    # +entity
    def _plus_entity(q: str):
        semantic = [
            (engine.note_indices[i], float(engine._semantic_search(q)[i]))
            for i in range(len(engine.note_indices))
        ]
        bm25 = engine._keyword_search(q)
        entity_pairs = entity_service.get_entity_signal(q)
        id_to_idx = {n["id"]: i for i, n in enumerate(engine.notes)}
        entity = [(id_to_idx[nid], s) for nid, s in entity_pairs if nid in id_to_idx]
        fused = engine.rrf_fuse([semantic, bm25, entity])
        ranked = sorted(fused.items(), key=lambda x: x[1], reverse=True)
        return [engine.notes[i]["id"] for i, _ in ranked]

    evaluate("+entity", _plus_entity)

    # +chunk
    def _plus_chunk(q: str):
        semantic = [
            (engine.note_indices[i], float(engine._semantic_search(q)[i]))
            for i in range(len(engine.note_indices))
        ]
        bm25 = engine._keyword_search(q)
        entity_pairs = entity_service.get_entity_signal(q)
        id_to_idx = {n["id"]: i for i, n in enumerate(engine.notes)}
        entity = [(id_to_idx[nid], s) for nid, s in entity_pairs if nid in id_to_idx]

        chunk_res = chunk_service.search_chunks(q, max_results=len(engine.notes))
        chunk_ranked = [
            (id_to_idx[n["id"]], float(n["score"])) for n in chunk_res if n["id"] in id_to_idx
        ]

        fused = engine.rrf_fuse([semantic, bm25, entity, chunk_ranked])
        ranked = sorted(fused.items(), key=lambda x: x[1], reverse=True)
        return [engine.notes[i]["id"] for i, _ in ranked]

    evaluate("+chunk", _plus_chunk)

    # +rerank
    def _plus_rerank(q: str):
        semantic = [
            (engine.note_indices[i], float(engine._semantic_search(q)[i]))
            for i in range(len(engine.note_indices))
        ]
        bm25 = engine._keyword_search(q)
        entity_pairs = entity_service.get_entity_signal(q)
        id_to_idx = {n["id"]: i for i, n in enumerate(engine.notes)}
        entity = [(id_to_idx[nid], s) for nid, s in entity_pairs if nid in id_to_idx]

        chunk_res = chunk_service.search_chunks(q, max_results=len(engine.notes))
        chunk_ranked = [
            (id_to_idx[n["id"]], float(n["score"])) for n in chunk_res if n["id"] in id_to_idx
        ]

        fused = engine.rrf_fuse([semantic, bm25, entity, chunk_ranked])
        ranked = sorted(fused.items(), key=lambda x: x[1], reverse=True)
        top_notes = [engine.notes[i] for i, _ in ranked[:20]]

        reranked = reranker.rerank(q, top_notes, top_k=20)
        return [n["id"] for n in reranked]

    evaluate("+rerank", _plus_rerank)

    # full
    def _full(q: str):
        return _plus_rerank(q)

    evaluate("full", _full)

    t1 = time.time()

    print("\n--- Retrieval Evaluation Results ---")
    print(f"{'Signal Combination':<20} | {'R@1':<5} | {'R@5':<5} | {'R@10':<5} | {'MRR':<5}")
    print("-" * 50)
    for name, (r1, r5, r10, m) in results.items():
        print(f"{name:<20} | {r1:.3f} | {r5:.3f} | {r10:.3f} | {m:.3f}")

    print("\n--- Signal Impact Analysis ---")
    base_mrr = results["dense only"][3]
    for name, (r1, r5, r10, m) in results.items():
        if name == "dense only":
            continue
        diff = m - base_mrr
        verdict = "improves" if diff > 0.001 else "degrades" if diff < -0.001 else "neutral"
        print(f"{name}: {verdict} MRR by {abs(diff):.3f}")

    print(f"\nEval completed in {t1 - t0:.2f}s")
    assert t1 - t0 < 60, "Eval took more than 60 seconds!"


if __name__ == "__main__":
    main()
