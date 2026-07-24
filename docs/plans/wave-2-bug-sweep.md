# Wave 2 — S1 bug sweep (PARALLEL, 5 agents)

Every user-visible correctness bug from the audit. Five lanes, disjoint write sets, dispatch all at
once. Total ≈ 2 developer-days, ≈ ½ day wall-clock.

**Shared rule for this wave:** every fix ships with a regression test that fails before it and passes
after. Several of these bugs survived for months precisely because nothing asserted the behaviour.
Reproduce with synthetic notes written inline in the test — never the real export.

---

## Lane A — chat & agent

**Owns:** `app/services/chat_service.py`, `app/services/agent/**`,
`app/services/reranker_service.py`, `tests/test_agent.py`, `tests/test_pydantic_agent.py`,
`tests/test_chat_service_seq.py`.

### T03 — Chat pipeline correctness

**Fixes:** B1, B5, B6, B7, B11.

**Do**
1. **B1 — follow-up suggestions have never worked.** `chat_service.py:255` uses `FOLLOW_UP_PROMPT`,
   which is never imported; the `NameError` is swallowed by `except Exception: return []` at :262.
   Import it from `app.prompts.system_prompts`. Then narrow that bare `except` so a future
   `NameError` surfaces instead of silently disabling the feature — catch the LLM/transport errors you
   actually expect and let programming errors propagate.
2. **B7 — `AGENT_MAX_STEPS` is ignored.** `:116` calls `gather_context_pydantic_agent(query,
   search_service)` with no `max_steps`, so the function default (5) always wins. Pass
   `max_steps=settings.agent_max_steps`.
3. **B6 — agent mode injects up to 250 full notes into the prompt.** `_stream_agentic` hands
   `item.notes` straight to `ContextBuilder`, ignoring `chat_context_notes`. Before building the
   prompt: cross-encoder rerank the collected set against the user query
   (`self.retrieval.reranker`, top-20 candidate window like the orchestrator uses) and cap to
   `self.retrieval.max_context_notes`. The UI token meter assumes this cap, so this also makes the
   meter honest.
4. **B5 — the agent's `filter_by_tag` tool always returns 0 notes.** `pydantic_agent.py:192-197`
   reads `n.get("tags", [])` on raw `search_service.notes`, which are never tag-enriched (enrichment
   only mutates route-level copies). Fix inside this lane: pass the tag lookup into
   `gather_context_pydantic_agent` as an explicit parameter (a `Callable[[str], list[str]]` or a
   `Mapping[str, list[str]]`) supplied by `chat_service` from the service it already holds. Do **not**
   edit `note_service.py` or `lifespan.py` — Lane C owns those. If the value you need is not reachable
   from `ChatService`, stop and report it as a blocker rather than reaching across lanes.
5. **B11 — the legacy path never verifies citations.** `_stream_agentic` calls `verify_citations`
   (:148) but `_stream_legacy` does not (:217), so the *default* config emits unverified `[Note #N]`.
   Hoist the verify + `citation_warnings` handling into a small shared helper used by both paths.
   Keep it a helper; do not merge the two stream methods (that is T20).

**Tests:** one per fix. For B5, assert a tag query returns the tagged note. For B6, assert
`len(prompt_notes) <= chat_context_notes` given 100 collected notes. For B1, assert the suggestions
list is non-empty with a stubbed LLM — and add a guard test that an unexpected `NameError` inside
`_generate_suggestions` is not swallowed.

**Checkpoint**
```
GOOGLE_KEEP_PATH=. uv run pytest tests/test_agent.py tests/test_pydantic_agent.py \
    tests/test_chat_service_seq.py -q     # all pass, ≥5 new tests
make check                                 # exits 0
```

**Commit:** `fix(chat): suggestions import, agent tag tool, context cap, max_steps, legacy citation verify`

---

## Lane B — search engine

**Owns:** `app/search.py`, `app/services/search/bm25.py`, `tests/test_hybrid_search.py`,
`tests/test_bm25.py`.

### T04 — The reranker silently caps search at 20 results

**Fixes:** B2.

**Do** `search.py:372-375` reranks `results[:20]` and then returns `top_k=max_results` **of those
20**, so `MAX_RESULTS=300` is dead and the Search tab can never show more than 20 notes. Keep the
cross-encoder on a bounded candidate window (that is the point of a reranker — do not feed it 300
pairs), but preserve the tail: rerank the top *N* (start at 50, a constant with a comment) and
**append** the un-reranked remainder in fused order, then slice to `max_results`.

