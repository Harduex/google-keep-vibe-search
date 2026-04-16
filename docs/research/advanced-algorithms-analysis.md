# Advanced Algorithms Analysis for Google Keep Vibe Search

*Research date: 2026-04-16*

## Overview

Analysis of 8 advanced algorithms for potential integration into the vibe search system. The system currently uses multi-signal RAG (BGE-M3 semantic + keyword + UMAP/HDBSCAN topic clustering), hybrid scoring (70% semantic + 30% keyword), local Ollama LLM on RTX 3060 (12GB VRAM), and streaming chat with citation parsing.

## Verdict Summary

| Algorithm | Fit | Value | Effort | Action |
|---|---|---|---|---|
| Entity Resolution | Strong | High | 2-3 days | **Build** |
| Tripartite Orchestration (RRF + reranker) | Strong | High | 1-2 days | **Build** |
| PRMs / Cross-encoder reranking | Strong | High | 1-2 days | **Build** |
| Systematic Collation (conflict detection) | Moderate | Medium-High | 3-5 days | Build after Tier 1 |
| Dynamic Epistemic Stopping | Moderate | Medium | 0.5-1 day | Quick win |
| AB-MCTS | Niche | Low-Medium | 2-3 days | Optional |
| MCTS (full tree search) | Poor | Low | High | Skip |
| BiRM | Niche | Low-Medium | 1-2 weeks | Skip |

---

## Tier 1: Build These

### 1. Entity Resolution

**Problem**: Personal notes have inconsistent references — "mom", "Mother", "Maria" are the same person. Current semantic search catches some aliases via embedding similarity but cannot transitively chain references or build a persistent alias graph.

**Pipeline**:
1. **NER extraction**: spaCy `en_core_web_sm` over each note's title+content at index time. ~20-40s for 5000 notes on CPU. Extract PERSON, GPE, ORG, PRODUCT entities.
2. **Blocking**: Type-blocking (only compare PERSON vs PERSON) + token-prefix blocking (first 3 chars). Reduces O(n^2) pairs to manageable set.
3. **Matching**: Jaro-Winkler string similarity (`jellyfish`) + BGE-M3 embedding cosine similarity. Threshold ~0.75 for match.
4. **Clustering**: Union-Find via `networkx.connected_components()` for transitive closure. Canonical name = most frequent surface form.
5. **Incremental**: Uses existing `compute_notes_hash()` — only re-process changed notes.

**Integration points**:
- New `app/services/entity_service.py` with `EntityService` class
- `app/search.py` — entity-matched notes get 15% boost: `60% semantic + 25% keyword + 15% entity`
- `app/core/lifespan.py` — build entity index alongside embeddings at startup
- `app/services/categorization_service.py` — entity features enrich cluster naming prompts

**Libraries**: `spacy`, `jellyfish`, `networkx`

**Performance**: Full build ~1-2 min. Incremental <5s. Zero VRAM (spaCy sm is CPU-only).

**Key benefit**: "What did I discuss with Maria?" finds notes mentioning "mom", "Mother", "M." — no embedding luck required.

---

### 2. Tripartite Orchestration (Signal Fusion Improvements)

**Problem**: Static 70/30 semantic/keyword blend. No adaptive behavior. Empty keyword results still contribute 30% of nothing.

**Three improvements**:

1. **Reciprocal Rank Fusion (RRF)** replaces linear weights:
   ```
   score = Σ 1/(60 + rank_i) for each signal
   ```
   No weight tuning needed. Outperforms linear combination in most benchmarks.

2. **Cross-encoder reranker** (`cross-encoder/ms-marco-MiniLM-L6-v2`, 22MB): reranks top-15 candidates after initial retrieval. ~1800 docs/sec on CPU.

3. **Fallback logic** in `_merge_and_rerank`:
   - If keyword returns 0 results → pure semantic
   - If cluster has intra-similarity >0.9 → boost cluster results
   - If two signals return disjoint sets → flag query ambiguity

**Integration points**:
- `app/search.py` — RRF fusion method
- `app/services/chat_service.py` — `_merge_and_rerank` gains orchestration rules + reranker

**Libraries**: `sentence-transformers` (for cross-encoders, likely already installed)

**VRAM**: MiniLM-L6-v2 is 22MB. Negligible.

---

### 3. PRMs via Cross-Encoder Reranking + Citation Verification

**Background**: Process Reward Models (PRMs) score each step of reasoning, not just the final answer. The PRM800K paper showed process supervision significantly outperforms outcome supervision. For RAG, "steps" = retrieval decisions and citation claims.

**Practical implementation** (no training required):

1. **Retrieval reranking** — `BAAI/bge-reranker-v2-m3` (0.6B, 1.2GB VRAM FP16): replaces cosine similarity as relevance scorer in `_merge_and_rerank`. Scores 20-50 pairs in <100ms on RTX 3060. Expected ~15-25% improvement in retrieval precision.

2. **Citation verification** — `cross-encoder/nli-deberta-v3-small` (184M, ~370MB): for each `[Note #N]` citation, check if the cited note actually supports the claim via NLI entailment. <20ms per pair on GPU.

3. **Streaming protocol extension**: New `verification` message type after `done`:
   ```json
   {"type": "verification", "citations": [
     {"note_number": 3, "claim": "...", "support_score": 0.92, "verified": true},
     {"note_number": 7, "claim": "...", "support_score": 0.31, "verified": false}
   ]}
   ```
   Frontend shows green/yellow/red confidence indicators on citations.

