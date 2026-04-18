# Chat System Deep Research

*Created: 2026-04-18*

Comprehensive audit of the Google Keep Vibe Search chat system — backend services, frontend components, streaming protocol, RAG integration, and NotebookLM benchmark.

---

## Executive Summary

The chat system has a solid RAG pipeline with 9 advanced retrieval features (RRF fusion, BM25, cross-encoder reranking, entity resolution, NLI citation verification, conflict detection, query decomposition, gap analysis, retrieval stopping). However, the frontend streaming UX has performance issues (1000+ re-renders per response), citation interactivity is broken (click handler never wired), and several NotebookLM-tier features are missing (follow-up suggestions, source panel with evidence linking, progressive status indicators, conversation branching). The architecture needs refactoring for robustness, streaming efficiency, and modern conversational AI UX.

---

## 1. Backend Architecture

### 1.1 Request Lifecycle

```
[HTTP POST /api/chat] (app/routes/chat.py:14)
  |
  v
[chat_service.stream_chat_with_protocol()] (chat_service.py:361)
  |
  v
[get_conversation_aware_context()] (chat_service.py:148)
  |- query_service.decompose_if_complex()     -- prompt decomposition
  |- get_relevant_notes()                      -- primary retrieval (semantic+BM25+entity)
  |- context retrieval (conversation-aware)    -- with duplicate query detection
  |- topic retrieval (optional)
  |- chunking_service.search_chunks()          -- chunk-level search
  |- _merge_and_rerank()                       -- RRF fusion across all signals
  |   |- RRF with k=60 across 6 signals
  |   |- Continuity boost (1.15x for previously cited notes)
  |   |- Cross-encoder reranking (top-20 -> top-10)
  |- _cap_if_saturated()                       -- coverage saturation check
  |- query_service.retrieve_with_gap_analysis() -- CRAG-style gap filling
  |
  v
[prepare_messages_with_context()] (chat_service.py:92)
  |- format_notes_for_context()                -- "--- Note #1 ---" blocks
  |- verification_service.detect_conflicts()   -- NLI contradiction detection
  |- Inject conflict warnings into system prompt
  |- Inject gap analysis warning if "best_effort"
  |
  v
[STREAMING via NDJSON]
  |- {"type": "context", "notes": [...], "conflicts": [...]}
  |- {"type": "delta", "content": "..."}  (per LLM chunk)
  |- {"type": "done", "citations": [...], "full_response": "..."}
  |- {"type": "verification", "citations": [...]}  (NLI scores)
  |- {"type": "error", "error": "..."}
```

### 1.2 Service Dependency Graph

```
ChatService (orchestrator)
  +-- SearchService
  |     +-- VibeSearch (app/search.py)
  |     |     +-- SentenceTransformer (MiniLM-L12-v2, 384d)
  |     |     +-- BM25Okapi (keyword search)
  |     |     +-- ImageProcessor (CLIP ViT-B/32, optional)
  |     |     +-- RerankerService (ms-marco-MiniLM-L6-v2, optional)
  |     |     +-- EntityService (spaCy NER + Jaro-Winkler clustering, optional)
  |     
  +-- ChunkingService (chunk-level embeddings)
  +-- RerankerService (cross-encoder reranking)
  +-- EntityService (NER + alias clustering)
  +-- VerificationService (NLI citation verification + conflict detection)
  +-- QueryService (prompt decomposition + CRAG gap analysis)
  +-- httpx.AsyncClient (LLM API, OpenAI-compatible)
```

### 1.3 Key Service Methods

| Service | Method | Lines | Purpose |
|---------|--------|-------|---------|
| ChatService | `get_conversation_aware_context()` | 148-220 | Multi-signal retrieval orchestrator |
| ChatService | `_merge_and_rerank()` | 222-281 | RRF fusion + cross-encoder |
| ChatService | `_is_duplicate_query()` | 48-56 | Query collapse (threshold 0.95) |
| ChatService | `_cap_if_saturated()` | 58-72 | Coverage saturation (threshold 0.9, cap 5) |
| ChatService | `_maybe_summarize_window()` | 283-301 | Conversation windowing |
| ChatService | `stream_chat_with_protocol()` | 361-452 | Main streaming endpoint |
| QueryService | `decompose_if_complex()` | 31-67 | Break complex queries into 2-3 sub-queries |
| QueryService | `retrieve_with_gap_analysis()` | 69-123 | CRAG-style iterative gap filling (max 2) |
| VerificationService | `verify_citations()` | 29-95 | NLI entailment scoring per citation |
| VerificationService | `detect_conflicts()` | 130-187 | Contradiction detection between notes |
| RerankerService | `rerank()` | 18-29 | Cross-encoder precision reranking |
| EntityService | `get_entity_signal()` | 184-191 | RRF-compatible entity match signal |

