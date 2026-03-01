# Product Requirements Document (PRD)
# Google Keep Vibe Search

**Version:** 2.0
**Date:** March 2026
**Status:** Active Development

---

## 1. Executive Summary

### Product Overview

Google Keep Vibe Search is an AI-powered semantic search and chat assistant for personal note management. It enables users to search their Google Keep notes by meaning rather than keywords, engage in conversational AI about their note collection, automatically organize notes into categories using AI, and manage tags across their entire collection.

### Problem Statement

Users accumulate thousands of notes in Google Keep over time, making it difficult to locate specific information. Traditional keyword-based search fails when users don't remember exact phrases or need to find notes related by theme. Additionally, users lack tools to organize large note collections into meaningful categories, or to manage tags at scale across hundreds of notes.

### Solution

- **Semantic Search** -- Transformer-based embeddings find notes by meaning, not just keywords
- **AI Chat with RAG** -- Conversational Q&A with source citations using retrieval-augmented generation
- **AI Categorization** -- Automatic topic discovery and tag proposals via UMAP + HDBSCAN clustering and LLM naming
- **Tag Management** -- Full tag lifecycle: create, rename, merge, remove, filter, and exclude across all notes
- **Visual Exploration** -- Cluster notes into semantic groups with interactive 3D scatter plots
- **Image Search** -- Find notes by visual content using CLIP embeddings

### Target Users

- Individual Google Keep users with large note collections (500+ notes)
- Knowledge workers who use notes for research, project management, or personal knowledge management
- Users seeking to surface forgotten information and discover connections across their notes

---

## 2. Target Audience & User Roles

### User Personas

| Persona | Description | Key Needs |
|---------|-------------|-----------|
| **Personal Knowledge Manager** | Tech-savvy individual with extensive notes | Semantic search, tag management, connection discovery |
| **Researcher** | Academic or professional with notes from multiple sources | Citation-based chat, chunking for precision, AI categorization |
| **Casual User** | Google Keep user with moderate note volume | Simple search, basic chat, easy setup |

### User Roles

The application operates as a **single-user local application** with no authentication system.

| Role | Access Level | Description |
|------|--------------|-------------|
| **Local User** | Full Read/Write | Full access to all features |

### Data Ownership

- All data remains local on the user's machine
- Notes are parsed from a Google Takeout export (read-only source)
- Embeddings, tags, and chat sessions are cached locally in `./cache/`
- No data is transmitted externally except LLM API calls when configured

---

## 3. Core Features & Functionality

### 3.1 Semantic Search

Find notes using natural language meaning rather than exact keyword matches.

**User Flow:**
1. User enters a natural language query (e.g., "What did I learn about machine learning?")
2. System embeds the query and computes cosine similarity against all note embeddings
3. Results are ranked by combined semantic similarity (70%) and keyword overlap (30%)
4. Results display with relevance scores, tag badges, and matched content

**Technical Details:**
- Model: `sentence-transformers` (`all-MiniLM-L6-v2`)
- Cosine similarity with configurable threshold
- Hybrid scoring: semantic + keyword overlap
- Results enriched with tags before returning to frontend

**Configuration:**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `MAX_RESULTS` | 300 | Maximum results returned |
| `SEARCH_THRESHOLD` | 0.3 | Minimum similarity score (0.0-1.0) |

### 3.2 AI Chat with Citations

Conversational interface where users ask questions about their notes and receive answers with cited sources.

**User Flow:**
1. User navigates to the Chat tab
2. Types a question in natural language
3. System retrieves relevant notes via multi-signal RAG
4. LLM generates a streaming response with `[Note #N]` citations
5. User can view the notes used as context in a side panel
6. Follow-up questions maintain conversational context

**Multi-Signal RAG Pipeline:**
- **Primary search:** Latest user message embedding
- **Context search:** Recent conversation messages (last 3)
- **Topic search:** Conversation topic summary
- **Chunk search:** Note fragment embeddings for long notes
- **Continuity boost:** Previously cited note IDs weighted for follow-ups

**Configuration:**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `LLM_MODEL` | llama3 | Model name for chat |
| `CHAT_CONTEXT_NOTES` | 10 | Notes injected as context per message |
| `CHAT_MAX_RECENT_MESSAGES` | 6 | Recent messages kept verbatim |
| `CHAT_SUMMARIZATION_THRESHOLD` | 12 | Message count before summarization |

