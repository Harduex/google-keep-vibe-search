# Implementation Plan: 10 Directly Applicable Algorithms

*Created: 2026-04-16*

System: Google Keep Vibe Search (5000 notes, RTX 3060 12GB, Ollama LLM, MiniLM-L12-v2 embeddings + CLIP ViT-B/32)

> **Note**: The research assumed BGE-M3 + SigLIP. The actual codebase uses `paraphrase-multilingual-MiniLM-L12-v2` (384d) and OpenAI CLIP. BGE-M3 sparse vectors (item 3) require a model upgrade first. All other items work with the current stack.

---

## Phase 1: Quick Wins (Week 1) — Items 1, 3-alt, 7

### 1. RRF Fusion (Replace 70/30 Linear Blend)

**File**: `app/search.py` — `search()` method (line 320)

**Current code** (line 320):
```python
text_score = (semantic_score * 0.7) + (keyword_score * 0.3)
```

**Replace with**:
```python
def _rrf_score(self, scores_by_signal: dict[str, list[tuple[int, float]]], k=60) -> dict[int, float]:
    """Reciprocal Rank Fusion. Scale-agnostic, no weight tuning needed."""
    fused = {}
    for signal_name, ranked_list in scores_by_signal.items():
        # Sort by score descending to get ranks
        sorted_items = sorted(ranked_list, key=lambda x: x[1], reverse=True)
        for rank, (note_idx, _score) in enumerate(sorted_items):
            fused[note_idx] = fused.get(note_idx, 0) + 1.0 / (k + rank + 1)
    return fused
```

**Integration**:
1. In `search()`: collect semantic scores and keyword scores as separate ranked lists
2. Pass both to `_rrf_score()`
3. If image search active, add as third signal
4. Sort by fused score, apply threshold

**Also update**: `chat_service.py` `_merge_and_rerank()` (line 122) — replace weighted score accumulation with RRF across its 4 signals (primary, context, topic, chunk)

**Effort**: 2-3 hours | **VRAM**: 0 | **Latency**: 0

---

### 3-alt. BM25 Keyword Search (Upgrade from Substring Matching)

> Original item 3 was "BGE-M3 Sparse Vectors" — requires model swap. Instead, upgrade keyword search to proper BM25 which gives a much bigger improvement over the current substring matching.

**File**: `app/search.py` — `_keyword_search()` (line 166)

**Current**: Simple substring matching (word in content). No term frequency, no IDF, no length normalization.

**Replace with**: `rank_bm25` library
```python
from rank_bm25 import BM25Okapi

# At index time (in __init__ or embedding computation):
tokenized = [doc.lower().split() for doc in self.texts]
self.bm25 = BM25Okapi(tokenized)

# At query time:
def _keyword_search(self, query: str) -> list[tuple[int, float]]:
    tokens = query.lower().split()
    scores = self.bm25.get_scores(tokens)
    return [(i, s) for i, s in enumerate(scores) if s > 0]
```

**Dependency**: `pip install rank-bm25`

**Effort**: 1-2 hours | **VRAM**: 0 | **Latency**: ~0

---

### 7. Retrieval Stopping (Query Collapse + Coverage Saturation)

**File**: `app/services/chat_service.py` — `get_conversation_aware_context()` (line 79)

**Level 1 — Query Collapse** (10 lines):
Before each retrieval call, check if the new query is a near-duplicate of a previous one:
```python
from sklearn.metrics.pairwise import cosine_similarity

def _is_duplicate_query(self, query: str, previous_queries: list[str], threshold=0.95) -> bool:
    if not previous_queries:
        return False
    q_emb = self.search_service.search_engine.model.encode([query])
    prev_embs = self.search_service.search_engine.model.encode(previous_queries)
    sims = cosine_similarity(q_emb, prev_embs)[0]
    return any(s > threshold for s in sims)
```

In `get_conversation_aware_context()`: skip context_results retrieval if context query duplicates the primary query.

**Level 2 — Coverage Saturation** (15 lines):
After retrieval, check if top-k results are all saying the same thing:
```python
def _is_saturated(self, notes: list, threshold=0.9) -> bool:
    if len(notes) < 3:
        return False
    texts = [n.get("content", "")[:500] for n in notes[:10]]
    embs = self.search_service.search_engine.model.encode(texts)
    sims = cosine_similarity(embs)
    # Average pairwise similarity (excluding diagonal)
    n = len(sims)
    avg = (sims.sum() - n) / (n * (n - 1)) if n > 1 else 0
    return avg > threshold
```

If saturated, cap results at 5 instead of sending 15 redundant notes to LLM.

**Effort**: 2-3 hours | **VRAM**: 0 | **Latency**: 0 (saves latency)

---