**Integration points**:
- `app/services/chat_service.py` — reranker in `_merge_and_rerank`, scoring in `get_conversation_aware_context`
- `app/services/citation_service.py` — `verify_citations()` function with NLI model
- `stream_chat_with_protocol` — emit `verification` message after `done`

**VRAM budget**: bge-reranker (1.2GB) + nli-deberta (0.4GB) + BGE-M3 (existing) + Ollama 7B Q4 (~4.5GB) = ~8-9GB. Fits in 12GB.

**Related papers**: Self-RAG (arXiv:2310.11511), R3-RAG (arXiv:2505.23794), OmegaPRM (arXiv:2406.06592), BiPRM (arXiv:2508.01682).

---

## Tier 2: Build After Tier 1

### 4. Systematic Collation (Conflict Detection)

**Origin**: Textual criticism — comparing manuscript variants. The tool CollateX implements this for literary texts but is over-engineered for notes.

**What actually applies**: NLI-based contradiction detection between retrieved notes. When two notes discuss the same topic but disagree ("Meeting moved to Thursday" vs "Meeting is on Wednesday"), detect and annotate the conflict.

**Pipeline**:
1. Cluster retrieved notes by semantic similarity (>0.85 = likely variants of same fact)
2. Run NLI cross-encoder on pairs within each cluster
3. Classify as entailment/neutral/contradiction
4. Annotate LLM prompt: "These two notes conflict on the meeting date: Note A (Oct 2) says Thursday, Note B (Sep 28) says Wednesday. Note A is more recent."

**Uses the same NLI model** as citation verification (deberta-v3-small). New `CollationService` adds ~50-100ms per query.

**Key benefit**: Prevents LLM hallucination when notes genuinely contradict. Particularly valuable for time-sensitive info (schedules, prices, decisions).

**Related research**: SeCon-RAG (semantic conflict-aware filtering), MAGIC benchmark (knowledge conflict detection), CARE (context assessor for unreliable passages).

---

### 5. Dynamic Epistemic Stopping

**Honesty note**: "Dynamic Epistemic Stopping" does not exist as a named algorithm in any literature. The concept (knowing when to stop retrieving) is real and researched under different names.

**Real papers**: Stop-RAG (arXiv:2510.14337), MiCP (arXiv:2604.01413), TSSS (arXiv:2510.19171), FLARE (arXiv:2305.06983).

**Practical levels for this project**:

- **Level 1 — Query collapse** (trivial): Before each retrieval expansion, check if current query duplicates a previous one (cosine >0.95 via existing embeddings). 10-20 lines. Zero cost.

- **Level 2 — Coverage saturation**: After retrieval, compute pairwise similarity of top-k results. If avg >0.9 (all notes saying the same thing), stop expanding. Prevents sending 15 redundant notes to the LLM.

Skip Levels 3-4 (RL-based stopping, confidence monitoring) — over-engineered for 5000 notes.

---

## Tier 3: Skip or Defer

### 6. MCTS (Monte Carlo Tree Search)

**The latency kills it.** MCTS requires many rollouts, each needing LLM inference. Even 8 rollouts on RTX 3060: 64-170 seconds per query. Current search runs in <100ms.

**One viable subset** ("MCTS-lite"): Generate 5 query variants with a single Ollama call, run all 5 through existing search, pick best result set. Total: ~2.5s. Worth considering as a "deep search" toggle.

**Key papers**: MCTSr (arXiv:2406.07394), MCTS-RAG (arXiv:2503.20757, GitHub: yale-nlp/MCTS-RAG), AirRAG (arXiv:2501.10053), CARROT (wang0702/CARROT — MCTS chunk combination).

### 7. AB-MCTS (Adaptive Branching)

**Clarification**: AB = "Adaptive Branching" (not Alpha-Beta). Paper: arXiv:2503.04412 (SakanaAI, NeurIPS 2025). Library: `pip install treequest`.

Dynamically decides whether to explore new search strategies ("go wider") or refine the best one ("go deeper"). Could adaptively select which search signal (semantic/keyword/topic) performs best per query using embedding-based reward. But RRF fusion achieves similar adaptive behavior with much less complexity.

### 8. BiRM (Bidirectional Process Reward Model)

Paper: arXiv:2508.01682. Adds right-to-left evaluation stream to PRMs via prompt reversal. 0.3% extra parameters, 37.7% improvement in step-level error detection. Only relevant after PRM pipeline (Tier 1 item 3) is working. The bidirectionality specifically helps citation verification — seeing both the question and the final claim improves support scoring.

---

## Implementation Order

```
Week 1:  Cross-encoder reranker + RRF fusion (items 2+3)
Week 2:  Entity Resolution service (item 1)  
Week 3:  Citation verification + conflict detection (items 3+4)
Anytime: Epistemic stopping levels 1-2 (item 5, trivial)
```

## New Dependencies

```
spacy>=3.0           # NER for entity resolution
jellyfish            # String similarity (Jaro-Winkler)
networkx             # Graph clustering for ER
# sentence-transformers likely already installed for cross-encoders
# Models to download:
#   en_core_web_sm (spaCy, 12MB)
#   cross-encoder/ms-marco-MiniLM-L6-v2 (22MB)
#   BAAI/bge-reranker-v2-m3 (1.2GB)
#   cross-encoder/nli-deberta-v3-small (370MB)
```

## VRAM Budget (all loaded simultaneously)

| Model | VRAM |
|---|---|
| BGE-M3 (existing) | ~2GB |
| bge-reranker-v2-m3 | ~1.2GB |
| nli-deberta-v3-small | ~0.4GB |
| Ollama 7B Q4 | ~4.5GB |
| **Total** | **~8.1GB / 12GB** |