### 3.3 Chat Sessions

Persistent conversation threads that survive page reloads.

**User Flow:**
1. Sessions are displayed in a sidebar
2. User can create new, rename, or delete sessions
3. Switching sessions loads the previous conversation
4. Sessions are auto-titled based on the first message

**Technical Details:**
- Sessions stored as JSON files in `./cache/chat_sessions/`
- Each session contains: ID, title, messages, relevant note IDs, timestamps
- Auto-save after each message exchange
- Messages saved separately via dedicated endpoint for auto-titling

### 3.4 Note Chunking

Automatic segmentation of long notes into smaller, semantically coherent chunks for higher-precision retrieval.

**Technical Details:**
- Notes > 500 characters split into paragraphs
- Paragraphs merged into chunks (100-1500 characters)
- Each chunk embedded independently
- Chunk search runs alongside note search in the RAG pipeline
- Results merged and re-ranked with boosted weights

| Parameter | Default | Description |
|-----------|---------|-------------|
| `MIN_CHUNK_LENGTH` | 100 | Minimum chunk size in characters |
| `MAX_CHUNK_LENGTH` | 1500 | Maximum chunk size in characters |
| `SHORT_NOTE_THRESHOLD` | 500 | Length before chunking applies |

### 3.5 Image Search

Find notes by visual content similarity using CLIP embeddings.

**User Flow:**
1. User toggles to Image Search mode
2. Enters a text description or uploads an image
3. System computes CLIP embeddings and matches against note attachments
4. Results blend image scores with text scores

**Technical Details:**
- Model: OpenAI CLIP (`ViT-B/32`)
- Supports text-to-image and image-to-image similarity
- Image scores blended with text scores using configurable weight
- Optional feature, disabled via `ENABLE_IMAGE_SEARCH=false`

**Configuration:**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `ENABLE_IMAGE_SEARCH` | true | Enable/disable CLIP image search |
| `IMAGE_SEARCH_THRESHOLD` | 0.2 | Minimum image similarity |
| `IMAGE_SEARCH_WEIGHT` | 0.3 | Weight of image vs text score |

### 3.6 Tag Management

Full lifecycle tag management across all notes with multiple access points.

**Tag Operations:**

| Operation | Description | Available From |
|-----------|-------------|----------------|
| **Create** | Assign a tag to one or more notes | Search results (bulk select), Tag Dialog |
| **Rename** | Change a tag name across all notes | Note cards (inline), Tag Filter (inline), Tag Manager dashboard |
| **Merge** | Combine two tags into one (rename with deduplication) | Tag Manager dashboard, AI categorization proposals |
| **Remove from note** | Remove a tag from a single note | Note card tag badges |
| **Remove from all** | Delete a tag from every note | Tag Manager (search results), Tag Manager dashboard |
| **Exclude** | Hide tagged notes from search results | Tag Manager (search results) |

**Inline Rename Pattern:**
All inline rename UIs follow the same pattern:
- Click edit icon to enter edit mode
- Input replaces the tag label
- Enter or confirm button to commit, Escape or cancel to abort
- `editCommittedRef` prevents double-fire when Enter triggers blur

**Tag Storage:**
- Tags stored in `./cache/tags.json` (map of note ID to tag name array)
- Excluded tags stored in `./cache/excluded_tags.json`
- No database -- all operations are in-memory with JSON persistence

### 3.7 AI-Powered Categorization (Smart Tags)

Automatic topic discovery and tag proposals using unsupervised clustering and LLM naming.

**User Flow:**
1. User navigates to the Organize tab
2. Selects granularity (broad or specific)
3. Clicks "Discover Categories"
4. System streams progress updates as it:
   - Reduces embedding dimensions via UMAP
   - Clusters notes with HDBSCAN
   - Names clusters via LLM
5. Proposals are displayed as cards with sample notes
6. User reviews each proposal:
   - **Approve** -- Accept the tag as-is
   - **Rename** -- Change the proposed tag name
   - **Merge** -- Combine with another proposal
   - **Reject** -- Discard the proposal
7. Click "Apply" to create tags from approved proposals

**Technical Details:**
- Dimensionality reduction: UMAP (50D for broad, 20D for specific)
- Clustering: HDBSCAN with configurable min_cluster_size
- LLM-based cluster naming via the configured chat endpoint
- Streaming progress via NDJSON (newline-delimited JSON)

