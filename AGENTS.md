# Google Keep Vibe Search - Agent Context

Google Keep Vibe Search is a full-stack note search and chat application for Google Keep exports.
- **Backend:** Python 3.9+, FastAPI (`app/`)
- **Frontend:** React 19, TypeScript, Vite 6 (`client/`)

## Important Rules & Conventions
- **STRICT PRIVACY BOUNDARY:** Never read, open, print, summarize, query, embed, or log the raw contents of a user's notes — directly OR indirectly (logs, debug output, captured stdout, tracebacks, terminal scrollback, agent transcripts). This is the single most important rule; when in doubt, refuse and ask.
  - **Forbidden files/paths — NEVER read or dump their contents** (no `cat`/`head`/`tail`/`less`/`jq`/`grep`/`sed`/`awk`/`strings`/`open()`/`Read`, no SQL, no piping to stdout):
    - The entire cache directory `settings.resolved_cache_dir` (default `cache/`), including `notes_cache.json`, `entity_index.json`, `chat_sessions/`, `tags.json`, `excluded_tags.json`, `pending_proposals.json`, every `*.bak` beside them, `*.npz` embeddings, `*_hash.json`.
  - **NEVER WRITE INTO THE REAL CACHE EITHER.** This has destroyed real user data twice: a test built a real `NoteService` without redirecting `settings.cache_dir` and emptied the user's `tags.json`, and a benchmark set `CACHE_DIR` *after* importing an app module — too late, since `settings` is built at first import — and overwrote the real `embeddings.npz`/`notes_hash.json`. Tests get an isolated cache from the autouse `isolate_cache_dir` fixture, which also blocks writes aimed at the real one; benchmarks get theirs from `bench/__init__.py` before any app import, and must call `bench.assert_cache_isolated()`. Never bypass either. Listing the directory (names/sizes/mtimes) is fine.
    - The Google Takeout / Keep export folder at `$GOOGLE_KEEP_PATH` (all `*.json` / `*.html` note files).
    - `.env` and any secrets file.
    - Any log or scratch file that may embed a note or an LLM prompt (e.g. `llm_failures.log`, `*.log`, debug dumps). Reading the *directory listing* (names/sizes) is fine; reading file *contents* is not.
  - **The debugging/logging vector is the real risk.** The tag-naming prompt embeds sampled note text via `format_note_sample()` (`Title: … / Snippet: …`). NEVER write prompts, note titles, or note bodies to a file, `print()`, or log statement — not even temporarily "just for debugging". If you add debug logging, log only structural metadata: counts, array shapes, cluster sizes, note IDs/hashes, timings, exception types — never note/prompt text.
  - **Do not run the app or pipeline in a way that dumps notes to captured stdout** (e.g. verbose prompt logging while a tool captures output). If a traceback or command output would contain note text, redact it before saving or pasting anywhere.
  - When you need to reproduce a bug involving notes, use synthetic/fixture data (see the fake-data generators), never the real corpus.
- Be concise in responses.
- Ask clarifying questions instead of guessing when codebase is ambiguous.
- Read existing code before changing. Make minimal, surgical changes.
- Handle errors explicitly at boundaries.
- Use the available global and project level skills when a use case for them exists.

## Architecture & Workflows
- **LLM Integration:** All calls go through `app/services/llm_client.py` (LiteLLM). Model string is `settings.resolved_litellm_model`. For Ollama, `api_base` must be the raw URL without `/v1/`.
- **Chat Pipeline:** One agentic path, always on — the `ENABLE_AGENT_MODE` flag and the legacy single-shot path were removed in T20. It yields `AgentStep` for live UI streaming. Streaming Protocol uses NDJSON (types: `phase`, `context`, `delta`, `done`, `suggestions`, `verification`, `agent_step`, `grounding`, `error`). The Organize categorize stream (separate NDJSON protocol) uses `progress`, `proposals`, `proposal`, `label_updates`, `done`, `error`.
- **Categorization Pipeline:** Math-heavy, LLM-light. Embeds notes -> groups via HDBSCAN (logarithmic sizing) -> extracts cluster keywords via c-TF-IDF -> samples 5-10 notes per cluster -> asks LLM to generate 1 tag via `complete_with_tools` -> applies tag to entire cluster. The LLM NEVER reads the whole corpus.
- **Setup/Validation:** Use `make setup`, `make dev`, `make test`, `make lint`, `make build`.
- **Plan Tracking:** Implementation plans live in `docs/plans/PLANS.md`.

## Critical Technical Findings (Memory)
- **PyTorch/CUDA Setup:** App runs on GPU with `torch==2.1.2` (cu121) and `numpy<2`. Use `SentenceTransformer(...).to("cuda")` instead of `device="cuda"` (fails in 2.2.2).
- **Local LLM Tool Calling:** Instruct models on LM Studio hallucinate tags. Use LiteLLM `complete_with_tools` with explicit schema and `tool_choice="required"`.
- **LLM Output Validation:** Strict regex word bounds fail on LLM tags containing numbers/symbols (e.g. "3D Printing", "&"). Use full-string character set validation (`^[A-Za-z0-9\s&/-]*$`).
- **Chat System Debt:** `ChatService` is a 262 LOC orchestrator now. Frontend uses RAF batching in `useChat` to solve re-render issues. Citation click handler uses `context-note-{n}` in `ChatNotes.tsx`.
- **Privacy Logging Rule (T10):** NEVER read, open, print, summarize, query, embed, or log raw note contents. If you add debug logging, log only structural metadata: counts, shapes, ids, hashes, timings, exception types. NEVER note/prompt text.