## Phase 2: Cross-Encoder Reranking (Week 1-2) — Item 2

### 2. Cross-Encoder Reranking

**New file**: `app/services/reranker_service.py`

```python
from sentence_transformers import CrossEncoder

class RerankerService:
    def __init__(self, model_name="cross-encoder/ms-marco-MiniLM-L6-v2"):
        self.model = CrossEncoder(model_name, max_length=512)
    
    def rerank(self, query: str, notes: list[dict], top_k=10) -> list[dict]:
        """Rerank notes by cross-encoder relevance. Input: top-N candidates."""
        pairs = [(query, n.get("title", "") + " " + n.get("content", "")[:400]) for n in notes]
        scores = self.model.predict(pairs)
        ranked = sorted(zip(notes, scores), key=lambda x: x[1], reverse=True)
        return [n for n, s in ranked[:top_k]]
```

**Integration points**:

1. **`app/core/lifespan.py`** (line 17): Initialize RerankerService, store in `app.state.reranker`
2. **`app/services/chat_service.py`** `_merge_and_rerank()` (line 122):
   - After score aggregation and sorting, take top-20 candidates
   - Pass to `reranker.rerank(query, top_20, top_k=10)`
   - Return reranked top-10 as context
3. **`app/search.py`** `search()` (line 285): Optional reranking for direct search (not just chat)

**Model**: `cross-encoder/ms-marco-MiniLM-L6-v2` — 22MB, ~1800 docs/sec on CPU, auto-downloads on first use.

**VRAM**: ~46 MB (negligible) | **Latency**: ~50-80ms for 20 pairs | **Effort**: 0.5-1 day

---

## Phase 3: Entity Resolution (Week 2) — Item 4

### 4. Entity Resolution

**New file**: `app/services/entity_service.py`

**Pipeline**:

1. **NER Extraction**: spaCy `en_core_web_sm` over each note (title + content)
   ```python
   import spacy
   nlp = spacy.load("en_core_web_sm")
   
   def extract_entities(self, notes: list[dict]) -> dict[str, list[Entity]]:
       results = {}
       for note in notes:
           text = (note.get("title", "") + " " + note.get("content", ""))[:5000]
           doc = nlp(text)
           results[note["id"]] = [
               Entity(text=ent.text, label=ent.label_, note_id=note["id"])
               for ent in doc.ents
               if ent.label_ in {"PERSON", "GPE", "ORG", "PRODUCT"}
           ]
       return results
   ```

2. **Blocking**: Only compare entities of same type. Token-prefix blocking (first 3 chars) to reduce pairs.

3. **Matching**: Jaro-Winkler similarity (`jellyfish`) + embedding cosine. Threshold 0.75.
   ```python
   import jellyfish
   
   def match_score(self, a: str, b: str) -> float:
       jw = jellyfish.jaro_winkler_similarity(a.lower(), b.lower())
       # Optional: embedding similarity for semantic aliases ("mom" → "Maria")
       return jw
   ```

4. **Clustering**: Union-Find via `networkx.connected_components()`. Canonical name = most frequent surface form.

5. **Index**: `entity_index: dict[str, set[str]]` — canonical entity → set of note IDs containing any alias.

**Integration**:
- **`app/core/lifespan.py`**: Build entity index after embeddings (CPU, ~1-2 min for 5000 notes)
- **`app/search.py`** `search()`: After RRF fusion, add entity signal:
  ```python
  # Extract entities from query
  query_entities = entity_service.extract_from_query(query)
  # Find notes containing any alias of those entities
  entity_matched_ids = entity_service.find_notes(query_entities)
  # Add as signal to RRF (or 15% boost in weighted scoring)
  ```
- **`app/services/chat_service.py`** `_merge_and_rerank()`: Entity-matched notes get additional score contribution
- **Incremental**: Hash-based cache (reuse existing `compute_notes_hash` pattern)

**Dependencies**: `spacy>=3.0`, `jellyfish`, `networkx` + `python -m spacy download en_core_web_sm`

**VRAM**: 0 (spaCy sm is CPU-only) | **Effort**: 2-3 days

---

## Phase 4: Citation Verification + Conflict Detection (Week 3) — Items 5, 6

### 5. Citation Verification (NLI-based)

**New file**: `app/services/verification_service.py`

