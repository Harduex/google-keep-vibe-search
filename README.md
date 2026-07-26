# Google Keep Vibe Search

A semantic search and AI chat assistant for your Google Keep notes export. Search by meaning, ask questions across your entire note collection, and surface connections you didn't know existed.

## Features

- **Semantic Search** — Find notes by meaning, not keyword. Powered by `sentence-transformers`.
- **AI Chat with Citations** — Ask questions about your notes; the LLM answers using retrieved context and cites sources as `[Note #N]`.
- **Chat Sessions** — Conversations persist across page reloads. Create, rename, and delete sessions from the sidebar.
- **Multi-Signal RAG** — Retrieval uses your latest message, recent context, and continuity boosting to handle follow-up questions naturally.
- **Note Chunking** — Long notes are split into chunks for higher-precision retrieval with large collections (2000+ notes).
- **Image Search** — Find notes by image content using OpenAI CLIP embeddings (optional).
- **Tag Management** — Assign tags to notes, rename tags inline, merge tags together, remove tags globally, and filter or exclude tags from search results.
- **AI-Powered Categorization** — Automatically discover and organize notes into meaningful categories using AI topic detection. Review, approve, rename, merge, or reject proposals before applying.
- **Tag Manager Dashboard** — Centralized tag management in the Organize tab. View all tags with note counts, rename, merge, or remove them.
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
make setup
```

**Windows (PowerShell):**
```powershell
.\scripts\setup.ps1
```

This creates a Python virtual environment via `uv`, installs all dependencies, installs frontend packages, copies `.env.example` → `.env` on first run, and installs the pre-commit git hooks.

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
make dev
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
| Ollama (default) | `http://localhost:11434`         | *(empty)*           |
| LM Studio    | `http://localhost:1234/v1`          | *(empty)*           |
| OpenAI       | `https://api.openai.com/v1`         | your OpenAI key     |
| Anthropic proxy | your proxy URL                   | your key            |

---

## Configuration

All settings are read from `.env`. Copy `.env.example` to get started.

| Variable | Default | Description |
|---|---|---|
| `GOOGLE_KEEP_PATH` | *(required)* | Path to your Google Keep export folder |
| `LLM_PROVIDER` | `ollama` | LLM provider (`ollama`, `openai`, `anthropic`, or any LiteLLM-supported) |
| `LLM_API_BASE_URL` | `http://localhost:11434` | OpenAI-compatible API base URL |
| `LLM_API_KEY` | *(empty)* | API key (leave empty for local providers) |
| `LLM_MODEL` | `ornith-1.0-9b` | Model name to use for chat |
| `MAX_RESULTS` | `300` | Maximum search results returned |
| `SEARCH_THRESHOLD` | `0.3` | Minimum similarity score (0.0–1.0). Lower = more results |
| `CHAT_CONTEXT_NOTES` | `10` | Number of notes injected as context per chat message |
| `CHAT_MAX_RECENT_MESSAGES` | `6` | Number of recent messages kept verbatim in context window |
| `CHAT_SUMMARIZATION_THRESHOLD` | `12` | Total messages before older ones are summarized |
| `ENABLE_IMAGE_SEARCH` | `true` | Enable CLIP-based image search (downloads ~350 MB model on first run) |
| `IMAGE_SEARCH_THRESHOLD` | `0.2` | Minimum image similarity score |

| `CACHE_DIR` | `./cache/` | Directory for embeddings and session cache |
| `FORCE_CACHE_REFRESH` | `false` | Set `true` to ignore cached notes/embeddings on startup |

---

## Docker

```bash
cp .env.example .env
# Edit .env: set GOOGLE_KEEP_PATH and LLM settings
docker compose up -d
```

Access the app at http://localhost (port 80 → frontend, port 8000 → backend API).

**Ollama networking in Docker:**

| Setup | `LLM_API_BASE_URL` |
|---|---|
| Native Ollama + Docker Desktop | `http://host.docker.internal:11434` |
| Native Ollama + Linux Docker | `http://172.17.0.1:11434` |
| Ollama in same Compose stack | `http://ollama:11434` |

---

## Development

### Project structure

```
app/                    # FastAPI backend
  core/
    config.py           # Pydantic BaseSettings (all env vars)
    lifespan.py         # App startup/shutdown — boots from the document store
    dependencies.py     # FastAPI Depends() injection
    exceptions.py       # Custom exception handlers
  domain/               # Content-addressed document model (SourceDoc, Document, ChangeSet)
  store/                # SQLite document store + mmapped vector store (keyed by content_hash)
    sqlite.py           #   documents, tags, imports history, per-index staleness ledger
    vectors.py          #   one .npy matrix per index kind, memory-mapped
  importers/            # Pluggable importers → SourceDoc (keep-takeout, markdown-dir)
  ingest.py             # The single writer: importer stream → ChangeSet (diff/upsert)
  models/               # Pydantic request/response models
  services/
    note_service.py     # Thin read/tag façade over the store
    search_service.py   # Wraps VibeSearch
    chat_service.py     # LLM calls, streaming, RAG retrieval
    session_service.py  # Chat session persistence (JSON files)
    chunking_service.py # Note → chunks for high-precision retrieval
    citation_service.py # Parse [Note #N] citations from responses
  routes/               # One file per API route group (incl. POST /api/imports)
  prompts/
    system_prompts.py   # LLM system prompt templates
  search.py             # VibeSearch: embedding + scoring (build / apply incremental)
  image_processor.py    # CLIP image embeddings

client/                 # React + TypeScript frontend (Vite)
  src/
    components/
      Chat/             # Chat tab: sessions sidebar, messages, context panel
      NoteCard/         # Note display with tag chips and actions
      AllNotes/         # Browse all notes with tag filtering and rename
      Organize/         # Smart Tags AI categorization and Tag Manager dashboard
      Clusters/         # Cluster view
      Results/          # Search results grid
      TagFilter/        # Tag inclusion filter with inline rename
      TagManager/       # Tag exclusion filter with removal
    hooks/              # useSearch, useChat, useTags, useOrganize, ...

tests/                  # pytest backend tests
  conftest.py           # Synthetic fixture corpus + isolated cache dir (autouse)
  test_store.py         # SQLite + vector store round-trips, idempotence, concurrency
  test_importers.py     # keep-takeout + markdown-dir importers
  test_ingest.py        # ingestion diff/upsert contract tests (A4, A5)
  test_search_cache.py  # VibeSearch.build / apply incremental indexing
```