**Test:** with 60 synthetic notes matching a query and a stub reranker, assert `len(results) > 20`
and that the first *N* are in reranker order while the tail keeps RRF order.

**Checkpoint**
```
GOOGLE_KEEP_PATH=. uv run pytest tests/test_hybrid_search.py -q
```

**Commit:** `fix(search): stop the reranker truncating results to the candidate window`

### T05 — BM25 recomputes everything on every query

**Fixes:** A9. **Depends on:** T04 (same file family).

**Do** `bm25.py:538-553` rebuilds `Counter(self.tokens[i])` and re-runs `clean_note()` regexes for
**every note on every query**, and `search.py:204` calls it with `k=len(self.notes)`. At 2k+ notes
this dominates search latency. In `BM25Index.build`, precompute per-document term frequencies and the
normalized text; use them in `search`. An inverted index (`term → [(doc, tf)]`) so scoring visits only
documents containing a query term is the better fix if it stays simple — otherwise the precompute
alone is most of the win.

**Constraint:** identical ranking before and after. Prove it — that is the checkpoint.

**Checkpoint**
```
# a test that asserts the ranked (id, score) list is unchanged vs a recorded baseline
GOOGLE_KEEP_PATH=. uv run pytest tests/test_bm25.py -q
```
Include a before/after timing for 500 synthetic notes × 20 queries in the commit body.

**Commit:** `perf(bm25): precompute term frequencies and normalized text at build time`

---

## Lane C — ingestion & tags

**Owns:** `app/parser.py`, `app/services/note_service.py`, `app/services/search_service.py`,
`app/core/lifespan.py`, `tests/test_parser.py`, `tests/test_note_service.py`.

### T06 — Checklist notes are invisible; Keep labels are discarded

**Fixes:** B3a.

**Do** `parser.py:50-67` reads only `textContent`. Google Keep stores checkbox notes in
`listContent: [{text, isChecked}]`, so those notes get empty text and are then dropped by the
`if cleaned.strip()` guard in `search.py:63` — invisible to search, chat, chunks, clustering and
tagging. In `parse_notes`:
1. When `textContent` is empty/absent and `listContent` is present, render items into `content` as
   `- [ ] item` / `- [x] item` lines, in order. If both exist, append the list after the text.
2. Expose Keep's own `labels: [{name}]` as `note["labels"] = [str]` (parse only — T07 turns them
   into tags).
3. Leave `compute_notes_hash` covering title + text only for now (T24 replaces the hashing scheme);
   note in a comment that list content is not yet hashed, so a checkbox-only edit will not invalidate
   the cache until then. Flag it, do not fix it here.

**Tests:** synthetic Keep-shaped dicts — list-only note, mixed note, note with labels, trashed note
still skipped, malformed JSON still counted as a parse failure.

**Checkpoint**
```
GOOGLE_KEEP_PATH=. uv run pytest tests/test_parser.py -q     # ≥4 new tests
```

**Commit:** `fix(parser): flatten Keep list content and surface source labels`

### T07 — Labels become tags; excluded tags are honoured everywhere

**Fixes:** B3b, B10. **Depends on:** T06.

**Do**
1. **Labels → tags.** On startup, seed `note_tags` from `note["labels"]` for notes that have no tag
   for that name yet. Additive and idempotent: never remove a user tag, never duplicate, and
   re-running startup must not change `tags.json`. This hands the user a real tag vocabulary for
   free, and gives Smart Tags anchor tags to reuse (T27).
2. **B10 — excluded tags leak into chat.** Only `/api/search` and `/api/all-notes` call
   `filter_by_excluded_tags`; both chat retrieval paths bypass it, so explicitly excluded notes still
   reach the LLM. Fix at the choke point: give `SearchService` the note service and filter inside
   `SearchService.search`, which every caller (routes, orchestrator, agent tools) already goes
   through. Wire the dependency in `lifespan.py`. The route-level filter then becomes redundant but
   harmless — leave it; Lane D owns the routes.
3. Keep `SearchService` a thin façade. This is the seam that becomes the `Retriever` in T26/Stage 4 —
   do not grow it beyond filtering.

**Tests:** excluding a tag removes its notes from `SearchService.search`; startup twice produces
identical `note_tags`; a user tag is never clobbered by a label of the same name.

**Checkpoint**
```
GOOGLE_KEEP_PATH=. uv run pytest tests/test_note_service.py tests/test_parser.py -q
```

**Commit:** `fix(tags): seed tags from Keep labels and enforce exclusions in all retrieval`

---

## Lane D — routes & client