```python
from sentence_transformers import CrossEncoder

class VerificationService:
    def __init__(self):
        self.nli_model = CrossEncoder("cross-encoder/nli-deberta-v3-small", max_length=512)
    
    def verify_citations(self, response: str, citations: list[dict], notes: list[dict]) -> list[dict]:
        """Check if cited notes actually support the claims made."""
        results = []
        for citation in citations:
            note = next((n for n in notes if n["id"] == citation["note_id"]), None)
            if not note:
                results.append({**citation, "support_score": 0, "verified": False})
                continue
            
            # Extract the sentence around the citation
            claim = self._extract_claim_context(response, citation["note_number"])
            note_text = note.get("content", "")[:500]
            
            # NLI: [entailment, neutral, contradiction]
            scores = self.nli_model.predict([(note_text, claim)])
            # Score is [contradiction, neutral, entailment] for this model
            entailment_score = float(scores[0][2]) if len(scores[0]) == 3 else float(scores[0])
            
            results.append({
                **citation,
                "claim": claim[:200],
                "support_score": round(entailment_score, 2),
                "verified": entailment_score > 0.5
            })
        return results
```

**Integration**:
- **`app/services/chat_service.py`** `stream_chat_with_protocol()` (line 245):
  After the `done` message, emit a new `verification` message:
  ```json
  {"type": "verification", "citations": [
    {"note_number": 1, "claim": "...", "support_score": 0.92, "verified": true},
    {"note_number": 3, "claim": "...", "support_score": 0.31, "verified": false}
  ]}
  ```
- **Frontend** (`client/src/hooks/useChat.ts`): Handle `verification` message type, show green/yellow/red indicators on citations

**Model**: `cross-encoder/nli-deberta-v3-small` — 370MB, <20ms/pair on GPU

---

### 6. Conflict Detection

**Add to**: `app/services/verification_service.py`

```python
def detect_conflicts(self, notes: list[dict], similarity_threshold=0.85) -> list[dict]:
    """Find contradictions between semantically similar notes."""
    # 1. Compute pairwise similarity of retrieved notes
    texts = [n.get("content", "")[:500] for n in notes]
    embs = self.search_service.search_engine.model.encode(texts)
    sims = cosine_similarity(embs)
    
    # 2. For high-similarity pairs, run NLI
    conflicts = []
    for i in range(len(notes)):
        for j in range(i + 1, len(notes)):
            if sims[i][j] > similarity_threshold:
                scores = self.nli_model.predict([(texts[i], texts[j])])
                # If contradiction score is highest
                if scores[0][0] > scores[0][1] and scores[0][0] > scores[0][2]:
                    conflicts.append({
                        "note_a": {"id": notes[i]["id"], "title": notes[i].get("title", "")},
                        "note_b": {"id": notes[j]["id"], "title": notes[j].get("title", "")},
                        "contradiction_score": float(scores[0][0])
                    })
    return conflicts
```

**Integration**:
- **`app/services/chat_service.py`** `prepare_messages_with_context()` (line 60):
  Before injecting notes into system prompt, run conflict detection. If conflicts found, append to system prompt:
  ```
  IMPORTANT: Notes #2 and #5 contain conflicting information about [topic].
  Note #2 (Oct 2) says X. Note #5 (Sep 28) says Y.
  Note #2 is more recent. Please acknowledge this conflict in your response.
  ```

**Uses same NLI model** as citation verification — no additional VRAM.

**Effort**: 3-5 days for both items 5+6 | **VRAM**: ~0.4 GB for NLI model

---

## Phase 5: Query Intelligence (Week 4) — Items 8, 9

### 8. Prompt Decomposition

**New file**: `app/services/query_service.py`

```python
class QueryService:
    def __init__(self, llm_client):
        self.llm = llm_client
    
    async def decompose_if_complex(self, query: str) -> list[str]:
        """Break complex queries into sub-queries. Gate: only for >10 words or temporal/comparative."""
        words = query.split()
        if len(words) <= 10 and not self._has_complex_markers(query):
            return [query]
        
        prompt = f"""Break this question into 2-3 simpler search queries. Return ONLY the queries, one per line.
Question: {query}"""
        
        response = await self._call_llm(prompt, max_tokens=100, temperature=0.0)
        sub_queries = [q.strip("- ").strip() for q in response.strip().split("\n") if q.strip()]
        return sub_queries[:3] or [query]
    
    def _has_complex_markers(self, query: str) -> bool:
        markers = ["compared to", "versus", "before", "after", "between", "and also",
                    "last week", "last month", "yesterday", "recently", "both"]
        return any(m in query.lower() for m in markers)
```

**Integration**:
- **`app/services/chat_service.py`** `get_conversation_aware_context()` (line 79):
  1. Decompose query into sub-queries
  2. Retrieve independently for each sub-query
  3. Merge all results via RRF
  4. Rerank merged set

**Latency**: +1.0-1.5s (one LLM call) | **Effort**: 1-2 days

---

### 9. Gap Analysis / Adaptive Retrieval (CRAG-style)

**Add to**: `app/services/query_service.py`