### 3.8 Tag Manager Dashboard

Centralized tag management UI in the Organize tab, always available regardless of categorization state.

**User Flow:**
1. Navigate to the Organize tab
2. Scroll to the Tag Manager section (below Smart Tags)
3. View all existing tags with note counts
4. For each tag:
   - **Rename** -- Click edit icon, type new name, confirm
   - **Merge** -- Click merge icon, select target tag from pill buttons
   - **Remove** -- Click delete icon, confirm in dialog

**Technical Details:**
- Uses the same backend endpoints as other tag operations
- Merge is implemented as rename (backend handles deduplication)
- Dashboard refreshes after AI categorization proposals are applied
- Reuses Organize tab CSS classes for visual consistency

### 3.9 Clustering & 3D Visualization

Group notes into semantic clusters and explore them in an interactive 3D scatter plot.

**User Flow:**
1. Navigate to the Clusters tab
2. View notes organized by semantic similarity
3. See cluster keywords as titles
4. Interact with 3D visualization (zoom, pan, rotate)
5. Click on points to view individual notes

**Technical Details:**
- K-means clustering on note embeddings
- PCA reduction to 3D for visualization
- Keywords extracted using TF-IDF with bigram preference
- 3D rendering with `@react-three/fiber` and `three.js`

**Configuration:**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `DEFAULT_NUM_CLUSTERS` | 20 | Default number of clusters |

### 3.10 Search Results Features

**Refinement Search:** Filter search results by additional keywords without re-running the semantic search.

**Bulk Tag Selection:** Select multiple notes from search results and assign a tag to all at once via the Tag Dialog.

**Tag Exclusion:** Exclude notes with specific tags from appearing in search results. Exclusions persist across searches.

**View Modes:** Toggle between list view and 3D visualization for search results.

---

## 4. Technical Architecture & Stack

### 4.1 Backend

| Component | Technology | Purpose |
|-----------|------------|---------|
| **Framework** | FastAPI | REST API server |
| **Server** | Uvicorn | ASGI server |
| **Language** | Python 3.9+ | Runtime |
| **Settings** | Pydantic Settings | Environment configuration |
| **HTTP Client** | httpx | Async HTTP for LLM API calls |
| **ML/Embedding** | sentence-transformers | Text embeddings |
| **Image Processing** | OpenAI CLIP | Vision embeddings |
| **ML Pipeline** | scikit-learn | K-means clustering, similarity |
| **Dim. Reduction** | UMAP | Embedding dimension reduction |
| **Clustering** | HDBSCAN | Density-based clustering |
| **Numerical** | NumPy | Array operations |
| **NLP** | NLTK | Stopword removal |
| **Deep Learning** | PyTorch (CUDA optional) | Model inference |
| **Testing** | pytest | Backend tests |

### 4.2 Frontend

| Component | Technology | Purpose |
|-----------|------------|---------|
| **Framework** | React 19 | UI library |
| **Language** | TypeScript 5.7 | Type safety |
| **Build Tool** | Vite 6 | Development server & bundler |
| **Styling** | Tailwind CSS 4 | Utility-first CSS |
| **3D Graphics** | React Three Fiber + Drei | 3D visualization |
| **3D Engine** | Three.js | WebGL rendering |
| **Markdown** | react-markdown | Render chat responses |
| **Testing** | Vitest | Unit tests |
| **Linting** | ESLint + Prettier | Code quality |

### 4.3 Infrastructure

| Component | Technology | Description |
|-----------|------------|-------------|
| **Containerization** | Docker + Docker Compose | Deployment |
| **LLM Runtime** | Ollama (recommended) | Local LLM inference |
| **Cache Storage** | Local filesystem (JSON, NPZ) | Embeddings, tags, sessions |

### 4.4 Architecture Patterns

**Service-Oriented Architecture:**
- Clean separation between routes, services, and models
- Dependency injection via FastAPI `Depends()`
- Singleton services initialized during app lifespan

**Caching Strategy:**
- Embeddings cached as compressed NumPy arrays (`*.npz`)
- Notes cached as JSON with content hashes for change detection
- Image embeddings cached separately
- Tags and excluded tags persisted as JSON
- Chat sessions persisted as individual JSON files

