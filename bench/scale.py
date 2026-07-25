import random
from typing import List, Optional

from bench.corpora import BenchCorpus


def inflate_corpus(corpus: BenchCorpus, target_size: int, seed: int = 42) -> BenchCorpus:
    """
    Deterministically inflates a corpus to `target_size` documents by resampling
    existing documents with token-level perturbation (randomly dropping or swapping words)
    so near-duplicate detection does not consider them identical.
    """
    if not corpus.docs or target_size <= len(corpus.docs):
        return corpus

    rng = random.Random(seed)
    new_docs = list(corpus.docs)
    new_labels = list(corpus.labels) if corpus.labels else None

    needed = target_size - len(corpus.docs)
    for i in range(needed):
        orig_idx = rng.randrange(len(corpus.docs))
        orig_text = corpus.docs[orig_idx]

        # Token-level perturbation: simple whitespace split, then drop or shuffle some
        tokens = orig_text.split()
        if not tokens:
            new_text = f"empty_variation_{i}"
        else:
            # Drop ~5% of tokens
            kept_tokens = [t for t in tokens if rng.random() > 0.05]
            if not kept_tokens:
                kept_tokens = tokens
            # Swap a few adjacent tokens
            for _ in range(max(1, len(kept_tokens) // 20)):
                idx = rng.randrange(len(kept_tokens) - 1)
                kept_tokens[idx], kept_tokens[idx + 1] = kept_tokens[idx + 1], kept_tokens[idx]

            new_text = " ".join(kept_tokens)

        new_docs.append(new_text)
        if new_labels is not None:
            new_labels.append(new_labels[orig_idx])

    return BenchCorpus(docs=new_docs, queries=corpus.queries, qrels=corpus.qrels, labels=new_labels)