```python
async def retrieve_with_gap_analysis(self, query: str, initial_notes: list[dict],
                                       max_iterations=2) -> tuple[list[dict], str]:
    """CRAG-style: retrieve → check sufficiency → retrieve gaps → max 2 iterations."""
    all_notes = list(initial_notes)
    
    for i in range(max_iterations):
        sufficiency_prompt = f"""Given this question: "{query}"
And these notes:
{self._format_notes_brief(all_notes)}

Is this information sufficient to answer the question? 
Reply ONLY with: SUFFICIENT or MISSING: <what's missing>"""
        
        response = await self._call_llm(sufficiency_prompt, max_tokens=50, temperature=0.0)
        
        if response.strip().startswith("SUFFICIENT"):
            return all_notes, "sufficient"
        
        # Extract what's missing and search for it
        missing = response.replace("MISSING:", "").strip()
        gap_notes = await self.search_service.search(missing, top_k=5)
        new_ids = {n["id"] for n in all_notes}
        all_notes.extend(n for n in gap_notes if n["id"] not in new_ids)
    
    return all_notes, "best_effort"
```

**Integration**:
- After initial retrieval in `get_conversation_aware_context()`, optionally run gap analysis
- If `status == "best_effort"` after 2 iterations, prepend to system prompt:
  `"Note: Your notes may not contain complete information about this topic. Be honest about gaps."`

**Latency**: +1.2-2.0s per iteration | **Effort**: 2-3 days

---

## Phase 6: Late Chunking (Later) — Item 10

### 10. Late Chunking

> Deferred. Requires switching to a model with token-level output (BGE-M3, Jina). Not compatible with current MiniLM-L12-v2 architecture. Implement after potential model upgrade.

**Prerequisites**:
1. Switch embedding model to BGE-M3 (`BAAI/bge-m3`, 568M, ~1.1GB VRAM)
2. BGE-M3 supports 8192 token window + token-level embeddings + sparse vectors

**Then**:
- Embed full note through BGE-M3 at token level
- Mean-pool per chunk boundary (reuse existing `ChunkingService` boundaries)
- Chunks retain global document context → +2-7% nDCG@10

**This also unlocks Item 3** (BGE-M3 Sparse Vectors) via `return_sparse=True`.

---

## VRAM Budget (All Loaded Simultaneously)

| Component | VRAM |
|---|---|
| MiniLM-L12-v2 (existing) | ~0.2 GB |
| CLIP ViT-B/32 (existing) | ~0.35 GB |
| ms-marco-MiniLM-L6-v2 reranker | ~0.05 GB |
| nli-deberta-v3-small (verification + conflict) | ~0.4 GB |
| Ollama LLM (8B Q4) | ~4.5 GB |
| **Total** | **~5.5 GB / 12 GB** |

Headroom: ~6.5 GB free. Room for future BGE-M3 upgrade (~1.1 GB).

---

## New Dependencies

```
rank-bm25              # BM25 keyword search
spacy>=3.0             # NER for entity resolution
jellyfish              # String similarity (Jaro-Winkler)
networkx               # Graph clustering for entity resolution
# sentence-transformers already installed (for cross-encoders)

# Models to download:
#   python -m spacy download en_core_web_sm        (12 MB)
#   cross-encoder/ms-marco-MiniLM-L6-v2            (22 MB, auto-download)
#   cross-encoder/nli-deberta-v3-small              (370 MB, auto-download)
```

---

## Implementation Order

```
Week 1:
  Day 1:  RRF fusion in search.py + chat_service.py (item 1)          ✅ DONE
  Day 1:  BM25 keyword upgrade (item 3-alt)                           ✅ DONE
  Day 1:  Retrieval stopping (item 7)                                 ✅ DONE
  Day 2-3: Cross-encoder reranker service (item 2)

Week 2:
  Day 1-3: Entity Resolution service (item 4)

Week 3:
  Day 1-2: Citation verification (item 5)
  Day 3-5: Conflict detection (item 6)

Week 4:
  Day 1-2: Prompt decomposition (item 8)
  Day 3-5: Gap analysis / CRAG (item 9)

Later:
  Model upgrade to BGE-M3 → Late Chunking + Sparse Vectors (item 10 + item 3)
```

---

## Testing Strategy

Each item gets:
1. **Unit tests** in `tests/` — mock models, test scoring logic
2. **Integration test** — verify end-to-end search quality improvement
3. **A/B comparison** — before/after on 10 sample queries, measure:
   - Relevance (manual rating 1-5)
   - Latency (ms)
   - VRAM usage (nvidia-smi)

Key test files to add:
- `tests/test_rrf_fusion.py`
- `tests/test_reranker_service.py`
- `tests/test_entity_service.py`
- `tests/test_verification_service.py`
- `tests/test_query_service.py`