**RAG Pipeline:**
```
User Query -> Embed -> Multi-Signal Search (note + chunk + context) -> Merge/Rerank -> Context Assembly -> LLM -> Stream Response + Citation Extraction
```

---

## 5. Data Models

### 5.1 Core Entities

#### Note
```python
class Note(BaseModel):
    id: str                                    # File basename
    title: str = ""                            # Note title
    content: str = ""                          # Note body text
    created: str = "Unknown date"              # Creation timestamp
    edited: str = "Unknown date"               # Last edit timestamp
    archived: bool = False                     # Archive status
    pinned: bool = False                       # Pinned status
    color: str = "DEFAULT"                     # Google Keep color
    annotations: Optional[List[Dict]] = None   # Labels/list items
    attachments: Optional[List[Dict]] = None   # Image attachments
    tags: List[str] = []                       # User-assigned tags
    score: Optional[float] = None              # Search relevance score
    matched_image: Optional[str] = None        # Matched image path
    has_matching_images: Optional[bool] = None # Has image matches
```

#### ChatSession
```python
class ChatSession(BaseModel):
    id: str                              # UUID
    title: str                           # Session title
    messages: List[ChatMessage]          # Message history
    relevant_note_ids: List[str] = []    # Cited note IDs
    created_at: str                      # Creation timestamp
    updated_at: str                      # Last update timestamp
```

#### ChatMessage
```python
class ChatMessage(BaseModel):
    role: str      # "user" or "assistant"
    content: str   # Message text
```

#### Tag (Frontend)
```typescript
interface Tag {
    name: string;   // Tag display name
    count: number;  // Number of notes with this tag
}
```

#### TagProposal (AI Categorization)
```typescript
interface TagProposal {
    tag_name: string;           // Proposed tag name
    note_ids: string[];         // Notes in this category
    note_count: number;         // Number of notes
    sample_notes: string[];     // Preview excerpts
    confidence: number;         // Clustering confidence
}
```

### 5.2 Request Models

| Model | Fields | Used By |
|-------|--------|---------|
| `SearchRequest` | `query: str` | POST /api/search |
| `ChatRequest` | `messages, stream, useNotesContext, topic, session_id` | POST /api/chat |
| `TagNotesRequest` | `note_ids: List[str], tag_name: str` | POST /api/notes/tag |
| `TagManagementRequest` | `excluded_tags: List[str]` | POST /api/tags/excluded |
| `RemoveTagRequest` | `tag_name: str` | POST /api/tags/remove |
| `RenameTagRequest` | `old_name: str, new_name: str` | POST /api/tags/rename |
| `CategorizeRequest` | `granularity: str` | POST /api/organize/categorize |
| `ApplyProposalsRequest` | `actions: List[dict]` | POST /api/organize/apply |

---

## 6. API Endpoints

### 6.1 Search

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/search?q=<query>` | Search notes by text query |
| POST | `/api/search` | Search notes by text query (JSON body) |
| POST | `/api/search/image` | Search notes by uploaded image |

### 6.2 Chat

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/chat` | Send message (streaming via SSE) |
| GET | `/api/chat/model` | Get current LLM model name |
| GET | `/api/chat/sessions` | List all chat sessions |
| POST | `/api/chat/sessions` | Create a new session |
| GET | `/api/chat/sessions/{id}` | Load a session |
| DELETE | `/api/chat/sessions/{id}` | Delete a session |
| PATCH | `/api/chat/sessions/{id}` | Rename a session (query param: `title`) |
| POST | `/api/chat/sessions/{id}/messages` | Save messages to session (auto-titles) |

### 6.3 Notes

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/all-notes` | Retrieve all notes with metadata and tags |

### 6.4 Tags

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/notes/tag` | Tag multiple notes with a single tag |
| GET | `/api/tags` | List all tags with note counts |
| GET | `/api/tags/excluded` | Get excluded tags list |
| POST | `/api/tags/excluded` | Set excluded tags |
| DELETE | `/api/notes/{note_id}/tag?tag_name=<name>` | Remove a tag from a single note |
| POST | `/api/tags/remove` | Remove a tag from all notes |
| POST | `/api/tags/rename` | Rename a tag across all notes |

### 6.5 Organize (AI Categorization)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/organize/categorize` | Stream AI category proposals (NDJSON) |
| POST | `/api/organize/apply` | Apply approved proposals as tags |

