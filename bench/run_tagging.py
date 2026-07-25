"""Tier-2 tagging benchmark: does the grouping stage recover known categories?

Runs the real embed → UMAP → HDBSCAN path over 20 Newsgroups and scores the clusters
against the 20 known labels with ARI / NMI / V-measure, plus the share of documents left
unclustered and the cluster count.

This is the only measurement in the plan that can say tagging got *better* rather than
merely more stable. It scores the grouping, not the tag names: naming is one LLM call per
cluster and the label set here has no ground-truth names to score against, so the LLM is
not called at all and `llm_calls` is reported as 0.

Writes `bench/.run/newsgroups20_current.json`. Exits non-zero rather than inventing numbers
if the corpus is unavailable.
"""

import json
import os
import random
import sys
import time
from typing import List, Tuple

from bench import BENCH_CACHE_DIR, RUN_DIR, assert_cache_isolated
from bench.corpora import load_newsgroups20
from bench.metrics import ari, nmi, v_measure

# 20 Newsgroups is ~18k documents; UMAP over all of them is tens of minutes. The default
# sample keeps every category represented while holding a run to a few minutes.
DOC_BUDGET = int(os.getenv("BENCH_DOCS", "2000"))
SAMPLE_SEED = int(os.getenv("BENCH_SEED", "20260725"))

HEADER = [
    "Domain shift: newsgroup posts are not personal notes. This measures the grouping —",
    "deltas transfer, absolute numbers do not.",
    "Gameable: tuning to maximise NMI here can make tagging worse on personal notes. The",
    "baseline is a tripwire and an ablation tool, never an optimisation target.",
    "Not a CI gate: real models, minutes and a GPU. Never wired into `make check`.",
]


def sample_docs(docs: List[str], labels: List[int], budget: int, seed: int) -> Tuple[List, List]:
    """Deterministic sample, stratified so every category keeps roughly its share."""
    rng = random.Random(seed)
    by_label = {}
    for doc, label in zip(docs, labels):
        if doc and doc.strip():
            by_label.setdefault(label, []).append(doc)

    per_label = max(1, budget // max(1, len(by_label)))
    sampled_docs: List[str] = []
    sampled_labels: List[int] = []
    for label in sorted(by_label):
        pool = by_label[label]
        picked = pool if len(pool) <= per_label else rng.sample(pool, per_label)
        sampled_docs.extend(picked)
        sampled_labels.extend([label] * len(picked))

    order = list(range(len(sampled_docs)))
    rng.shuffle(order)
    return [sampled_docs[i] for i in order], [sampled_labels[i] for i in order]


def run() -> int:
    for line in HEADER:
        print(line)
    print()

    corpus = load_newsgroups20()
    if corpus is None or corpus.labels is None:
        print(
            "20 Newsgroups is not available locally. Run `make bench-fetch` first — this "
            "benchmark does not substitute placeholder numbers.",
            file=sys.stderr,
        )
        return 1

    docs, labels = sample_docs(corpus.docs, corpus.labels, DOC_BUDGET, SAMPLE_SEED)
    print(
        f"20 Newsgroups sample: {len(docs)} docs, {len(set(labels))} categories, seed {SAMPLE_SEED}"
    )

    from app.services.tagging.cluster import cluster_notes
    from app.services.tagging.embed import embed_notes
    from app.services.tagging.preprocess import clean_note

    # The cache was isolated in bench/__init__ before these imports; verify it took effect.
    assert_cache_isolated()

    cleaned = [clean_note(doc) for doc in docs]
    keep = [i for i, text in enumerate(cleaned) if text and text.strip()]
    cleaned = [cleaned[i] for i in keep]
    labels = [labels[i] for i in keep]
    print(f"After preprocessing: {len(cleaned)} docs")

    t0 = time.perf_counter()
    embeddings = embed_notes(cleaned)
    embed_seconds = time.perf_counter() - t0

    t1 = time.perf_counter()
    cluster_labels, _probabilities = cluster_notes(embeddings)
    cluster_seconds = time.perf_counter() - t1

    predicted = [int(label) for label in cluster_labels]
    unclustered = sum(1 for label in predicted if label == -1)
    n_clusters = len({label for label in predicted if label != -1})

    metrics = {
        "ari": round(ari(labels, predicted), 4),
        "nmi": round(nmi(labels, predicted), 4),
        "v_measure": round(v_measure(labels, predicted), 4),
        "untagged_percent": round(100.0 * unclustered / max(1, len(predicted)), 2),
        "tag_count": n_clusters,
        "llm_calls": 0,
    }

    print("\n--- Tagging quality (20 Newsgroups) ---")
    print(f"{'metric':<18} | value")
    print("-" * 30)
    for name, value in metrics.items():
        print(f"{name:<18} | {value}")
    print(
        f"\nembed {embed_seconds:.1f}s · cluster {cluster_seconds:.1f}s · "
        f"{len(cleaned)} docs · {len(set(labels))} true categories"
    )
    print("Naming not exercised: no ground-truth tag names in this corpus, so 0 LLM calls.")

    payload = {
        "corpus": "newsgroups20",
        "sample": {"docs": len(cleaned), "categories": len(set(labels)), "seed": SAMPLE_SEED},
        "embed_seconds": round(embed_seconds, 1),
        "cluster_seconds": round(cluster_seconds, 1),
        "metrics": metrics,
    }
    out_path = RUN_DIR / "newsgroups20_current.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
    print(f"\nWrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(run())
