"""Tier-2 retrieval benchmark: signal ablation over a real IR corpus, real models.

Runs the shipped `VibeSearch` stack over BEIR SciFact with real judgments and reports
recall@{1,5,10}, MRR and nDCG@10 per signal combination, plus a per-signal verdict and the
latency each signal costs.

Writes `bench/.run/scifact_current.json` for `bench/compare.py`. It never invents a number:
if the corpus is not available it exits non-zero and writes nothing.
"""

import json
import os
import random
import shutil
import sys
import time
from typing import Dict, List, Set, Tuple

from bench import BENCH_CACHE_DIR, RUN_DIR, assert_cache_isolated
from bench.ablation import build_rankers
from bench.corpora import BenchCorpus, load_beir_scifact
from bench.metrics import mrr, ndcg_at_k, recall_at_k

# Sample sizes. The full corpus is ~5k docs / 300 test queries; the defaults keep a run in
# the low minutes on one GPU while staying well above the noise floor. Override for a fuller
# run — the sample is recorded in the report and in the baseline, and comparing two runs
# taken at different sample sizes is not meaningful.
DOC_BUDGET = int(os.getenv("BENCH_DOCS", "1200"))
QUERY_BUDGET = int(os.getenv("BENCH_QUERIES", "100"))
SAMPLE_SEED = int(os.getenv("BENCH_SEED", "20260725"))

HEADER = [
    "Domain shift: medical abstracts are not personal notes. This measures the engine —",
    "deltas transfer, absolute numbers do not.",
    "Not a CI gate: real models over a real corpus, minutes and a GPU. Never wired into",
    "`make check`.",
]


def sample_corpus(
    corpus: BenchCorpus, n_queries: int, n_docs: int, seed: int
) -> Tuple[List[str], List[str], Dict[int, Set[int]]]:
    """Take a deterministic sample that keeps every judgment for the sampled queries.

    Relevant docs are always kept — dropping them would deflate recall and read as a
    regression that never happened.
    """
    rng = random.Random(seed)
    judged = sorted(qid for qid, rel in (corpus.qrels or {}).items() if rel)
    picked_queries = judged if len(judged) <= n_queries else rng.sample(judged, n_queries)
    picked_queries.sort()

    required_docs: Set[int] = set()
    for qid in picked_queries:
        required_docs |= corpus.qrels[qid]

    filler = [i for i in range(len(corpus.docs)) if i not in required_docs]
    rng.shuffle(filler)
    budget = max(0, n_docs - len(required_docs))
    doc_ids = sorted(required_docs | set(filler[:budget]))

    doc_remap = {old: new for new, old in enumerate(doc_ids)}
    docs = [corpus.docs[i] for i in doc_ids]
    queries = [corpus.queries[qid] for qid in picked_queries]
    qrels = {
        new_qid: {doc_remap[d] for d in corpus.qrels[old_qid]}
        for new_qid, old_qid in enumerate(picked_queries)
    }
    return docs, queries, qrels


def as_notes(docs: List[str]) -> List[Dict[str, object]]:
    """Shape corpus documents like the note dicts the engine expects."""
    notes = []
    for i, text in enumerate(docs):
        notes.append(
            {
                "id": f"doc_{i}",
                "title": text[:80],
                "content": text,
                "created": "2024-01-01 00:00:00",
                "edited": "2024-01-01 00:00:00",
                "archived": False,
                "pinned": False,
            }
        )
    return notes


def evaluate(ranker, queries: List[str], qrels: Dict[int, Set[int]]) -> Dict[str, float]:
    """Mean metrics over the query set, plus mean per-query latency."""
    totals = {"recall@1": 0.0, "recall@5": 0.0, "recall@10": 0.0, "mrr": 0.0, "ndcg@10": 0.0}
    elapsed = 0.0
    for qid, query in enumerate(queries):
        expected = {f"doc_{d}" for d in qrels.get(qid, set())}
        t0 = time.perf_counter()
        ranked = ranker(query)
        elapsed += time.perf_counter() - t0
        totals["recall@1"] += recall_at_k(expected, ranked, 1)
        totals["recall@5"] += recall_at_k(expected, ranked, 5)
        totals["recall@10"] += recall_at_k(expected, ranked, 10)
        totals["mrr"] += mrr(expected, ranked)
        totals["ndcg@10"] += ndcg_at_k(expected, ranked, 10)

    n = max(1, len(queries))
    metrics = {name: round(total / n, 4) for name, total in totals.items()}
    metrics["latency_ms"] = round(1000 * elapsed / n, 2)
    return metrics


