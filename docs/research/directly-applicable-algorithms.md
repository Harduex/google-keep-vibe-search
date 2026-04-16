# Directly Applicable Algorithms — Implementation Priorities

*Research date: 2026-04-16*

Ordered by relevance to Google Keep Vibe Search (5000 notes, RTX 3060 12GB, Ollama LLM, BGE-M3 + SigLIP embeddings).

---

## 1. RRF Fusion (Replace 70/30 Linear Blend)

**Problem**: Cosine similarity and BM25/keyword scores live in different numerical ranges. Linear blending is fundamentally broken.

**Solution**: Reciprocal Rank Fusion — `score(d) = Σ 1/(60 + rank)` per ranked list. Scale-agnostic, no tuning needed. Industry standard (Qdrant, Weaviate, Azure AI Search).

**Effort**: ~1 day | **VRAM**: 0 | **Latency**: 0

---

## 2. Cross-Encoder Reranking

**Model**: `ms-marco-MiniLM-L6-v2` (22.7M params, 46MB VRAM)

**How**: Retrieve top-100 candidates, rerank to top-10 with cross-encoder. +5-15% relevance improvement.

**Latency**: ~80-100ms on RTX 3060 | **Effort**: ~1 day

Alternative: `BAAI/bge-reranker-v2-m3` (567M, 1.1GB) for BEIR SOTA, but 400-700ms latency.

---

## 3. BGE-M3 Sparse Vectors (Free Upgrade)

BGE-M3 already outputs learned sparse `lexical_weights` via `return_sparse=True`. Matches or beats BM25 with same tokenizer as dense vectors. No separate index needed.

**Effort**: Hours | **VRAM**: 0 | **Latency**: 0

---

## 4. Entity Resolution

**Pipeline**: spaCy NER extraction (20-40s, CPU) → Jaro-Winkler + embedding matching → Union-Find clustering → canonical entity index.

**Result**: "What did I discuss with Maria?" also finds "mom", "Mother", "M."

**Integration**: 15% entity boost in hybrid scoring (60% semantic + 25% keyword + 15% entity)

**Libraries**: `spacy`, `jellyfish`, `networkx` | **VRAM**: 0 | **Effort**: 2-3 days

---

## 5. Citation Verification (PRM-Inspired)

**Model**: `cross-encoder/nli-deberta-v3-small` (184M, 370MB, <20ms/pair)

**How**: For each `[Note #N]` citation, NLI entailment check: does cited note actually support the claim?

**UI**: Green/yellow/red confidence indicators. New `verification` streaming message type.

**Effort**: 1-2 days

---

## 6. Conflict Detection (Systematic Collation)

**How**: Cluster retrieved notes by similarity (>0.85) → NLI cross-encoder classifies entailment/neutral/contradiction → Annotate LLM prompt with explicit conflicts + chronological resolution.

**Uses same NLI model** as citation verification. Prevents hallucination on contradictory notes.

**Effort**: 3-5 days

---

## 7. Retrieval Stopping (Epistemic Stopping)

**Level 1**: Query collapse — skip retrieval if new query cosine >0.95 with previous. 10-20 lines.

**Level 2**: Coverage saturation — if top-k pairwise similarity >0.9, stop expanding. Prevents 15 redundant notes to LLM.

**Effort**: Half day | **VRAM**: 0 | **Latency**: 0

---

## 8. Prompt Decomposition

**How**: Break complex queries into sub-queries, retrieve independently, synthesize.

**Gate it**: Only for queries >10 words or with temporal/comparative language.

**Latency**: +1.0-1.5s | **Effort**: 2-3 days

---

## 9. Gap Analysis / Adaptive Retrieval

**How (CRAG-style)**: Retrieve → ask LLM "is this sufficient?" → if not, retrieve "what's missing" → max 2 iterations.

**Honesty**: If still low confidence after 2 iterations, say "your notes don't have this" instead of hallucinating.

**Latency**: +1.2-2.0s | **Effort**: 2-3 days

---

## 10. Late Chunking

**How**: Embed full note through BGE-M3 (token-level) → mean-pool per chunk boundary. Chunks retain global document context.

**Gain**: +2-7% nDCG@10 on longer notes (>200 tokens). Compatible with BGE-M3 (8192 token window).

**Effort**: 3-5 days

---

## VRAM Budget (All Loaded)

| Component | VRAM |
|---|---|
| BGE-M3 (existing) | ~1.1 GB |
| SigLIP (existing) | ~0.8 GB |
| MiniLM-L6-v2 reranker | ~46 MB |
| NLI-DeBERTa (citation + conflict) | ~0.4 GB |
| Ollama Llama 3 8B Q4 | ~4.5 GB |
| **Total** | **~6.8 GB / 12 GB** |

## Implementation Order

```
Week 1:  RRF fusion + Cross-encoder reranker + BGE-M3 sparse (items 1-3)
Week 2:  Entity Resolution (item 4)
Week 3:  Citation verification + Conflict detection (items 5-6)
Week 4:  Prompt decomposition + Gap analysis (items 8-9)
Anytime: Retrieval stopping (item 7, trivial)
Later:   Late chunking (item 10)
```

## Dependencies to Add

```
spacy>=3.0
jellyfish
networkx
# Models:
#   python -m spacy download en_core_web_sm
#   cross-encoder/ms-marco-MiniLM-L6-v2 (auto-download, 22MB)
#   cross-encoder/nli-deberta-v3-small (auto-download, 370MB)
```