### 1.4 Prompt Templates

| Prompt | Location | Purpose |
|--------|----------|---------|
| `NOTES_CHAT_SYSTEM_PROMPT` | `app/prompts/system_prompts.py:1-29` | Main system prompt with citation instructions |
| No-notes fallback | `system_prompts.py:31-32` | When no relevant notes found |
| `CONVERSATION_SUMMARY_PROMPT` | `system_prompts.py:35-44` | Summarize old messages (max 200 words) |
| `DECOMPOSE_PROMPT` | `query_service.py:15-17` | Break complex query into sub-queries |
| Gap analysis prompt | `query_service.py:82-87` | "SUFFICIENT" or "MISSING: <what>" |

### 1.5 Context Window Management

| Parameter | Value | Config Key |
|-----------|-------|------------|
| Max notes in context | 5 | `chat_context_notes` |
| Max recent messages before summarization | 12 | `chat_summarization_threshold` |
| Messages to keep after summarization | 6 | `chat_max_recent_messages` |
| Summary max tokens | 300 | Hardcoded |
| LLM read timeout | 120s | Hardcoded |

### 1.6 API Routes

| Route | Method | Handler | Purpose |
|-------|--------|---------|---------|
| `/api/chat` | POST | `chat()` | Main chat endpoint (streaming/non-streaming) |
| `/api/chat/model` | GET | `get_chat_model()` | Return LLM model name |
| `/api/chat/sessions` | GET | `list_sessions()` | List all sessions |
| `/api/chat/sessions` | POST | `create_session()` | Create new session |
| `/api/chat/sessions/{id}` | GET | `load_session()` | Load session with messages |
| `/api/chat/sessions/{id}` | DELETE | `delete_session()` | Delete session |
| `/api/chat/sessions/{id}` | PATCH | `rename_session()` | Rename session (query param: title) |
| `/api/chat/sessions/{id}/messages` | POST | `save_session_messages()` | Save messages + auto-title |

---

## 2. Frontend Architecture

### 2.1 Component Tree

```
App
  +-- ErrorBoundary
        +-- Chat (index.tsx, 255 lines)
              +-- SessionList (140 lines) -- left sidebar
              +-- ChatMessage[] (135 lines each) -- message list
              |     +-- ReactMarkdown (content rendering)
              |     +-- Thinking section (collapsible <think> tags)
              |     +-- Citation chips (with NLI verdict colors)
              +-- ChatNotes (67 lines) -- right sidebar
              |     +-- Conflict banner
              |     +-- NoteCard[]
              +-- Input form (textarea + send button)
              +-- Topic input (conditional)
              +-- Notes context toggle
```

### 2.2 State Management (useChat.ts, 414 lines)

```typescript
// Core state
messages: ChatMessage[]              // Full conversation
isLoading: boolean                   // Streaming in progress
error: string | null                 // Error message
relevantNotes: Note[]                // Context notes from last response
conflicts: ConflictInfo[]            // Detected contradictions
modelName: string | null             // LLM model name
useNotesContext: boolean             // Toggle notes retrieval
topic: string                        // Optional topic filter

// Session state
sessionId: string | null
sessions: ChatSessionSummary[]
abortControllerRef: useRef<AbortController>
```

### 2.3 Streaming Consumption

**Protocol**: NDJSON via `fetch` + `ReadableStream.getReader()`

```
fetch(POST /api/chat) -> ReadableStream -> TextDecoder -> line buffer -> JSON.parse
  -> switch(type):
       "context"      -> setRelevantNotes, setConflicts
       "delta"        -> accumulate content, setMessages (PER CHUNK)
       "done"         -> finalize with citations
       "verification" -> update citations with NLI verdicts
       "error"        -> setError
```

### 2.4 Message Rendering

- **Markdown**: `ReactMarkdown` library, no custom plugins
- **Thinking**: `<think>` tag extraction via regex, collapsible section with `aria-expanded`
- **Citations**: Colored chips (green=supported, red=contradicted, orange=neutral)
- **Code blocks**: Plain `<pre><code>` styling, no syntax highlighting, no copy button