The corpus is no longer "a folder of JSON files re-parsed on every change". It is a
durable SQLite document store (`cache/store.db`) plus a memory-mapped vector store
(`cache/vectors/`), populated once via an importer and updated incrementally —
editing one note re-embeds only that note, not the whole corpus. See
`docs/audit/ARCHITECTURE-PROPOSAL.md` §1–2 for the design.

### Running tests

**Unified Command (Linux / macOS):**
```bash
make test
```

**Backend (manual):**
```bash
uv run pytest
```

**Frontend (manual):**
```bash
cd client && npm test
```

### Code formatting

**Check only, non-mutating (also what CI runs):**
```bash
make check    # black --check, isort --check-only, eslint, tsc -b, pytest, vitest run
```
`make lint` is an alias of `make check` — it does **not** rewrite files.

**Rewrite files in place:**
```bash
make format   # black, isort, npm run fix (prettier --write + eslint --fix)
```

**Python (manual):**
```bash
uv run black app tests
uv run isort app tests
```

**TypeScript (manual):**
```bash
cd client && npm run fix
```

### Git hooks

`make setup` runs `pre-commit install` so the hooks in `.pre-commit-config.yaml` run on every commit.
To install them manually: `uv run pre-commit install`.

---

## How it works

1. **Ingestion & storage** — Notes are read once by a pluggable importer
   (`keep-takeout` for a Google Keep export, `markdown-dir` for an
   Obsidian-style folder) into content-addressed documents stored in a SQLite
   document store (`cache/store.db`), with dense vectors in a memory-mapped
   store (`cache/vectors/`) keyed by each note's content hash. A `POST /api/imports`
   call (or a first boot with a default source configured) runs the diff/upsert
   pipeline: only added or edited notes are embedded, so re-importing an
   unchanged export is a no-op and adding 12 notes to a 2,000-note store costs
   12 embeddings, not 2,012.

2. **Startup** — The app opens the document store and memory-maps the vectors,
   rather than re-parsing and re-embedding the export. Subsequent boots load in
   seconds; only a note whose content hash is absent from the vector store is
   ever encoded.

3. **Semantic search** — Your query is embedded with the same model. Cosine similarity ranks notes. An optional keyword overlap score is blended in for better precision on exact matches.

4. **Image search** — If enabled, attached images are embedded with OpenAI CLIP. Image similarity scores are merged with text scores via Reciprocal Rank Fusion.

5. **Chat / RAG & Agentic Mode** — On each message, the backend runs multi-signal retrieval (latest message + recent context + topic + chunk-level search + continuity boost), injects the top notes into a structured system prompt, and streams the LLM response token-by-token. An agentic loop uses PydanticAI to execute 1-3 query probes per step across 3 search tools (`search_notes`, `search_chunks`, `filter_by_tag`) with PydanticAI validation retries and pure-math deterministic stopping (coverage thresholds, novelty ratios, max steps). Agent loop thresholds and internal limits are configured in `app/services/agent/constants.py`. The final `done` event includes verified `[Note #N]` citations.

6. **Chunking** — Notes longer than 500 characters are split into paragraph-level chunks that are embedded independently, enabling higher-precision retrieval in large collections.

7. **Sessions** — Chat histories are persisted as JSON in `./cache/chat_sessions/`. The session sidebar lets you switch, rename, and delete conversations.

8. **Tag Management** — Tags can be managed from multiple locations:
   - **Search results** — The Tag Filters panel excludes tagged notes from results; individual tags can be removed from notes via badge buttons.
   - **All Notes** — The Tag Filter panel supports filtering by tag with inline rename.
   - **Note cards** — Each tag badge supports inline rename and removal.
   - **Organize tab** — The Tag Manager dashboard provides centralized rename, merge (combine two tags into one), and removal.
   - **AI Categorization** — Smart Tags uses UMAP + HDBSCAN clustering and LLM naming to propose categories. Proposals can be approved, renamed, merged, or rejected before applying.

---

## Troubleshooting

**No notes loaded** — The store is populated by an import. Either set `GOOGLE_KEEP_PATH` to the folder containing `.json` files (imported automatically on first boot), or run `POST /api/imports` against an importer (`keep-takeout` or `markdown-dir`).

**Slow first start** — The first import embeds every note (and, if enabled, every image), which takes a few minutes on a large corpus. Subsequent boots open the SQLite store and memory-map the vectors in seconds, and re-imports only embed notes whose content changed.

**Chat not responding** — Verify your LLM endpoint is reachable: `curl http://localhost:11434/v1/models` for Ollama. Check that `LLM_MODEL` matches an available model.

**Image search disabled** — Set `ENABLE_IMAGE_SEARCH=true`. The CLIP model (~350 MB) downloads automatically on first use.

---

## License

MIT License