**Owns:** `app/routes/images.py`, `app/routes/organize.py`, `client/src/hooks/useOrganize.ts`,
`client/src/hooks/__tests__/buildApplyAction.test.ts`, `tests/test_organize_apply.py`.

### T08 — Path traversal in the image route

**Fixes:** B12.

**Do** `routes/images.py:13-16` guards with `full_path.startswith(base)`, which accepts sibling
escapes: with `base = /data/Keep`, the path `../Keep_other/x` normalizes to `/data/Keep_other/x`,
which passes `startswith`. Replace with a real containment check —
`Path(full).resolve().is_relative_to(Path(base).resolve())` (or `os.path.commonpath`) — and return
400 on failure without echoing the attempted path back.

**Test:** `../Keep_other/x`, `../../etc/passwd`, an absolute path, and a symlink escape all 400; a
legitimate nested image path still 200s.

**Checkpoint**
```
GOOGLE_KEEP_PATH=. uv run pytest -q -k image     # traversal cases all 400
```

**Commit:** `fix(images): reject sibling-prefix path traversal`

### T09 — "Merge" on a tag proposal silently behaves as "approve"

**Fixes:** B8.

**Do** The client stages a merge target (`useOrganize.ts:226-237` sets `mergeTarget`) but
`buildApplyAction` (:44-51) drops it, and the backend lumps `merge` in with `approve`
(`routes/organize.py:33-46`), tagging notes with their **own** name. So the button lies.
1. Client: for `action === 'merge'`, emit `{action: 'merge_tags', source_tag: proposal.tag_name,
   target_tag: state.mergeTarget}` — the payload shape the backend already handles for gray-zone
   merges, so no new backend action type is needed.
2. Backend: verify the merge branch applies the source tag's notes to the target and then renames, and
   that a merge whose source was never applied still degrades gracefully (the existing
   `except (KeyError, ValueError): continue`).
3. Extend `buildApplyAction.test.ts` — it is the one client unit test that already exists for this.

**Checkpoint**
```
cd client && npx vitest run                              # merge case asserted
GOOGLE_KEEP_PATH=. uv run pytest tests/test_organize_apply.py -q
```

**Commit:** `fix(organize): make the merge proposal action actually merge tags`

---

## Lane E — privacy

**Owns:** `app/services/categorization_service.py`, `app/core/redact.py` (new),
`tests/test_categorization_service.py`.

### T10 — Stop leaking prompts and note text into logs

**Fixes:** P1, P2, P3. **This is the highest-severity finding in the audit that is not a visible bug.**

**Do**
1. `categorization_service.py:444` and `:455` write `f"EXCEPTION:{str(e1)}"` to `llm_failures.log`,
   and `:461` calls `traceback.print_exc()`. The comment claims "WITHOUT exposing the prompt", but
   LiteLLM/httpx exceptions routinely embed the **request body** — which contains
   `Title: … / Snippet: …` sampled note text (`format_note_sample`). `*.log` is gitignored, so this
   would never be noticed. Log `type(e).__name__`, the attempt number, and a status code if present.
   Nothing else.
2. Add `app/core/redact.py` with a tiny, documented API — e.g. `safe_exc(e) -> str` (type + code
   only) and `safe_meta(**kw) -> str` (counts/ids/shapes/timings). Make it the single sanctioned way
   to log anything adjacent to an LLM call. Keep it under ~40 lines; no dependencies.
3. Audit every `print`/log in this file and route it through the helper. Cluster **names** are fine
   (they are generated tags); sampled note text, prompts, and raw LLM error payloads are not.
   `:465`'s `RAW LLM: {repr(raw)}` prints a model-generated tag — keep it but route it through the
   helper and truncate.
4. Decide `pydantic_agent._log_agent_step` explicitly: it prints the user's question and every
   generated probe. That is user text, not note text. Recommendation — keep it (it is the debugging
   surface the agent needs) but say so in a one-line comment referencing this task, so it reads as a
   decision rather than an oversight. **Do not edit that file** — it is Lane A's. Record the
   recommendation in your commit body and add it to `PLANS.md` as a proposed follow-up if you think
   it should change.

**Test:** call the naming path with a stubbed LLM that raises an exception whose message contains a
sentinel string, then assert the sentinel appears in **no** log output, no file under the repo root,
and no captured stdout.

**Checkpoint**
```
GOOGLE_KEEP_PATH=. uv run pytest tests/test_categorization_service.py -q    # sentinel-leak test passes
grep -rn "str(e" app/services/categorization_service.py                     # no raw exception strings
```

**Commit:** `fix(privacy): redact LLM failures so note text can never reach logs`