### 2.5 Session Management

| Operation | Endpoint | Frontend Trigger |
|-----------|----------|-----------------|
| Create | POST /api/chat/sessions | Auto on first message |
| Load | GET /api/chat/sessions/{id} | Click session in sidebar |
| Delete | DELETE /api/chat/sessions/{id} | Delete button in sidebar |
| Rename | PATCH /api/chat/sessions/{id} | Double-click title |
| Save messages | POST /api/chat/sessions/{id}/messages | Auto after streaming (100ms delay) |
| Auto-title | Server-side via save endpoint | If title is "New Chat" |

---

## 3. Bugs & Issues Found

### 3.1 Critical

| # | Issue | Location | Impact |
|---|-------|----------|--------|
| 1 | **Citation click handler never wired** | Chat/index.tsx → ChatMessage | `onCitationClick` prop is optional and never passed. Users click citations and nothing happens. |
| 2 | **1000+ re-renders per response** | useChat.ts:293-299 | `setMessages()` called for EVERY delta chunk. A 500-token response triggers 500+ React state updates and re-renders. |
| 3 | **Duplicate conflict detection** | chat_service.py:110 & 377 | Conflicts computed twice per stream request — once in `prepare_messages_with_context()` and again in `stream_chat_with_protocol()`. |
| 4 | **NDJSON double newlines** | chat_service.py:390,429 | Each message ends with `.encode() + b"\n"` potentially adding extra newlines. Could break strict NDJSON parsers. |

### 3.2 Moderate

| # | Issue | Location | Impact |
|---|-------|----------|--------|
| 5 | **No streaming status indicator** | Chat/index.tsx | User sees nothing for 1-3s while notes are retrieved. No "Searching notes..." message. |
| 6 | **Gap analysis "best_effort" misleading** | query_service.py:120 | Warning appended even when information is sufficient after 1st attempt but gap search found no new notes. |
| 7 | **Citation regex doesn't validate bounds** | citation_service.py:6 | Can cite non-existent Note #99 if LLM hallucinates. No bounds check against context_notes length. |
| 8 | **Conversation summarization blocks streaming** | chat_service.py:293 | Synchronous LLM call delays stream start for long conversations. |
| 9 | **Message lookup by timestamp** | useChat.ts:293-299 | O(n) scan through messages array on every delta chunk. Should use index or ref. |
| 10 | **Stop button no feedback** | Chat/index.tsx | After clicking stop, message keeps updating briefly. No "Generation stopped" indicator. |

### 3.3 Minor

| # | Issue | Location |
|---|-------|----------|
| 11 | **Hardcoded RRF k=60** | search.py:200 |
| 12 | **No telemetry/metrics** | All services |
| 13 | **No per-chunk streaming timeout** | chat_service.py:399 |
| 14 | **Session auto-title invisible** | useChat.ts session save |
| 15 | **Textarea lacks `<label>`** | Chat/index.tsx |
| 16 | **Empty chat gives no example questions** | Chat/index.tsx:177-181 |
| 17 | **Sidebar toggle not persisted** | Chat/index.tsx |
| 18 | **Code blocks lack syntax highlighting** | ChatMessage.tsx |
| 19 | **Auto-scroll interrupts reading** | Chat/index.tsx:44-46 |
| 20 | **Session list not paginated** | SessionList.tsx |

---

## 4. RAG Pipeline Integration Analysis

### 4.1 Feature Integration Map

| Feature | Where in Chat Flow | Status | Notes |
|---------|-------------------|--------|-------|
| RRF Fusion | `_merge_and_rerank()` line 258 | Working | 6 signals fused with k=60 |
| BM25 Search | `VibeSearch.search()` via `get_relevant_notes()` | Working | Replaces substring matching |
| Cross-Encoder Reranking | `_merge_and_rerank()` line 279 | Working | Top-20 -> top-10 |
| Entity Resolution | `_merge_and_rerank()` as RRF signal | Working | spaCy NER + Jaro-Winkler |
| NLI Citation Verification | `stream_chat_with_protocol()` line 441 | Working | Post-stream verification |
| Conflict Detection | `prepare_messages_with_context()` line 110 | Working (duplicated) | Also at line 377 |
| Query Decomposition | `get_conversation_aware_context()` line 166 | Working | >10 words or complex markers |
| Gap Analysis (CRAG) | `get_conversation_aware_context()` line 216 | Working | Max 2 iterations |
| Retrieval Stopping | `_is_duplicate_query()` + `_cap_if_saturated()` | Working | Query collapse + saturation |