### 6.6 Embeddings & Clusters

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/embeddings` | Get 3D PCA-reduced note embeddings |
| GET | `/api/clusters?num_clusters=<n>` | Get K-means clusters |

### 6.7 Images

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/image/{image_path}` | Retrieve note attachment image |

### 6.8 System

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/stats` | Note statistics (counts, cache status) |
| GET | `/api/ready` | Backend readiness check |

---

## 7. Third-Party Integrations

### Google Keep (Data Source)
- **Method:** Google Takeout JSON export
- **Data Parsed:** Note titles, content, timestamps, colors, attachments, annotations
- **Format:** Individual JSON files per note
- **Path:** Configured via `GOOGLE_KEEP_PATH`

### LLM Providers (OpenAI-Compatible API)

| Provider | API Base URL | Authentication |
|----------|--------------|----------------|
| Ollama (default) | `http://localhost:11434/v1` | None |
| LM Studio | `http://localhost:1234/v1` | None |
| OpenAI | `https://api.openai.com/v1` | API Key |
| Anthropic (proxy) | Custom URL | API Key |

**Required:** `/v1/chat/completions` endpoint with streaming support.

---

## 8. Frontend Architecture

### Component Structure

| Component | Location | Purpose |
|-----------|----------|---------|
| **SearchBar** | `components/SearchBar.tsx` | Main search input with mode toggle |
| **Results** | `components/Results.tsx` | Search results with bulk selection, refinement, tag exclusion |
| **NoteCard** | `components/NoteCard.tsx` | Note display with inline tag rename, remove, and related search |
| **AllNotes** | `components/AllNotes/` | Browse all notes with sorting, filtering, and tag filter |
| **Chat** | `components/Chat/` | Chat interface with sessions sidebar and context panel |
| **Organize** | `components/Organize/` | Smart Tags AI categorization and Tag Manager dashboard |
| **TagFilter** | `components/TagFilter/` | Tag inclusion filter with inline rename |
| **TagManager** | `components/TagManager/` | Tag exclusion filter with tag removal |
| **TagDialog** | `components/TagDialog/` | Modal for assigning tags to selected notes |
| **Visualization** | `components/Visualization/` | 3D scatter plot with React Three Fiber |
| **NotesClusters** | `components/NotesClusters.tsx` | Cluster tab with keyword-titled groups |
| **ImageGallery** | `components/ImageGallery/` | Lightbox overlay for note images |

### Custom Hooks

| Hook | Purpose |
|------|---------|
| `useSearch` | Search query state, results, refinement |
| `useChat` | Chat messages, streaming, session management |
| `useTags` | Tag CRUD operations (create, rename, remove, exclude) |
| `useAllNotes` | Fetch all notes with metadata |
| `useOrganize` | AI categorization flow (proposals, actions, apply) |
| `useClusters` | K-means cluster data |
| `useEmbeddings` | 3D embedding coordinates |
| `useStats` | Backend statistics |
| `useBackendReady` | Poll backend readiness |
| `useTheme` | Dark/light theme toggle |
| `useError` | Global error state |

### Tab Navigation

| Tab | Component | Description |
|-----|-----------|-------------|
| Search | `SearchBar` + `Results` | Semantic search with results |
| All Notes | `AllNotes` | Browse, sort, filter all notes |
| Chat | `Chat` | AI chat with sessions |
| Clusters | `NotesClusters` | Semantic clustering |
| Organize | `Organize` | AI categorization + Tag Manager |

---

## 9. Project Structure

