# RAG Pipeline Spec: Chat Feature

*Created: 2026-04-17*

Complete architecture reference for the Retrieval-Augmented Generation pipeline powering the chat feature.

---

## End-to-End Flow

```
POST /api/chat  (routes/chat.py)
  |
  +-- get_conversation_aware_context  (chat_service.py)
  |     +-- decompose_if_complex  --> 1-3 sub-queries  (query_service.py)
  |     +-- VibeSearch.search (primary query)  (search.py)
  |     |     +-- _semantic_search  --> cosine similarity
  |     |     +-- _keyword_search   --> BM25 scores
  |     |     +-- _image_search     --> CLIP similarity  [if enabled]
  |     |     +-- entity signal     --> NER-matched notes  [if enabled]
  |     |     +-- rrf_fuse (k=60)
  |     |     +-- reranker.rerank (top-20 -> top-N)  [if enabled]
  |     +-- search each sub-query (5 notes each)
  |     +-- search context window (last 3 user msgs, 5 notes)
  |     +-- search topic string (5 notes)  [if provided]
  |     +-- chunking_service.search_chunks
  |     +-- _merge_and_rerank  (RRF + rerank across all signals)
  |     +-- _cap_if_saturated  (cap=5 if avg sim > 0.9)
  |     +-- truncate to chat_context_notes
  |     +-- gap_analysis  (CRAG-style, max 2 iterations)  [if enabled]
  |
  +-- detect_conflicts  (verification_service.py)
  +-- _maybe_summarize_window  (LLM call for old messages)
  +-- prepare_messages_with_context  (system prompt + notes + warnings)
  +-- LLM streaming call  --> delta frames
  +-- extract_citations  --> "done" frame
  +-- verify_citations  (NLI check) --> "verification" frame
```

---

## Layer 1: Indexing

### 1.1 Note Loading (`note_service.py`, `parser.py`)

- Parses `GOOGLE_KEEP_PATH/*.json`, skips trashed notes
- Fields: id, title, content (textContent), created/edited, archived, pinned, color, annotations, attachments, tags
- Cache: `cache/notes_cache.json`, invalidated by MD5 hash of all note titles+content

### 1.2 Note-Level Embedding (`search.py`)

- Model: `paraphrase-multilingual-MiniLM-L12-v2` (384-dim, ~117M params)
- Text: `"{title} {content}"` per note
- Cache: `cache/embeddings.npz` + `cache/notes_hash.json`
- CUDA if available, else CPU

### 1.3 Chunk-Level Embedding (`chunking_service.py`)

- Short notes (<=500 chars): single chunk = entire note
- Long notes: split by paragraphs/headers/lists, merge greedily up to 1500 chars
- First chunk gets title prepended
- Same embedding model as note-level
- Cache: `cache/chunk_embeddings.npz` + `cache/chunk_hash.json`
- Search groups by note, keeps best-scoring chunk per note

| Constant | Value | Location |
|---|---|---|
| `SHORT_NOTE_THRESHOLD` | 500 chars | `chunking_service.py` |
| `MIN_CHUNK_LENGTH` | 100 chars | `chunking_service.py` |
| `MAX_CHUNK_LENGTH` | 1500 chars | `chunking_service.py` |

### 1.4 BM25 Index (`search.py`)

- `rank_bm25.BM25Okapi` over `text.lower().split()` (no stemming/stopwords)
- Note-level only (no chunk-level BM25)
- Default Okapi params: k1=1.5, b=0.75

### 1.5 Entity Index (`entity_service.py`)

- spaCy `en_core_web_sm` NER on `(title + content)[:5000]` per note
- Entity types: PERSON, GPE, ORG, PRODUCT
- Clustering: Jaro-Winkler similarity (threshold 0.75) + token-prefix blocking + networkx connected components
- Canonical name = most frequent surface form
- Cache: `cache/entity_index.json`

---

## Layer 2: Retrieval

### 2.1 `get_conversation_aware_context()` (`chat_service.py`)

Orchestrates multi-signal retrieval:

| Step | Signal | Max Notes | Condition |
|---|---|---|---|
| 1 | Prompt decomposition | 1-3 sub-queries | `enable_prompt_decomposition` + >10 words or markers |
| 2 | Primary note search | context_notes + 5 | Always (if user message exists) |
| 3 | Sub-query search | 5 per sub-query | If decomposition produced >1 query |
| 4 | Conversation context | 5 | If last 3 msgs not duplicate of primary (sim < 0.95) |
| 5 | Topic search | 5 | If topic provided and not duplicate |
| 6 | Chunk search | context_notes + 5 | Always |
| 7 | RRF merge + rerank | All signals | Always |
| 8 | Saturation cap | Cap to 5 | If avg pairwise sim > 0.9 |
| 9 | Truncate | `chat_context_notes` | Always |
| 10 | Gap analysis | +5 per iteration | `enable_gap_analysis`, max 2 iterations |

### 2.2 Prompt Decomposition (`query_service.py`)

- Complexity gate: >10 words OR contains markers ("compared to", "versus", "before/after", "between", "both", "recently", etc.)
- LLM call: `max_tokens=100, temperature=0.0`
- Returns 1-3 sub-queries, fallback to original on error

### 2.3 Gap Analysis (`query_service.py`)

- CRAG-style: LLM judges if notes are sufficient
- Prompt: "Reply SUFFICIENT or MISSING: <what>" (`max_tokens=60, temperature=0.0`)
- If MISSING: search for the gap, add new notes (dedup by id)
- Max 2 iterations, then "best_effort" status triggers system prompt warning
- Non-fatal: returns original notes on any error

---

## Layer 3: Ranking

### 3.1 RRF Fusion (`search.py`, `chat_service.py`)

```
score(note) = SUM( 1 / (60 + rank + 1) )  across all signals
```

Signals at search level: semantic, BM25, image, entity
Signals at chat level: primary, context, topic, chunks, decomposed, entity

### 3.2 Continuity Boost (`chat_service.py`)

Previously cited note IDs get RRF score x1.15.

### 3.3 Cross-Encoder Reranking (`reranker_service.py`)

- Model: `cross-encoder/ms-marco-MiniLM-L6-v2` (~22M params)
- Input: `(query, (title + content)[:400])` pairs
- Takes top-20 RRF candidates, returns top-N
- Called twice: once in `VibeSearch.search()`, once in `_merge_and_rerank()`

---

## Layer 4: Generation

### 4.1 Conversation Windowing (`chat_service.py`)

- If messages exceed `chat_max_recent_messages + 2`: summarize old messages via LLM (`max_tokens=300`)
- Keeps last 6 messages verbatim, older messages become summary

### 4.2 System Prompt (`system_prompts.py`)

With notes: `NOTES_CHAT_SYSTEM_PROMPT` — ground answers in notes, cite as `[Note #N]`, synthesize across notes, be explicit about gaps

Without notes: `NO_NOTES_SYSTEM_PROMPT` — answer from general knowledge

### 4.3 Dynamic Prompt Injections

| Condition | Injection |
|---|---|
| Conflicts detected (NLI) | "CONFLICTING NOTES DETECTED: ... prefer most recently edited note" |
| Gap analysis best_effort | "Your notes may not contain complete information... Be honest about gaps" |

### 4.4 LLM Call

- `httpx.AsyncClient` -> OpenAI-compatible `/chat/completions`
- Timeouts: connect=10s, read=120s, write=10s
- Streaming: NDJSON frames (context -> delta -> done -> verification)
- Fallback: `ollama_api_url/v1/` if `llm_api_base_url` not set

---

## Layer 5: Verification

### 5.1 Citation Extraction (`citation_service.py`)

- Regex: `[Note #N]` and `[Note #N, #M]` patterns
- Returns: note_number, note_id, note_title (deduped)

### 5.2 Citation Verification (`verification_service.py`)

- Model: `cross-encoder/nli-deberta-v3-small` (~44M params)
- Extracts claim context around each `[Note #N]` reference
- NLI prediction: label order `[contradiction, entailment, neutral]`
- Softmax over logits -> verdict: supported/contradicted/neutral
- UI: green/orange/red icons on citation chips

