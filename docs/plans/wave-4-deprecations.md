# Wave 4 — Deprecations (PARALLEL, 4 agents + 1 serial tail)

Answers Q1/Q2/Q3 from the audit. Removes ≈ 700 LOC and one of the three clustering systems. Safe to
do aggressively **because** Wave 3's integration test now pins the behaviour that must survive.
Total ≈ 1¾ developer-days, ≈ ¾ day wall-clock.

Lanes H, I, J, K dispatch together. **T20 is serial and last** — it depends on T19 landing.

---

## Lane H — remove the Clusters tab

**Owns:** `client/src/components/NotesClusters.tsx`, `client/src/components/ClustersButton.tsx`,
`client/src/hooks/useClusters.ts`, `client/src/components/TabNavigation/**`, `client/src/App.tsx`,
`app/routes/embeddings.py`, `app/search.py`.

### T15 — Delete KMeans clustering; recolour the 3D map by tag

**Fixes:** Q1, A2, A10.

**Rationale (from the audit):** KMeans with a user-guessed `k`, recomputed on every request, labelled
by a bespoke bigram counter, producing groups you cannot name, tag, persist or approve. Smart Tags
does the same job with HDBSCAN + LLM naming + a review flow. This is the weakest of the three
clustering systems.

**Do**
1. Delete: the `clusters` tab entry and `TabId` member, `NotesClusters.tsx`, `ClustersButton.tsx`
   (already unreferenced — A16), `useClusters.ts`, `NoteCluster` from `types/index.ts`, the
   `CLUSTERS` API route constant, `GET /api/clusters`, `VibeSearch.get_clusters`,
   `VibeSearch._extract_cluster_keywords`, `DEFAULT_NUM_CLUSTERS`, and the now-unused `KMeans` /
   `stopwords` / `nltk` imports in `search.py`. Check whether `nltk` is still needed anywhere before
   touching `pyproject.toml` — if it becomes unused, note it for T32 rather than editing packaging
   here.
2. **Keep the 3D map.** It is reached from the Results / All Notes view toggle, not the deleted tab, so
   removing the tab does not remove it. Re-purpose it: `GET /api/embeddings` also returns each note's
   tags, and the visualization colours points by primary tag instead of KMeans cluster — turning it
   into a visual map of the Smart Tags result.
3. `@lru_cache` the PCA projection keyed by the embeddings hash (A10) — it currently re-runs on every
   request.

**Checkpoint**
```
GOOGLE_KEEP_PATH=. uv run pytest -q && cd client && npx tsc -b && npx vitest run
grep -rn "get_clusters\|useClusters\|NoteCluster\|api/clusters" app client/src   # no hits
```
Report LOC removed (`git show --stat`) in the commit body.

**Commit:** `refactor: remove KMeans clusters tab, colour the 3D map by tag`

---

## Lane I — remove the Topic input

**Owns:** `client/src/components/Chat/index.tsx`, `client/src/hooks/useChat.ts`,
`app/models/chat.py`, `app/routes/chat.py`, `app/services/retrieval_orchestrator.py`.

### T16 — Replace Topic with tag/date scoping

**Fixes:** Q3, B13.

**Rationale:** the Topic field is a fifth RRF list capped at 5 notes, suppressed whenever it resembles
the question — and **entirely ignored in agent mode** (B13: `_stream_agentic` accepts `topic` and
never reads it). It is a no-op in the mode the app is standardising on.

**Do**
1. Remove the disclosure toggle, the input, `showTopicInput`, `topic`/`setTopic` from `useChat`, the
   `topic` field on `ChatRequest`, and `topic_results` plus the `topic` parameter from
   `RetrievalOrchestrator.get_context`. Leave `chat_service.py` alone — Lane A/K own it; if the
   `topic` argument must change there, report it as a blocker (T20 removes those signatures anyway).
2. Add real scoping in its place, because the retrieval layer can now enforce it: tag chips (from
   `/api/tags`) and an optional date range, passed as structured filters and applied through
   `SearchService` (the T07 choke point). This is also where B10's fix earns its keep.
3. Also delete the `clearChat` / `newChat` duplication in `useChat` — byte-identical (A16).

**Checkpoint**
```
cd client && npx tsc -b && npx vitest run
grep -rnw "topic\|setTopic\|showTopicInput\|topic_results" client/src app/models/chat.py \
    app/services/retrieval_orchestrator.py   # no hits (-w: whole words, so "topical" etc. don't trip it)
GOOGLE_KEEP_PATH=. uv run pytest tests/test_api_integration.py -q   # scoping asserted
```

**Commit:** `refactor(chat): drop the no-op topic input for tag and date scoping`

---

## Lane J — dead code and doc rot

**Owns:** `app/services/agent/tools.py`, `tests/test_agent.py`, `docs/plans/23-*.md`,
`.claude/rules/**`, `.github/instructions/**`, `.github/copilot-instructions.md`, `AGENTS.md`, `docs/research/**`.

### T17 — Delete `agent/tools.py`

**Fixes:** A14.