```
google-keep-vibe-search/
  app/                          # FastAPI backend
    core/
      config.py                 # Pydantic settings (all env vars)
      dependencies.py           # FastAPI dependency injection
      exceptions.py             # Custom exception handlers
      lifespan.py               # Startup/shutdown lifecycle
    models/
      note.py                   # Note data model
      chat.py                   # Chat request/response models
      tag.py                    # Tag management models
      search.py                 # Search request models
    services/
      note_service.py           # Note loading, tag CRUD, enrichment
      search_service.py         # Search orchestration
      chat_service.py           # LLM calls, RAG, streaming
      session_service.py        # Chat session persistence
      chunking_service.py       # Note chunking for precision
      citation_service.py       # Parse [Note #N] citations
      cache_service.py          # Cache I/O operations
    routes/
      search.py                 # Search endpoints
      chat.py                   # Chat endpoints
      notes.py                  # Note endpoints
      tags.py                   # Tag management endpoints
      stats.py                  # Statistics endpoint
      images.py                 # Image serving endpoint
      embeddings.py             # Embedding & cluster endpoints
      organize.py               # AI categorization endpoints
    prompts/
      system_prompts.py         # LLM system prompt templates
    search.py                   # VibeSearch: embedding + similarity engine
    parser.py                   # Google Keep JSON parser
    image_processor.py          # CLIP image embeddings
    main.py                     # FastAPI app entry point

  client/                       # React + TypeScript frontend
    src/
      components/
        AllNotes/               # Browse all notes with tag filtering
        Chat/                   # Chat interface with sessions
        Clusters/               # Cluster visualization (unused alias)
        ImageGallery/           # Image lightbox overlay
        Organize/               # Smart Tags + Tag Manager dashboard
          index.tsx
          CategorizationProgress.tsx
          GranularitySelector.tsx
          ProposalCard.tsx
          ProposalDashboard.tsx
          TagManagementCard.tsx
          TagManagerDashboard.tsx
        ScrollToTop/            # Scroll-to-top button
        TabNavigation/          # Top-level tab bar
        TagDialog/              # Bulk tag assignment dialog
        TagFilter/              # Tag inclusion filter with rename
        TagManager/             # Tag exclusion filter
        ViewToggle/             # List/3D view toggle
        Visualization/          # 3D scatter plot (React Three Fiber)
        NoteCard.tsx            # Note card with tag badges and actions
        Results.tsx             # Search results view
        SearchBar.tsx           # Main search input
        NotesClusters.tsx       # Cluster tab view
        ...
      hooks/
        useSearch.ts
        useChat.ts
        useTags.ts
        useAllNotes.ts
        useOrganize.ts
        useClusters.ts
        useEmbeddings.ts
        useStats.ts
        useBackendReady.ts
        useTheme.ts
        useError.ts
      types/
        index.ts                # All TypeScript interfaces and types

  cache/                        # Runtime cache (gitignored)
    embeddings.npz
    notes_cache.json
    notes_hash.json
    chunk_embeddings.npz
    image_embeddings.npz
    image_hashes.json
    tags.json
    excluded_tags.json
    chat_sessions/

  tests/                        # Backend tests (pytest)
    conftest.py
    test_parser.py
    test_citation_service.py
    test_session_service.py
    test_chunking_service.py

  scripts/
    setup.ps1 / setup.sh        # Environment setup
    dev.ps1 / dev.sh            # Development servers

  .env.example                  # Environment template
  requirements.txt              # Python dependencies
  docker-compose.yml            # Docker deployment
  Dockerfile                    # Backend container
  README.md                     # Project documentation
```

---

## 10. Configuration Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GOOGLE_KEEP_PATH` | Yes | -- | Path to Google Takeout Keep folder |
| `MAX_RESULTS` | No | 300 | Maximum search results returned |
| `SEARCH_THRESHOLD` | No | 0.3 | Minimum similarity score (0.0-1.0) |
| `DEFAULT_NUM_CLUSTERS` | No | 20 | Default number of clusters |
| `HOST` | No | 127.0.0.1 | Backend bind address |
| `PORT` | No | 8000 | Backend port |
| `LLM_API_BASE_URL` | No | (derived from Ollama) | OpenAI-compatible API base URL |
| `LLM_API_KEY` | No | (empty) | API key for cloud providers |
| `LLM_MODEL` | No | llama3 | Model name for chat and categorization |
| `CHAT_CONTEXT_NOTES` | No | 10 | Notes injected as context per chat message |
| `CHAT_MAX_RECENT_MESSAGES` | No | 6 | Recent messages kept verbatim in context |
| `CHAT_SUMMARIZATION_THRESHOLD` | No | 12 | Total messages before summarization |
| `OLLAMA_API_URL` | No | http://localhost:11434 | Ollama server URL |
| `ENABLE_IMAGE_SEARCH` | No | true | Enable CLIP-based image search |
| `IMAGE_SEARCH_THRESHOLD` | No | 0.2 | Minimum image similarity score |
| `IMAGE_SEARCH_WEIGHT` | No | 0.3 | Weight of image score vs text score |
| `CACHE_DIR` | No | ./cache/ | Cache directory path |
| `FORCE_CACHE_REFRESH` | No | false | Ignore cached data on startup |
