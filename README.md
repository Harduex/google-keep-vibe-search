# Google Keep Vibe Search

A semantic search and AI chat assistant for your Google Keep notes export — rebuilt as a Knowledge Operating System with hybrid retrieval, agentic routing, and source-grounded citations.

## Features

- **Semantic Search** — Find notes by meaning, not keyword. Powered by `sentence-transformers` (`all-MiniLM-L6-v2`).
- **Hybrid RAG** — Queries are routed to the right retrieval backend: LanceDB (dense vector), GraphRAG (entity relationships), or RAPTOR (hierarchical summaries).
- **Agentic Router** — Classifies each query as `FACTUAL`, `RELATIONAL`, `SUMMARY`, or `MIXED` and dispatches accordingly. Falls back gracefully when optional backends are disabled.
- **Grounded Citations** — Answers cite sources as `[citation:id]` inline. The system refuses to answer from memory — if the notes don't contain an answer, it says so.
- **Document Viewer** — Click any citation to open the full note in a side panel with the cited passage highlighted. Uses the [CSS Custom Highlight API](https://developer.mozilla.org/en-US/docs/Web/API/CSS_Custom_Highlight_API) (Chrome 105+) with `<mark>` fallback for Firefox.
- **Docling Chunking** — Long notes are chunked with Docling's `HierarchicalChunker`, injecting character offsets into every chunk so citations highlight exact passages.
- **Chat Sessions** — Conversations persist across reloads. Create, rename, and delete sessions from the sidebar.
- **Image Search** — Find notes by image content using OpenAI CLIP embeddings (optional).
- **Tag Management** — Assign tags to notes, exclude tags from search results.
- **Clustering & 3D Visualization** — Group notes into semantic clusters and explore them in an interactive 3D scatter plot.
- **Any OpenAI-Compatible LLM** — Works with Ollama, LM Studio, OpenAI, Anthropic (via proxy), or any `/v1/chat/completions` endpoint.

---

## Quick Start

### Prerequisites

- Python 3.9+
- Node.js 18+
- A [Google Takeout](https://takeout.google.com/) export with Keep selected
- An LLM endpoint (Ollama recommended for local use)

### 1. Export your Google Keep notes

1. Go to [Google Takeout](https://takeout.google.com/)
2. Select only **Keep**
3. Download and extract the ZIP file

### 2. Run the setup script

**Linux / macOS:**
```bash
bash scripts/setup.sh
```

**Windows (PowerShell):**
```powershell
.\scripts\setup.ps1
```

This creates a Python virtual environment, installs all dependencies, installs frontend packages, and copies `.env.example` → `.env` on first run.

### 3. Edit `.env`

Open `.env` and set at minimum:

```env
GOOGLE_KEEP_PATH=/home/user/Takeout/Keep   # or C:\Users\user\Takeout\Keep on Windows
LLM_MODEL=llama3                            # model name available in your LLM provider
```

See [Configuration](#configuration) for all options.

### 4. Start the development servers

**Linux / macOS:**
```bash
bash scripts/dev.sh
```

**Windows (PowerShell):**
```powershell
.\scripts\dev.ps1
```

| Service  | URL                       |
|----------|---------------------------|
| Frontend | http://localhost:5173      |
| Backend  | http://localhost:8000      |
| API docs | http://localhost:8000/docs |

---

## LLM Providers

Set `LLM_API_BASE_URL` and `LLM_MODEL` in your `.env` to point at any OpenAI-compatible endpoint.

| Provider     | `LLM_API_BASE_URL`                  | `LLM_API_KEY`       |
|--------------|-------------------------------------|---------------------|
| Ollama (default) | *(leave empty, uses `OLLAMA_API_URL`/v1)* | *(empty)*       |
| LM Studio    | `http://localhost:1234/v1`          | *(empty)*           |
| OpenAI       | `https://api.openai.com/v1`         | your OpenAI key     |
| Anthropic proxy | your proxy URL                   | your key            |

---

## Configuration

All settings are read from `.env`. Copy `.env.example` to get started.

### Core

| Variable | Default | Description |
|---|---|---|
| `GOOGLE_KEEP_PATH` | *(required)* | Path to your Google Keep export folder |
| `MAX_RESULTS` | `300` | Maximum search results returned |
| `SEARCH_THRESHOLD` | `0.3` | Minimum similarity score (0.0–1.0). Lower = more results |
| `DEFAULT_NUM_CLUSTERS` | `20` | Number of clusters for the Clusters tab |
| `HOST` | `127.0.0.1` | Backend bind address |
| `PORT` | `8000` | Backend port |
| `CACHE_DIR` | `./cache/` | Directory for embeddings, LanceDB, and session cache |

### LLM / Chat

| Variable | Default | Description |
|---|---|---|
| `LLM_API_BASE_URL` | *(empty)* | OpenAI-compatible API base URL. If empty, derived from `OLLAMA_API_URL` |
| `LLM_API_KEY` | *(empty)* | API key (leave empty for local providers) |
| `LLM_MODEL` | `llama3` | Model name to use for chat |
| `OLLAMA_API_URL` | `http://localhost:11434` | Ollama server URL (fallback if `LLM_API_BASE_URL` is empty) |
| `CHAT_CONTEXT_NOTES` | `10` | Number of context chunks injected per chat message |
| `CHAT_MAX_RECENT_MESSAGES` | `6` | Number of recent messages kept verbatim in context window |
| `CHAT_SUMMARIZATION_THRESHOLD` | `12` | Total messages before older ones are summarized |

### Retrieval Backends

| Variable | Default | Description |
|---|---|---|
| `CHUNKING_STRATEGY` | `docling` | Chunking engine: `docling` (semantic, with char offsets) or `legacy` (paragraph split) |
| `LANCEDB_PATH` | `{CACHE_DIR}/lancedb` | LanceDB storage directory |
| `ENABLE_GRAPHRAG` | `false` | Enable GraphRAG index (entity/relation extraction via LLM — slow to build) |
| `GRAPH_PERSIST_DIR` | `{CACHE_DIR}/graph` | Directory for persisted graph store |
| `ENABLE_RAPTOR` | `false` | Enable RAPTOR index (LLM-summarized cluster hierarchy — slow to build) |
| `RAPTOR_PERSIST_DIR` | `{CACHE_DIR}/raptor` | Directory for persisted RAPTOR tree |

### Image Search

| Variable | Default | Description |
|---|---|---|
| `ENABLE_IMAGE_SEARCH` | `true` | Enable CLIP-based image search (downloads ~350 MB model on first run) |
| `IMAGE_SEARCH_THRESHOLD` | `0.2` | Minimum image similarity score |
| `IMAGE_SEARCH_WEIGHT` | `0.3` | Weight of image score vs. text score in combined results |

---

## Docker

```bash
cp .env.example .env
# Edit .env: set GOOGLE_KEEP_PATH and LLM settings
docker compose up -d
```

Access the app at http://localhost (port 80 → frontend, port 8000 → backend API).

**Ollama networking in Docker:**

| Setup | `OLLAMA_API_URL` |
|---|---|
| Native Ollama + Docker Desktop | `http://host.docker.internal:11434` |
| Native Ollama + Linux Docker | `http://172.17.0.1:11434` |
| Ollama in same Compose stack | `http://ollama:11434` |

---

## Development

### Project structure

```
app/                          # FastAPI backend
  core/
    config.py                 # Pydantic BaseSettings (all env vars)
    lifespan.py               # App startup: initialises all services
    dependencies.py           # FastAPI Depends() injection
    exceptions.py             # Custom exception handlers
  models/
    chunk.py                  # DoclingNoteChunk with char offsets
    retrieval.py              # GroundedContext, GroundedCitation
  services/
    note_service.py           # Note loading, tag CRUD
    cache_service.py          # Embedding and note cache I/O
    search_service.py         # Wraps VibeSearch
    chat_service.py           # Streaming chat with RouterAgent + grounding
    session_service.py        # Chat session persistence (JSON files)
    citation_service.py       # Parse [citation:id] / [Note #N] citations
    docling_adapter.py        # Google Keep JSON → DoclingDocument
    docling_chunking_service.py  # Docling HierarchicalChunker with offsets
    chunking_service.py       # Legacy paragraph chunker (fallback)
    llama_index_service.py    # LlamaIndex Settings (embeddings + LLM)
    lancedb_service.py        # LanceDB: notes + chunks tables
    graph_service.py          # GraphRAG: PropertyGraphIndex (opt-in)
    raptor_service.py         # RAPTOR: hierarchical summary tree (opt-in)
    router_agent.py           # Query intent classification + dispatch
  routes/                     # One file per API route group
  prompts/
    system_prompts.py         # Legacy system prompt templates
    grounded_prompts.py       # Strict citation-grounded system prompt
  search.py                   # VibeSearch: embedding + scoring
  parser.py                   # Google Keep JSON → Note objects
  image_processor.py          # CLIP image embeddings

client/                       # React + TypeScript frontend (Vite)
  src/
    components/
      Chat/
        index.tsx             # Main chat layout with document viewer
        ChatMessage.tsx       # Renders inline [citation:id] chips
        ChatNotes.tsx         # Context sidebar with grounded sources
        CitationInline.tsx    # Superscript citation chip + tooltip
        DocumentViewer.tsx    # Full-note side panel with highlight
    hooks/
      useChat.ts              # Chat state, streaming, document viewer
    utils/
      citationParser.ts       # Parse [citation:id] markers → segments
      levenshteinMatcher.ts   # Sliding-window approx text matching
      highlightApi.ts         # CSS Custom Highlight API + mark fallback
    types/index.ts            # GroundedContext, GroundedCitation, etc.

scripts/
  migrate_to_lancedb.py       # One-time: migrate .npz cache → LanceDB

tests/                        # pytest backend tests (203 tests)
  test_docling_adapter.py
  test_docling_chunking_service.py
  test_lancedb_service.py
  test_llama_index_service.py
  test_graph_service.py
  test_raptor_service.py
  test_router_agent.py
  test_grounded_citation_service.py
  test_citation_service.py
  test_session_service.py
  test_chunking_service.py
  test_parser.py
```

### Running tests

**Backend (203 tests):**
```bash
venv/bin/pytest          # Linux/macOS
venv\Scripts\pytest      # Windows
```

**Frontend (52 tests):**
```bash
cd client
npm test
```

### Code formatting

```bash
# Python
venv/bin/black app/
venv/bin/isort app/

# TypeScript
cd client && npm run format
```

---

## How it works

### 1. Startup

Notes are parsed from Google Keep JSON files. Depending on `CHUNKING_STRATEGY`:

- **`docling`** (default): Notes are converted to `DoclingDocument` objects and chunked with `HierarchicalChunker`. Each chunk carries `start_char_idx` / `end_char_idx` offsets into the original note text.
- **`legacy`**: Notes are split into paragraph-level chunks without offset tracking.

Chunks are embedded with `all-MiniLM-L6-v2` and stored in LanceDB (`chunks` table). Full-note embeddings go into the `notes` table. Everything is cached; subsequent starts skip re-embedding unchanged notes.

If `ENABLE_GRAPHRAG=true` or `ENABLE_RAPTOR=true`, those indexes are loaded from their persist directories (build them separately with the indexing scripts before first use).

### 2. Semantic search

Your query is embedded with the same model. Cosine similarity ranks notes against the LanceDB `notes` table. An optional keyword overlap score is blended in for better precision on exact matches.

### 3. Image search

If enabled, attached images are embedded with OpenAI CLIP. Image similarity scores are merged with text scores using `IMAGE_SEARCH_WEIGHT`.

### 4. Chat / RAG

On each message the pipeline is:

1. **Router Agent** classifies intent:
   - `FACTUAL` → dense retrieval from LanceDB `chunks` table
   - `RELATIONAL` → GraphRAG entity/relation traversal (if enabled, else LanceDB fallback)
   - `SUMMARY` → RAPTOR summary tree query (if enabled, else LanceDB fallback)
   - `MIXED` → LanceDB + any available optional backend

2. **Retrieval** returns `GroundedContext` objects — each with `note_id`, `citation_id`, `text`, `start_char_idx`, `end_char_idx`, `relevance_score`, and `source_type`.

3. **LLM** is called with a strict grounded system prompt that requires `[citation:id]` inline markers after every claim and mandates "I don't have enough information" when context is absent.

4. **Streaming** emits NDJSON events:
   - `context` — `GroundedContext[]` + detected intent, shown in the context sidebar
   - `delta` — token-by-token content
   - `done` — `GroundedCitation[]` (deduplicated, with text snippets)

### 5. Citation UI

The frontend parses `[citation:id]` markers from the streamed response and renders each as a superscript chip. Clicking a chip opens the **Document Viewer** side panel:

- **Primary**: uses `start_char_idx` / `end_char_idx` for exact character-offset highlighting via the CSS Custom Highlight API (Chrome) or `<mark>` injection (Firefox).
- **Fallback**: if offsets are unavailable, a sliding-window Levenshtein matcher finds the best approximate match in the note text (threshold ≤ 0.3 normalised distance).

### 6. Sessions

Chat histories are persisted as JSON in `./cache/chat_sessions/`. The session sidebar lets you switch, rename, and delete conversations.

---

## Migrating from the previous version

If you have an existing `.npz` embeddings cache and want to keep it, run the migration script once after startup:

```bash
python scripts/migrate_to_lancedb.py
```

The old numpy cache is not deleted; you can switch back with `CHUNKING_STRATEGY=legacy` at any time.

---

## Troubleshooting

**No notes loaded** — Check `GOOGLE_KEEP_PATH` points to the folder that contains `.json` files (not the parent Takeout folder).

**Slow first start** — Embedding all notes takes a few minutes on first run. Building GraphRAG or RAPTOR indexes requires LLM calls and should be done as a separate step. Subsequent starts load from cache.

**Chat not responding** — Verify your LLM endpoint is reachable: `curl http://localhost:11434/v1/models` for Ollama. Check that `LLM_MODEL` matches an available model.

**Citations not highlighted** — Character-offset highlighting requires `CHUNKING_STRATEGY=docling` (default). If you migrated from `legacy`, re-index your notes by deleting the LanceDB cache and restarting.

**Image search disabled** — Set `ENABLE_IMAGE_SEARCH=true`. The CLIP model (~350 MB) downloads automatically on first use.

**GraphRAG / RAPTOR not routing** — These backends are opt-in and need to be indexed before the server starts. Set `ENABLE_GRAPHRAG=true` / `ENABLE_RAPTOR=true` and run the indexing scripts first.

---

## License

MIT License