**Do** `AgentTools` + `TOOL_SCHEMAS` (195 LOC) are referenced **only** by `tests/test_agent.py`; the
live agent dispatches tools inline in `pydantic_agent.py`. Delete the module and its test class. If
Lane A's T03 added tests to `test_agent.py`, keep those — `git pull --ff-only` picks up Lane A's committed work
(`EXECUTION-PROTOCOL.md` §3); do not edit or rewrite it.

**Checkpoint** `grep -rn "AgentTools\|TOOL_SCHEMAS" app tests` → no hits; `pytest -q` green.

**Commit:** `refactor: delete the unused AgentTools module`

### T18 — Fix dangling references and dedupe agent instructions

**Fixes:** H3, H4.

**Do**
1. Delete `docs/plans/23-live-acceptance-signoff.md` — superseded; its acceptance checkpoints moved
   into T27 and T14 (see `PLANS.md` § Superseded).
2. `.github/copilot-instructions.md` points at `docs/memories/`, which does not exist — point it at
   `docs/audit/` and `docs/plans/PLANS.md` instead.
3. Collapse the duplicated instruction pairs: `.claude/rules/{python,typescript}.md` and
   `.github/instructions/{python,typescript}.instructions.md` say nearly the same thing. Keep one
   source of truth and have the other reference it (or symlink if the tooling permits).
4. Update the stale notes in `AGENTS.md` § Critical Technical Findings: `ChatService` no longer "needs
   splitting" (it is a 262-line orchestrator), and the frontend per-chunk re-render problem is solved
   (RAF batching in `useChat`). Point the citation-handler note at reality — it works; the id
   contract is `context-note-{n}` in `ChatNotes.tsx`. Add the privacy-logging rule from T10.
5. Fix `docs/research/` rot: add a one-paragraph header to each file saying what actually shipped, or
   move superseded files to `docs/research/superseded/`. Do not delete them — they hold the reasoning.

**Checkpoint** every relative path referenced from `AGENTS.md`, `CLAUDE.md`, `.github/*.md` and
`docs/plans/*.md` resolves. Script it in the commit body.

**Commit:** `docs: repair dangling references and dedupe agent instructions`

---

## Lane K — agent parity, then legacy removal

**Owns:** `app/services/chat_service.py`, `app/services/agent/pydantic_agent.py`.

### T19 — Route the agent's search tool through `RetrievalOrchestrator`

**Fixes:** Q2 pre-requisite. **The reason legacy chat cannot simply be deleted today.**

**Do** The agent currently calls raw `search_service.search(q)`, so it loses everything the legacy
path has: chunk-level search, cross-encoder reranking, query decomposition, the entity signal, the
continuity boost, and CRAG gap analysis. Make the agent's `search_notes` / `search_chunks` tools call
`RetrievalOrchestrator` instead, so both paths share one retrieval implementation. Keep the agent's
own loop control (`coverage_is_sufficient`, the duplicate-query guard) — that is deliberately
deterministic and stays. `gap_status` should come from the orchestrator rather than being hardcoded
`"sufficient"` in `AgentResult`.

**Checkpoint**
```
make eval-retrieval    # agent-mode MRR >= legacy-mode MRR on the golden set (T13) — the tripwire
GOOGLE_KEEP_PATH=. uv run pytest tests/test_api_integration.py -q   # both modes still pass
# the evidence: tier 2 (EXECUTION-PROTOCOL.md §4) — run bench/run_retrieval.py (T36) in both modes;
# agent-mode MRR/nDCG must match or beat legacy on the real corpus. Paste both tables.
```
Parity is the gate, and mode-vs-mode ranking is a tier-2 question — the stub eval alone cannot decide
it. If agent mode does not match or beat legacy on **both** the golden set and the real-corpus bench,
**stop and report** — do not proceed to T20.

**Commit:** `refactor(agent): retrieve through the shared orchestrator`

### T20 — Flip the default; delete `_stream_legacy` (SERIAL, after T19)

**Fixes:** Q2, A13. **Depends on:** T19 checkpoint passing.

**Do**
1. Default agent mode on, then delete `_stream_legacy`, the `agent` branch in
   `stream_chat_with_protocol`, and the `ENABLE_AGENT_MODE` setting (the one sanctioned exception to
   the frozen-config rule — `EXECUTION-PROTOCOL.md` §5). Remove it from `.env.example`, the README
   table, and
   `/api/chat/model`'s payload.
2. `_stream_agentic` and `_stream_legacy` were ~90% identical (context → conflicts → build → stream →
   citations → suggestions → verification → grounding). One path remains; fold T03's shared citation
   helper back inline if that reads better.
3. Keep single-shot retrieval as an **automatic fast path**, not a user-visible mode: a 0-step agent
   run *is* the legacy path, and `coverage_is_sufficient` already computes the decision. Verify a
   simple query still resolves in one step so cheap questions do not pay for a loop.

**Checkpoint**
```
grep -rn "ENABLE_AGENT_MODE\|enable_agent_mode\|_stream_legacy" app client/src .env.example README.md
    # no hits
GOOGLE_KEEP_PATH=. uv run pytest -q && make eval-retrieval    # no MRR regression
```
Report: LOC removed, and the step count for a simple vs a complex query.

**Commit:** `refactor(chat): single agentic path, remove the legacy mode flag`