### 5.3 Conflict Detection (`verification_service.py`)

- Pre-filter: pairwise cosine similarity > 0.85 (same embedding model as retrieval)
- NLI batch prediction on high-similarity pairs
- Reports: note indices, titles, edit dates, contradiction score
- UI: orange warning banner in notes panel

---

## Models Summary

| Role | Model | Params | Library |
|---|---|---|---|
| Embedding | `paraphrase-multilingual-MiniLM-L12-v2` | ~117M, 384-dim | sentence-transformers |
| Reranker | `cross-encoder/ms-marco-MiniLM-L6-v2` | ~22M | sentence-transformers CrossEncoder |
| NLI | `cross-encoder/nli-deberta-v3-small` | ~44M | sentence-transformers CrossEncoder |
| NER | `en_core_web_sm` | ~12M | spaCy |
| LLM | Configurable (`llm_model`) | User-controlled | httpx -> OpenAI API |

---

## Configuration Reference

| Setting | Default | Purpose |
|---|---|---|
| `EMBEDDING_MODEL` | `paraphrase-multilingual-MiniLM-L12-v2` | Note/chunk embedding |
| `LLM_MODEL` | `llama3` | Chat generation + decomposition + gap analysis |
| `LLM_API_BASE_URL` | `""` (falls back to Ollama) | OpenAI-compatible endpoint |
| `CHAT_CONTEXT_NOTES` | `5` | Max notes in context window |
| `CHAT_MAX_RECENT_MESSAGES` | `6` | Messages kept verbatim before summarization |
| `ENABLE_RERANKER` | `True` | Cross-encoder reranking |
| `RERANKER_MODEL` | `cross-encoder/ms-marco-MiniLM-L6-v2` | Reranker model |
| `ENABLE_ENTITY_RESOLUTION` | `True` | spaCy NER entity index |
| `ENABLE_CITATION_VERIFICATION` | `True` | NLI verification + conflict detection |
| `NLI_MODEL` | `cross-encoder/nli-deberta-v3-small` | NLI model |
| `ENABLE_PROMPT_DECOMPOSITION` | `True` | Complex query decomposition |
| `ENABLE_GAP_ANALYSIS` | `True` | CRAG-style adaptive retrieval |
| `SEARCH_THRESHOLD` | `0.0` | Min cosine similarity for semantic search |
| `MAX_RESULTS` | `20` | Max search results (non-chat) |
| `FORCE_CACHE_REFRESH` | `False` | Bypass all caches on startup |

---

## Known Issues & Improvement Opportunities

### Issues

1. **`chat_summarization_threshold` unused** — declared in config but windowing uses `max_recent_messages + 2` as trigger
2. **`image_search_weight` unused** — images enter RRF as equal-weight signal, config value ignored
3. **Double reranking** — cross-encoder fires in `VibeSearch.search()` AND in `_merge_and_rerank()`, scoring some notes twice
4. **BM25 is note-level only** — no chunk-level keyword search for long notes
5. **Entity signal uses uniform score** — all entity-matched notes get 1.0 regardless of match quality
6. **Chunking params are code constants** — `SHORT_NOTE_THRESHOLD`, `MIN_CHUNK_LENGTH`, `MAX_CHUNK_LENGTH` require code changes to tune

### Potential Improvements

- **Hybrid chunk search**: add BM25 at chunk level for better keyword recall on long notes
- **Weighted entity signal**: score by number of matched entities or entity prominence
- **Configurable chunking**: expose chunk size params to `.env`
- **Model upgrade path**: BGE-M3 would unlock late chunking (item 10) + sparse vectors (item 3) + 8192 token window
- **Streaming gap analysis**: run gap analysis in parallel with initial LLM response, inject supplementary context mid-stream
- **Citation grounding**: highlight the specific passage in the source note that supports each citation
- **Multi-modal RAG**: use CLIP embeddings for image-based context retrieval in chat (currently only in search)
- **Evaluation framework**: automated relevance scoring on a test query set to measure pipeline changes
