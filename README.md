# Google Keep Vibe Search

A semantic search and AI chat assistant for your Google Keep notes export. Search by meaning, ask questions across your entire note collection, and surface connections you didn't know existed.

## Features

- **Semantic Search** — Find notes by meaning, not keyword. Powered by `sentence-transformers`.
- **AI Chat with Citations** — Ask questions about your notes; the LLM answers using retrieved context and cites sources as `[Note #N]`.
- **Chat Sessions** — Conversations persist across page reloads. Create, rename, and delete sessions from the sidebar.
- **Multi-Signal RAG** — Retrieval uses your latest message, recent context, and continuity boosting to handle follow-up questions naturally.
- **Note Chunking** — Long notes are split into chunks for higher-precision retrieval with large collections (2000+ notes).
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

| Variable | Default | Description |
|---|---|---|
| `GOOGLE_KEEP_PATH` | *(required)* | Path to your Google Keep export folder |
| `MAX_RESULTS` | `300` | Maximum search results returned |
| `SEARCH_THRESHOLD` | `0.3` | Minimum similarity score (0.0–1.0). Lower = more results |
| `DEFAULT_NUM_CLUSTERS` | `20` | Number of clusters for the Clusters tab |
| `HOST` | `127.0.0.1` | Backend bind address |
| `PORT` | `8000` | Backend port |
| `LLM_API_BASE_URL` | *(empty)* | OpenAI-compatible API base URL. If empty, derived from `OLLAMA_API_URL` |
| `LLM_API_KEY` | *(empty)* | API key (leave empty for local providers) |
| `LLM_MODEL` | `llama3` | Model name to use for chat |
| `CHAT_CONTEXT_NOTES` | `10` | Number of notes injected as context per chat message |
| `CHAT_MAX_RECENT_MESSAGES` | `6` | Number of recent messages kept verbatim in context window |
| `CHAT_SUMMARIZATION_THRESHOLD` | `12` | Total messages before older ones are summarized |
| `OLLAMA_API_URL` | `http://localhost:11434` | Ollama server URL (fallback if `LLM_API_BASE_URL` is empty) |
| `ENABLE_IMAGE_SEARCH` | `true` | Enable CLIP-based image search (downloads ~350 MB model on first run) |
| `IMAGE_SEARCH_THRESHOLD` | `0.2` | Minimum image similarity score |
| `IMAGE_SEARCH_WEIGHT` | `0.3` | Weight of image score vs. text score in combined results |
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

| Setup | `OLLAMA_API_URL` |
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
    lifespan.py         # App startup/shutdown
    dependencies.py     # FastAPI Depends() injection
    exceptions.py       # Custom exception handlers
  models/               # Pydantic request/response models
  services/
    note_service.py     # Note loading, tag CRUD
    cache_service.py    # Embedding and note cache I/O
    search_service.py   # Wraps VibeSearch
    chat_service.py     # LLM calls, streaming, RAG retrieval
    session_service.py  # Chat session persistence (JSON files)
    chunking_service.py # Note → chunks for high-precision retrieval
    citation_service.py # Parse [Note #N] citations from responses
  routes/               # One file per API route group
  prompts/
    system_prompts.py   # LLM system prompt templates
  search.py             # VibeSearch: embedding + scoring
  parser.py             # Google Keep JSON → Note objects
  image_processor.py    # CLIP image embeddings

client/                 # React + TypeScript frontend (Vite)
  src/
    components/
      Chat/             # Chat tab: sessions sidebar, messages, context panel
      NoteCard/         # Note display with tag chips and actions
      AllNotes/         # Browse all notes with filtering
      Clusters/         # Cluster view
      Results/          # Search results grid
    hooks/              # useSearch, useChat, useTags, ...

tests/                  # pytest backend tests
  conftest.py
  test_parser.py
  test_citation_service.py
  test_session_service.py
  test_chunking_service.py
```

### Running tests

**Backend:**
```bash
venv/bin/pytest          # Linux/macOS
venv\Scripts\pytest      # Windows
```

**Frontend:**
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

1. **Startup** — Notes are parsed from Google Keep JSON files, passed through `sentence-transformers` to produce embeddings, and cached to `./cache/`. Subsequent loads skip re-embedding unchanged notes.

2. **Semantic search** — Your query is embedded with the same model. Cosine similarity ranks notes. An optional keyword overlap score is blended in for better precision on exact matches.

3. **Image search** — If enabled, attached images are embedded with OpenAI CLIP. Image similarity scores are merged with text scores using `IMAGE_SEARCH_WEIGHT`.

4. **Chat / RAG** — On each message, the backend runs multi-signal retrieval (latest message + recent context + topic + chunk-level search + continuity boost), injects the top notes into a structured system prompt, and streams the LLM response token-by-token. The final `done` event includes parsed `[Note #N]` citations.

5. **Chunking** — Notes longer than 500 characters are split into paragraph-level chunks that are embedded independently, enabling higher-precision retrieval in large collections.

6. **Sessions** — Chat histories are persisted as JSON in `./cache/chat_sessions/`. The session sidebar lets you switch, rename, and delete conversations.

---

## Troubleshooting

**No notes loaded** — Check `GOOGLE_KEEP_PATH` points to the folder that contains `.json` files (not the parent Takeout folder).

**Slow first start** — Embedding all notes and (if enabled) images takes a few minutes on first run. Subsequent starts load from cache.

**Chat not responding** — Verify your LLM endpoint is reachable: `curl http://localhost:11434/v1/models` for Ollama. Check that `LLM_MODEL` matches an available model.

**Image search disabled** — Set `ENABLE_IMAGE_SEARCH=true`. The CLIP model (~350 MB) downloads automatically on first use.

---

## License

MIT License