def run() -> int:
    for line in HEADER:
        print(line)
    print()

    corpus = load_beir_scifact()
    if corpus is None or not corpus.queries or not corpus.qrels:
        print(
            "SciFact is not available locally. Run `make bench-fetch` first — this "
            "benchmark does not substitute placeholder numbers.",
            file=sys.stderr,
        )
        return 1

    docs, queries, qrels = sample_corpus(corpus, QUERY_BUDGET, DOC_BUDGET, SAMPLE_SEED)
    print(f"SciFact sample: {len(docs)} docs, {len(queries)} judged queries, seed {SAMPLE_SEED}")

    # Imported here so the corpus check above does not pay for torch.
    from app.search import VibeSearch
    from app.services.chunking_service import ChunkingService
    from app.services.entity_service import EntityService
    from app.services.reranker_service import RerankerService

    # The cache was isolated in bench/__init__ *before* these imports could construct
    # `settings`; verify it took effect rather than trusting it.
    assert_cache_isolated()

    notes = as_notes(docs)
    cache_dir = str(BENCH_CACHE_DIR)

    t_build = time.perf_counter()
    engine = VibeSearch(notes, force_refresh=True)
    entity_service = EntityService(notes, cache_dir=cache_dir)
    chunk_service = ChunkingService(engine.model)
    chunk_service.build_chunks(notes)
    chunk_service.load_or_compute_embeddings()
    reranker = RerankerService()
    build_seconds = time.perf_counter() - t_build
    print(f"Index build: {build_seconds:.1f}s\n")

    rankers = build_rankers(engine, entity_service, chunk_service, reranker)
    # `full` is `plus_rerank` in this configuration — decomposition and CRAG need an LLM
    # call per query and are reported as skipped rather than silently folded in — so it is
    # measured once and copied rather than run twice.
    measured = {name: fn for name, fn in rankers.items() if name != "full"}

    metrics: Dict[str, Dict[str, float]] = {}
    for name, ranker in measured.items():
        metrics[name] = evaluate(ranker, queries, qrels)
        print(f"  measured {name}")
    metrics["full"] = dict(metrics["plus_rerank"])

    print("\n--- Signal ablation (SciFact) ---")
    header = (
        f"{'combination':<14} | {'R@1':<6} | {'R@5':<6} | {'R@10':<6} | "
        f"{'MRR':<6} | {'nDCG@10':<7} | ms/query"
    )
    print(header)
    print("-" * len(header))
    for name, row in metrics.items():
        print(
            f"{name:<14} | {row['recall@1']:<6.3f} | {row['recall@5']:<6.3f} | "
            f"{row['recall@10']:<6.3f} | {row['mrr']:<6.3f} | {row['ndcg@10']:<7.3f} | "
            f"{row['latency_ms']:.1f}"
        )

    print("\n--- Per-signal verdict (vs the row above, on MRR) ---")
    ladder = list(measured.keys())
    for previous, name in zip(ladder, ladder[1:]):
        delta = metrics[name]["mrr"] - metrics[previous]["mrr"]
        cost = metrics[name]["latency_ms"] - metrics[previous]["latency_ms"]
        verdict = "helps" if delta > 0.001 else "hurts" if delta < -0.001 else "neutral"
        print(f"{name:<14} {verdict:<8} MRR {delta:+.3f} at {cost:+.1f} ms/query")
    print("decomposition, CRAG: skipped — both require an LLM call per query.")

    payload = {
        "corpus": "scifact",
        "sample": {"docs": len(docs), "queries": len(queries), "seed": SAMPLE_SEED},
        "models": {
            "embedding": getattr(engine.model, "model_name", "unknown"),
            "reranker": getattr(reranker, "model_name", "unknown"),
        },
        "build_seconds": round(build_seconds, 1),
        "metrics": metrics,
    }
    out_path = RUN_DIR / "scifact_current.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
    print(f"\nWrote {out_path}")

    shutil.rmtree(cache_dir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(run())