### 4.2 Latency Budget (Estimated per Request)

| Stage | Latency | Condition |
|-------|---------|-----------|
| Query decomposition | +1.0-1.5s | If complex query |
| Primary retrieval (semantic+BM25+entity) | ~200ms | Always |
| Context retrieval | ~200ms | If not duplicate |
| Chunk-level search | ~100ms | Always |
| RRF fusion + sort | ~5ms | Always |
| Cross-encoder reranking | ~50-80ms | If enabled |
| Gap analysis (per iteration) | +1.2-2.0s | If enabled, max 2x |
| Conflict detection (NLI) | ~100-500ms | Depends on note count |
| Conversation summarization | +1.0-2.0s | If history > threshold |
| **Total pre-LLM overhead** | **~0.5-7.5s** | Worst case with all features |

### 4.3 Bottleneck Analysis

1. **Gap analysis** is the biggest latency contributor (up to 4s for 2 iterations). Each iteration requires a full LLM call + search.
2. **Conflict detection** is O(n^2) on note pairs for similarity computation. With 10 notes, that's 45 NLI calls.
3. **Conversation summarization** blocks the stream start. Should be async/cached.
4. **Query decomposition** adds 1-1.5s for an LLM call that often returns the original query unchanged.

---

## 5. NotebookLM Feature Benchmark

### 5.1 Feature Comparison

| Feature | NotebookLM | Current App | Gap |
|---------|------------|-------------|-----|
| **Grounded citations** | Inline `[1]` links to exact source passages | `[Note #N]` with post-hoc NLI verification | Missing: exact passage linking |
| **Source panel** | Side panel showing source text with highlighted evidence | Note cards in sidebar, no evidence highlights | Missing: evidence highlighting |
| **Follow-up suggestions** | 3 suggested questions after each response | None | Missing entirely |
| **Multi-turn coherence** | Full context threading with topic tracking | Conversation windowing + summarization | Partial: summarization loses detail |
| **Streaming quality** | Progressive rendering with status indicators | Raw delta streaming, no status phases | Missing: retrieval/thinking/writing phases |
| **Source selection** | Choose which notebooks/sources to include | All notes searched, optional topic filter | Missing: source selection UI |
| **Audio overview** | AI-generated podcast-style audio summary | None | Out of scope |
| **Notebook guide** | Auto-generated overview of all sources | None | Nice-to-have |
| **Citation confidence** | Visual confidence indicators on each citation | NLI scores in tooltip only | Missing: prominent visual indicators |
| **Conversation management** | Multiple notebooks with separate conversations | Session list with CRUD | Comparable |
| **Error recovery** | Graceful degradation with partial results | Generic error messages | Missing: graceful degradation |
| **Thinking/reasoning display** | "Analyzing sources..." status | `<think>` tag parsing (if LLM supports) | Partial |
| **Export** | Copy, share, save as doc | None | Missing |
| **Inline source highlighting** | Click citation → highlights passage in source | Citation click does nothing (broken) | Missing (and broken) |
| **Query reformulation** | Internally reformulates vague queries | Prompt decomposition for complex queries | Partial |
| **Fact-check indicators** | Shows when claims can't be verified | NLI verdict (supported/contradicted/neutral) | Comparable |
| **Conversation branching** | Fork conversations from any point | Linear history only | Missing |

### 5.2 Priority Gap Analysis

**Must-Have for NotebookLM Parity:**
1. Fix citation click → scroll to source note with evidence highlight
2. Follow-up question suggestions (3 per response)
3. Streaming status phases (Searching → Analyzing → Writing)
4. Source panel with evidence linking (highlighted passages)
5. Prominent citation confidence indicators (not just tooltips)

**Should-Have:**
6. Source/note selection before chat (choose which notes to include)
7. Conversation export (copy/download)
8. Example questions on empty chat state
9. Graceful error recovery (partial results on timeout)
10. Smart auto-scroll (only if at bottom)

**Nice-to-Have:**
11. Conversation branching/forking
12. Notebook guide (auto-summary of all notes)
13. Code block syntax highlighting + copy
14. Keyboard shortcuts for chat actions

---

## 6. Architecture Issues for Refactoring

