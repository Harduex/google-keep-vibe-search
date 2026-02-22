# AGENTS.md

**MANDATORY**: Before starting any task, read `docs/main-agent-orchestrator.prompt.md` and follow its pipeline. The orchestrator is the entry point for all AI agent work in this project.

---

## Project Overview

Google Keep Vibe Search is a Knowledge Operating System built on top of Google Keep note exports. It provides:

- Meaning-based semantic search via `sentence-transformers` (`all-MiniLM-L6-v2`)
- Hybrid RAG chat with intent-aware routing (LanceDB, GraphRAG, RAPTOR)
- Strict source-grounded citations (`[citation:id]`) with a side-by-side document viewer
- Docling semantic chunking with character offsets for exact passage highlighting
- Conversation sessions, note clustering, CLIP image search, and tag management

---

## Architecture

### Backend (`app/`)

- **Framework**: FastAPI + Python 3.9+
- **Configuration**: Pydantic `BaseSettings` in `app/core/config.py` (all values come from `.env`)
- **Service layer**: all business logic in `app/services/`. Routes only handle HTTP concerns.
- **LLM integration**: LlamaIndex wrapping `all-MiniLM-L6-v2` (embeddings) and an OpenAI-compatible endpoint (LLM generation). Default: Ollama.
- **Vector store**: LanceDB with two tables — `notes` (full-note embeddings) and `chunks` (chunk embeddings, 384-dim).
- **Streaming**: NDJSON over HTTP streaming. See [Streaming Protocol](#streaming-protocol) below.

### Frontend (`client/`)

- **Framework**: React 19 + TypeScript + Vite 6
- **Styling**: Tailwind CSS v4 + custom CSS variables in `client/src/components/Chat/styles.css` (light/dark theme)
- **State**: custom hooks pattern — each feature domain (`useChat`, `useSearch`, `useTags`, …) owns its own state and API calls
- **Citation UI**: parses `[citation:id]` markers inline, renders superscript chips, opens a side-panel `DocumentViewer` with CSS Custom Highlight API (Chrome) / `<mark>` fallback (Firefox)

---

## Directory Structure

```
app/                            # FastAPI backend
  core/
    config.py                   # All env vars (Pydantic BaseSettings)
    lifespan.py                 # Startup/shutdown: wires all services onto app.state
    dependencies.py             # FastAPI Depends() getters for each service
    exceptions.py               # Custom HTTP exception handlers
  models/
    chat.py                     # ChatMessage, ChatRequest, ChatResponse, ChatSession
    chunk.py                    # DoclingNoteChunk (with start_char_idx / end_char_idx)
    retrieval.py                # GroundedContext, GroundedCitation, RetrievalResult
  services/
    note_service.py             # Load notes from Google Takeout, tag CRUD, cache check
    cache_service.py            # Read/write embeddings + notes cache (.npz / JSON)
    search_service.py           # Thin wrapper around VibeSearch
    chat_service.py             # Streaming chat: RouterAgent → LLM → NDJSON protocol
    session_service.py          # Chat session persistence (JSON files in cache/)
    citation_service.py         # Extract [citation:id] or legacy [Note #N] from LLM text
    chunking_service.py         # Legacy paragraph chunker (fallback, no offsets)
    docling_adapter.py          # Google Keep JSON dict → DoclingDocument
    docling_chunking_service.py # Docling HierarchicalChunker; preserves heading trail + offsets
    llama_index_service.py      # LlamaIndex Settings: HuggingFaceEmbedding + OpenAILike LLM
    lancedb_service.py          # LanceDB: initialize tables, upsert, search_notes, search_chunks
    graph_service.py            # GraphRAG: PropertyGraphIndex (opt-in, ENABLE_GRAPHRAG=true)
    raptor_service.py           # RAPTOR hierarchical summaries (opt-in, ENABLE_RAPTOR=true)
    router_agent.py             # Intent classification (FACTUAL/RELATIONAL/SUMMARY/MIXED) + dispatch
  routes/                       # One file per route group (search, chat, notes, tags, …)
  prompts/
    system_prompts.py           # Legacy LLM prompts ([Note #N] format)
    grounded_prompts.py         # Strict grounded prompt (requires [citation:id], no fabrication)
  search.py                     # VibeSearch: cosine similarity engine, delegates to LanceDB
  parser.py                     # Google Keep JSON → Note objects
  image_processor.py            # CLIP image embeddings (optional)

client/
  src/
    components/
      Chat/
        index.tsx               # Main chat layout; wires document viewer
        ChatMessage.tsx         # Renders assistant text with inline CitationInline chips
        ChatNotes.tsx           # Context sidebar: grounded sources grouped by note
        CitationInline.tsx      # Superscript citation chip + hover tooltip
        DocumentViewer.tsx      # Full-note side panel with highlighted cited passage
        SessionList.tsx         # Session history sidebar
        styles.css              # All Chat component styles (light/dark, responsive)
      AllNotes/                 # Browse all notes
      Visualization/            # 3-D cluster + embeddings views
      ImageGallery/             # Image search results
      NoteCard/                 # Single note card with tag chips
      TagFilter/ TagManager/ TagDialog/
    hooks/
      useChat.ts                # Chat state, NDJSON stream parsing, document viewer callbacks
      useSearch.ts              # Semantic + keyword search
      useTags.ts                # Tag fetch + exclude management
      useAllNotes.ts            # Full note list
      useEmbeddings.ts          # 3-D PCA projection fetch
      useClusters.ts            # K-means cluster fetch
      useStats.ts               # System stats
      useTheme.ts               # Dark/light mode
      useError.ts               # Global error state
    utils/
      citationParser.ts         # Parse [citation:id] → ParsedContent (segments + citations)
      levenshteinMatcher.ts     # Sliding-window Levenshtein for approx highlight fallback
      highlightApi.ts           # CSS Custom Highlight API wrapper + <mark> fallback
    types/
      index.ts                  # All shared TS types (Note, GroundedContext, GroundedCitation, …)

scripts/
  dev.ps1 / dev.sh              # Start backend + frontend concurrently
  setup.ps1 / setup.sh          # One-time: venv, npm install, copy .env.example
  migrate_to_lancedb.py         # One-time: .npz cache → LanceDB tables

tests/                          # pytest backend tests (203 total)
  conftest.py
  test_parser.py
  test_citation_service.py
  test_session_service.py
  test_chunking_service.py
  test_docling_adapter.py
  test_docling_chunking_service.py
  test_llama_index_service.py
  test_lancedb_service.py
  test_graph_service.py
  test_raptor_service.py
  test_router_agent.py
  test_grounded_citation_service.py

docs/                           # Agent knowledge base (read-only reference)
  main-agent-orchestrator.prompt.md
  agents/                       # Specialised agent roles
  skills/                       # Rules and skill definitions
  memory/                       # Long-term learned lessons

.ai-workspace/                  # Ephemeral (gitignored)
  prd.md                        # Current feature requirements
  tasks.md                      # Step-by-step task breakdown
  progress.md                   # Pause/resume log
```

---

## Configuration Variables

All values loaded from `.env` (copy from `.env.example`).

### Core
| Variable | Default | Description |
|---|---|---|
| `GOOGLE_KEEP_PATH` | *(required)* | Path to Google Takeout Keep export folder |
| `HOST` | `127.0.0.1` | Backend bind address |
| `PORT` | `8000` | Backend port |
| `CACHE_DIR` | `./cache/` | Root cache directory (embeddings, LanceDB, sessions) |

### Search
| Variable | Default | Description |
|---|---|---|
| `MAX_RESULTS` | `300` | Max search results returned |
| `SEARCH_THRESHOLD` | `0.3` | Min cosine similarity (0–1) |
| `DEFAULT_NUM_CLUSTERS` | `20` | K-means cluster count |

### LLM / Chat
| Variable | Default | Description |
|---|---|---|
| `LLM_API_BASE_URL` | *(empty)* | OpenAI-compatible base URL; if empty, derived from `OLLAMA_API_URL` |
| `LLM_API_KEY` | *(empty)* | API key (empty for local providers) |
| `LLM_MODEL` | `llama3` | Model name |
| `OLLAMA_API_URL` | `http://localhost:11434` | Fallback Ollama URL |
| `CHAT_CONTEXT_NOTES` | `10` | Context chunks injected per message |
| `CHAT_MAX_RECENT_MESSAGES` | `6` | Recent messages kept verbatim in context window |
| `CHAT_SUMMARIZATION_THRESHOLD` | `12` | Message count before history summarisation |

### Retrieval Backends
| Variable | Default | Description |
|---|---|---|
| `CHUNKING_STRATEGY` | `docling` | `docling` (semantic, with char offsets) or `legacy` (paragraph split) |
| `LANCEDB_PATH` | `{CACHE_DIR}/lancedb` | LanceDB storage dir |
| `ENABLE_GRAPHRAG` | `false` | GraphRAG (requires LLM indexing, slow) |
| `GRAPH_PERSIST_DIR` | `{CACHE_DIR}/graph` | Graph store persistence |
| `ENABLE_RAPTOR` | `false` | RAPTOR hierarchical summaries (requires LLM indexing, slow) |
| `RAPTOR_PERSIST_DIR` | `{CACHE_DIR}/raptor` | RAPTOR tree persistence |

### Image Search (optional)
| Variable | Default | Description |
|---|---|---|
| `ENABLE_IMAGE_SEARCH` | `true` | CLIP image search (downloads ~350 MB model on first run) |
| `IMAGE_SEARCH_THRESHOLD` | `0.2` | Min image similarity score |
| `IMAGE_SEARCH_WEIGHT` | `0.3` | Image weight in combined text+image score |

---

## Service Wiring (Lifespan)

`app/core/lifespan.py` starts up in four stages:

1. **Notes + Search** — Parse Google Keep notes (or load from cache) → `VibeSearch` → `SearchService`
2. **Chunking** — Branch on `CHUNKING_STRATEGY`: `DoclingChunkingService` or legacy `ChunkingService`
3. **LlamaIndex + Vector DB** — `LlamaIndexService` (embed model + LLM) → `LanceDBService` → optionally `GraphRAGService` + `RAPTORService` (gracefully skip if disabled or unavailable)
4. **Chat** — `RouterAgent` → `ChatService(search, chunking, graph, raptor, lancedb)` → `SessionService`

All services are stored on `app.state`. `app/core/dependencies.py` exposes them as `Depends()` getters.

---

## Streaming Protocol

`ChatService.stream_chat_with_protocol()` emits newline-delimited JSON:

```
{"type": "context", "items": [...GroundedContext], "intent": "factual", "session_id": "..."}
{"type": "delta",   "content": "partial token text"}
{"type": "delta",   "content": "more text"}
{"type": "done",    "citations": [...GroundedCitation], "full_response": "..."}
{"type": "error",   "error": "message"}   # only on failure
```

**GroundedContext** fields: `citation_id`, `note_id`, `note_title`, `text`, `start_char_idx`, `end_char_idx`, `relevance_score`, `source_type`, `heading_trail[]`

**GroundedCitation** fields: `citation_id`, `note_id`, `note_title`, `start_char_idx`, `end_char_idx`, `text_snippet`

The frontend (`useChat.ts`) parses `context` to populate the context sidebar and document viewer state; `done` to attach deduplicated citations to the completed message.

---

## Citation Flow

```
LLM response text
 "The budget was approved [citation:note1.json_c0]."
        │
        ▼
citationParser.ts      → ParsedContent { segments[], citations[], cleanText }
        │
        ▼
ChatMessage.tsx        → renders CitationInline chip after "approved"
        │ click
        ▼
useChat openDocumentViewer(citationId)
        │
        ▼
DocumentViewer.tsx
  ├── primary:   start_char_idx / end_char_idx → CSS Custom Highlight API (Chrome 105+)
  └── fallback:  levenshteinMatcher.findBestMatch() → <mark> injection (Firefox)
```

Backward compat: responses with `[Note #N]` markers are handled by the legacy path in `citation_service.py` and `ChatMessage.tsx`.

---

## Key API Routes

| Method | Path | Description |
|--------|------|-------------|
| POST   | `/api/chat` | Streaming chat (NDJSON) or non-streaming |
| GET    | `/api/chat/model` | Configured model name |
| GET/POST | `/api/chat/sessions` | List / create sessions |
| GET/PATCH/DELETE | `/api/chat/sessions/{id}` | Load, rename, delete session |
| POST   | `/api/chat/sessions/{id}/messages` | Persist messages |
| GET/POST | `/api/search` | Semantic text search |
| POST   | `/api/search/image` | CLIP image search |
| GET    | `/api/all-notes` | Full note list |
| GET/POST | `/api/tags/excluded` | Get / set excluded tags |
| GET    | `/api/embeddings` | 3-D PCA projections |
| GET    | `/api/clusters` | K-means clusters |
| GET    | `/api/stats` | System stats |

---

## Running the Project

```bash
# Backend only
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# Frontend only
cd client && npm run dev

# Both (Windows)
.\scripts\dev.ps1

# Both (Linux/macOS)
bash scripts/dev.sh

# Backend tests (203 tests)
venv\Scripts\pytest          # Windows
venv/bin/pytest              # Linux/macOS

# Frontend tests (52 tests)
cd client && npm test

# TypeScript type-check
cd client && npx tsc --noEmit
```

---

## AI Agent Rules

1. **Read the orchestrator first**: `docs/main-agent-orchestrator.prompt.md` is mandatory before any task.

2. **Lazy-load context**: Pull specialist docs only when relevant — `docs/agents/product-designer.prompt.md` for UI, `docs/agents/bug-hunter.prompt.md` for bugs, `docs/skills/zero-assumptions.prompt.md` for architecture.

3. **Read before you write**: Never modify a file you haven't read in the current session. Use `Read` or the `Explore` agent to understand existing code before proposing changes.

4. **Follow existing patterns**:
   - Business logic → `app/services/`
   - HTTP concerns → `app/routes/`
   - Validation → Pydantic models in `app/models/`
   - Frontend state + API calls → custom hooks in `client/src/hooks/`
   - Shared TS types → `client/src/types/index.ts`
   - Styles → `client/src/components/Chat/styles.css` (follow existing class naming conventions)

5. **No refactoring without permission**: Identify and propose opportunities; do not act without explicit approval.

6. **Production-ready code only**: No placeholder comments, no `# TODO`, no "added in v2" annotations, no change-marker comments.

7. **Use the workspace**: Write plans to `.ai-workspace/prd.md`, track tasks in `.ai-workspace/tasks.md`, log progress in `.ai-workspace/progress.md`.

8. **Optional services degrade gracefully**: GraphRAG and RAPTOR are opt-in. Code that depends on them must check availability before use (use `getattr(app.state, "service", None)` pattern).

9. **Backward compatibility**: The legacy `[Note #N]` citation format must continue to work as a fallback throughout the stack (citation_service.py, ChatMessage.tsx).

10. **Test every change**: Run `pytest tests/` for backend changes and `npx vitest run` + `npx tsc --noEmit` for frontend changes before considering a task done.

---

## After Every Implementation — MANDATORY

At the end of every implementation task (feature, fix, or refactor) **you must**:

### 1. Update `README.md`

- **Features section**: add or update bullet points for any new user-visible capability.
- **Configuration section**: add rows for any new `.env` variables. Keep the grouped structure (Core / LLM & Chat / Retrieval Backends / Image Search).
- **Project structure tree**: add or update file entries. Every new `app/services/*.py`, `client/src/utils/*.ts`, test file, or script must appear.
- **Running tests section**: update test counts if they changed.
- **How it works section**: update the relevant sub-section if the pipeline changed.
- **Troubleshooting section**: add entries for any new failure modes introduced.
- **Migration section**: add instructions if users with existing caches need to take action.

### 2. Update `AGENTS.md`

- **Architecture overview**: update bullet points if a new layer or technology was introduced.
- **Directory structure**: add every new file with a one-line description.
- **Configuration Variables**: add rows for any new config knobs.
- **Service Wiring (Lifespan)**: update the numbered stages if startup order or wiring changed.
- **Streaming Protocol**: update if the NDJSON event schema changed.
- **Key API Routes**: add rows for new endpoints.
- **AI Agent Rules**: add a rule if a new cross-cutting constraint was established.

### Checklist

Before marking a task complete, verify:

- [ ] `README.md` features, config table, project structure, and "how it works" sections are accurate.
- [ ] `AGENTS.md` directory structure, config table, and service wiring are accurate.
- [ ] `pytest tests/` passes (all backend tests green).
- [ ] `npx vitest run` passes (all frontend tests green).
- [ ] `npx tsc --noEmit` reports no TypeScript errors.