### 6.1 ChatService is a God Object

`chat_service.py` handles:
- Retrieval orchestration (5 different retrieval paths)
- RRF fusion and reranking
- Context formatting and prompt construction
- Conversation windowing and summarization
- LLM API communication
- Streaming protocol
- Citation extraction
- Verification orchestration

**Recommendation**: Split into:
- `RetrievalOrchestrator` — multi-signal retrieval + fusion + reranking
- `ContextBuilder` — format notes, inject conflicts/warnings, build messages
- `ConversationManager` — windowing, summarization, history
- `StreamingProtocol` — SSE/NDJSON encoding, message types
- `ChatService` — thin orchestrator calling the above

### 6.2 Streaming Protocol Limitations

Current protocol is one-directional NDJSON with 5 message types. Missing:
- **Progress phases**: No way to communicate "retrieving notes" vs "analyzing" vs "generating"
- **Partial results**: Can't send intermediate retrieval results while LLM generates
- **Cancellation acknowledgment**: Client sends abort but no server confirmation
- **Heartbeat**: No keepalive mechanism for long retrieval phases
- **Structured citations**: Citations only sent in `done` message, not inline during streaming

### 6.3 Frontend Performance

The biggest issue is **per-chunk state updates** during streaming:
```typescript
// Called 500+ times per response
setMessages((prev) => prev.map((msg) =>
  msg.timestamp === id ? { ...msg, content: accumulated } : msg
));
```

Each call triggers React reconciliation on the entire messages array. Fix options:
1. **Ref-based streaming**: Store streaming content in a ref, update state on `requestAnimationFrame`
2. **Separate streaming state**: Use a `streamingContent` state that only renders in the active message
3. **Virtualized message list**: Only render visible messages

### 6.4 Missing Observability

No structured logging, metrics, or tracing for:
- Retrieval quality (which signals contributed to final results)
- Latency breakdown per pipeline stage
- Citation accuracy rates
- Conflict detection frequency
- Gap analysis trigger rate and success rate

---

## 7. Contradictions & Uncertainties

1. **Conflict detection placement**: Code shows it running both in `prepare_messages_with_context()` and `stream_chat_with_protocol()`. Unclear if this is intentional (different note sets) or a bug.

2. **NLI label ordering**: `verify_citations()` uses `[0=contradiction, 1=entailment, 2=neutral]` (line 70). `detect_conflicts()` uses the same model. The `nli-deberta-v3-small` model's actual label order should be verified — different cross-encoder versions may differ.

3. **Gap analysis search function**: `retrieve_with_gap_analysis()` receives `search_fn` as parameter. The actual search function passed and its configuration (max results, thresholds) couldn't be fully traced without runtime testing.

4. **Entity service in chat**: Entity signal is added to RRF in `_merge_and_rerank()`, but the exact integration (whether entity service is always initialized or config-gated) depends on runtime configuration.

---

## 8. Sources

| # | Source | Type |
|---|--------|------|
| 1 | `app/services/chat_service.py` (452 lines) | Backend service |
| 2 | `app/services/query_service.py` (132 lines) | Query intelligence |
| 3 | `app/services/verification_service.py` (187 lines) | NLI verification |
| 4 | `app/services/reranker_service.py` (29 lines) | Cross-encoder |
| 5 | `app/services/entity_service.py` (191 lines) | Entity resolution |
| 6 | `app/services/chunking_service.py` (220 lines) | Chunk management |
| 7 | `app/search.py` (362 lines) | Core search engine |
| 8 | `app/routes/chat.py` (110 lines) | API routes |
| 9 | `app/core/lifespan.py` (111 lines) | Service initialization |
| 10 | `app/prompts/system_prompts.py` | Prompt templates |
| 11 | `app/models/chat.py` | Request/response schemas |
| 12 | `client/src/hooks/useChat.ts` (414 lines) | Frontend state management |
| 13 | `client/src/components/Chat/index.tsx` (255 lines) | Main chat component |
| 14 | `client/src/components/Chat/ChatMessage.tsx` (135 lines) | Message rendering |
| 15 | `client/src/components/Chat/ChatNotes.tsx` (67 lines) | Context notes panel |
| 16 | `client/src/components/Chat/SessionList.tsx` (140 lines) | Session management |
| 17 | `client/src/components/Chat/styles.css` (1242 lines) | Chat styling |
| 18 | `client/src/types/index.ts` | TypeScript types |
