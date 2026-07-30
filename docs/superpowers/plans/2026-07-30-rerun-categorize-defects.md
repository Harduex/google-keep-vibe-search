# Re-run Categorization Defects Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the confirmed defects when re-running Auto-Categorize over already-tagged notes: duplicate proposal cards whose accept/discard clicks mis-route or do nothing, same-named clusters collapsing in consolidation, and `_sanitize_tag_name` mangling vault tags the LLM correctly reused.

**Architecture:** Every `Label` gets a stable `proposal_id` (uuid4 hex) that flows through streamed `proposal` frames, consolidation merges, and the final `label_updates` frame; the review UI stages decisions against that id and maps id → name only at the server lock-list boundary (whose contract stays name-keyed). Names are made unique during the naming loop, before anything streams. Vault-tag reuse matches case-insensitively before sanitization. Spec: `docs/feature-ideas/scoped-retagging-and-replacement.md` Part 2 ("The fix, in dependency order"). Part 1 (scope/write-mode) is explicitly out of scope.

**Tech Stack:** FastAPI + Pydantic backend (`app/`), React 19 + TypeScript frontend (`client/`), pytest + vitest.

## Global Constraints

- **PRIVACY:** never read real note data (`cache/`, `$GOOGLE_KEEP_PATH`, `.env*`, `*.log`). All tests use synthetic notes; backend tests rely on the autouse `isolate_cache_dir` fixture (never bypass it); never add logging of note/prompt text — structural metadata only.
- Backend checks from repo root: `uv run pytest tests/ -x -q` (or `make test` for everything). Frontend from `client/`: `npx vitest run`, `npx tsc --noEmit`, `npm run lint` (needs Node >= 22.12; `nvm use 22.23.2` if 22.9 hits ERR_REQUIRE_ESM).
- Commits: conventional style, NO Co-Authored-By trailer, never push. Pre-commit runs black/isort/prettier; on "files were modified by this hook", re-add and commit again.
- The server lock-list contract stays name-keyed: `PUT /organize/pending/actions` stores `{tag_name: action}` (`app/routes/organize.py`), and consolidation locks by name. Do not change that contract.
- Follow existing test patterns: backend pipeline tests model on `tests/test_pipeline.py` (stub LLM + stubbed SearchService, stream-contract style); frontend hook tests model on the vitest + Testing Library patterns in `client/src/hooks/__tests__/` and `client/src/components/__tests__/`.

---

### Task 1: `proposal_id` on `Label`, emitted everywhere

**Files:**

- Modify: `app/models/label.py`
- Modify: `app/services/categorization_service.py` (streamed `proposal` frame ~line 1140; `_apply_merge_map` merged label ~line 355)
- Test: `tests/test_label_identity.py` (create)

**Interfaces:**

- Produces: `Label.proposal_id: str` — uuid4 hex, `Field(default_factory=lambda: uuid.uuid4().hex)`, assigned at construction so every creation site gets one for free (cluster loop, noise label, incremental path, Uncategorized).
- `LabelVocabulary.to_proposals()` dicts gain `"proposal_id": lbl.proposal_id` — this covers the final `label_updates` frame and incremental mode's `proposals` frame without touching those call sites.
- The streamed `proposal` frame dict (categorization_service.py ~1142, built inline to match `to_proposals()` element-for-element) gains the same `"proposal_id": lbl.proposal_id` key.
- `_apply_merge_map`: the merged replacement `Label` keeps the identity of the merge **target** when the target label was found in the map, else the largest constituent's id — a staged decision on the surviving card must stay attached through the merge.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_label_identity.py
"""proposal_id: every Label carries a stable unique identity that survives merging."""

from app.models.label import Label, LabelVocabulary
from app.services.categorization_service import CategorizationService


def test_labels_get_unique_proposal_ids():
    a = Label(name="Topic", seed_note_ids=["1"])
    b = Label(name="Topic", seed_note_ids=["2"])
    assert a.proposal_id and b.proposal_id
    assert a.proposal_id != b.proposal_id


def test_to_proposals_includes_proposal_id():
    vocab = LabelVocabulary()
    lbl = Label(name="Topic", seed_note_ids=["1"])
    vocab.add(lbl)
    (proposal,) = vocab.to_proposals()
    assert proposal["proposal_id"] == lbl.proposal_id


def test_merge_keeps_target_identity():
    vocab = LabelVocabulary()
    target = Label(name="Cooking", seed_note_ids=["1", "2"])
    source = Label(name="Recipes", seed_note_ids=["3", "4", "5"])
    vocab.add(target)
    vocab.add(source)

    CategorizationService._apply_merge_map(
        vocab, {"merges": [{"into": "Cooking", "from": ["Recipes"]}]}
    )

    (merged,) = vocab.labels
    assert merged.name == "Cooking"
    # The surviving card keeps the target's identity even though the source
    # was larger — a staged decision on "Cooking" must stay attached.
    assert merged.proposal_id == target.proposal_id
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_label_identity.py -q`
Expected: FAIL — `Label` has no field `proposal_id`.

- [ ] **Step 3: Implement**

`app/models/label.py`: add `import uuid` and, on `Label`:

```python
    # Stable identity for one proposal card across streaming, consolidation and the
    # final frame. Tag names are NOT unique (the LLM can name two clusters alike), so
    # nothing that routes a user's click may key on the name.
    proposal_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
```

`to_proposals()`: add `"proposal_id": lbl.proposal_id,` to the dict.

`categorization_service.py` streamed frame (~1142): add `"proposal_id": lbl.proposal_id,` to the inline `"proposal"` dict.

`_apply_merge_map` (~355): capture the target label before building the merged one —
`target_label = prop_map.get(into_sanitized)` is popped into `constituents`; keep a reference first, then construct `merged_prop = Label(..., proposal_id=(target_label.proposal_id if target_label is not None else largest.proposal_id))`. Read the surrounding code and thread it through the actual variable names there (`constituents.append(prop_map.pop(into_sanitized))` — take the reference at that point).

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_label_identity.py tests/test_categorization_service.py tests/test_merge_approval.py -q`
Expected: PASS (existing merge tests unaffected — the field has a default).

- [ ] **Step 5: Commit**

```bash
git add app/models/label.py app/services/categorization_service.py tests/test_label_identity.py
git commit -m "feat(categorize): give every proposal a stable proposal_id"
```

---

### Task 2: Unique names at stream time

Collisions are currently repaired only at the end (`_deduplicate_name` pass at ~line 1403), after every streamed card was already shown. Dedupe as names are assigned in the naming loop, so no two identical cards ever stream, and consolidation only ever sees unique names.

**Files:**

- Modify: `app/services/categorization_service.py` (naming loop, ~lines 1072–1126)
- Test: `tests/test_pipeline.py` (extend) or `tests/test_stream_name_dedup.py` (create) — implementer's choice, model on the existing stream-contract tests in `tests/test_pipeline.py`

**Interfaces:**

- Consumes: `self._deduplicate_name(name, seen)` (~line 1833) — existing suffixing helper (`Topic`, `Topic 2`, …).
- Produces: within one run, every non-`DROP_ME` label name is unique **at the moment its `proposal` frame is emitted**. The end-of-run `_deduplicate_name` pass at ~1403 stays as a safety net (it is idempotent on already-unique names).

- [ ] **Step 1: Write the failing regression test**

The doc's backend regression test: a `categorize` run whose LLM returns the same name for every cluster emits **unique** `tag_name`s (and unique `proposal_id`s) in its streamed `proposal` frames. Model the harness on `tests/test_pipeline.py`'s stream-contract tests: stubbed SearchService with synthetic embeddings that form ≥2 clusters, stub LLM whose `complete_with_tools`/`complete` always answers `Topic`. Collect frames from the `categorize` stream; assert:

```python
proposal_frames = [f for f in frames if f["type"] == "proposal"]
names = [f["proposal"]["tag_name"] for f in proposal_frames]
ids = [f["proposal"]["proposal_id"] for f in proposal_frames]
assert len(proposal_frames) >= 2, "need a collision to test dedup"
assert len(set(names)) == len(names), f"streamed duplicate names: {names}"
assert len(set(ids)) == len(ids)
```

If the existing harness in `tests/test_pipeline.py` already streams a multi-cluster run, extend it; otherwise create the new file reusing its stubs. Synthetic notes only.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest <the test file> -q`
Expected: FAIL — duplicate `Topic` names in streamed frames.

- [ ] **Step 3: Implement**

In the naming loop (the `for i, (lbl, n_text, kw_str, neighbor_kw, reused_tag) in enumerate(llm_tasks):` block): initialize `stream_seen: Dict[str, int] = {}` before the loop; after `lbl.name` is finally assigned for this iteration (all three branches: manifest reuse, LLM name, keyword fallback) and is not `DROP_ME`, apply `lbl.name = self._deduplicate_name(lbl.name, stream_seen)` **before** the `proposal` frame is emitted. Note the manifest-reuse branch (`lbl.name = reused_tag`) must go through the same dedup — that branch is exactly where re-runs collide (two clusters reusing the same manifest tag).

- [ ] **Step 4: Run tests**

Run: `uv run pytest <the test file> tests/test_pipeline.py tests/test_naming.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/categorization_service.py tests/
git commit -m "fix(categorize): dedupe cluster names before streaming, not after review"
```

---

### Task 3: Consolidation keyed on identity, not name

With Task 2, names reaching consolidation are unique — this task makes consolidation safe even if that invariant is ever violated (restored pre-fix state, future code paths), fixing the doc's Defect 2.

**Files:**

- Modify: `app/services/categorization_service.py` (`_apply_merge_map` ~line 289: `prop_map = {lbl.name: lbl}`; gray-zone union-find `merged_into = {lbl.name: lbl.name}` ~line 1163)
- Test: `tests/test_label_identity.py` (extend)

**Interfaces:**

- Consumes: `Label.proposal_id` (Task 1).
- Produces: `_apply_merge_map` keys its working map on `proposal_id`; LLM merge answers (which are names, by protocol) resolve name → labels via a name index; when a name maps to multiple labels (the violated-invariant case), that name is skipped for merging (log a structural count only) rather than silently collapsing labels. `vocab.labels` reconstruction preserves every label not explicitly merged. Same de-ambiguation for the gray-zone `merged_into` union-find: key on `proposal_id`, resolve names through the same guarded index.

- [ ] **Step 1: Write the failing test**

```python
def test_same_named_labels_survive_unrelated_merge():
    """Defect 2: a merge between OTHER tags must not drop same-named bystanders."""
    vocab = LabelVocabulary()
    topic_a = Label(name="Topic", seed_note_ids=["1"])
    topic_b = Label(name="Topic", seed_note_ids=["2"])
    cooking = Label(name="Cooking", seed_note_ids=["3"])
    recipes = Label(name="Recipes", seed_note_ids=["4"])
    for lbl in (topic_a, topic_b, cooking, recipes):
        vocab.add(lbl)

    CategorizationService._apply_merge_map(
        vocab, {"merges": [{"into": "Cooking", "from": ["Recipes"]}]}
    )

    ids = {lbl.proposal_id for lbl in vocab.labels}
    # Both Topics survive; only Recipes folded into Cooking.
    assert topic_a.proposal_id in ids and topic_b.proposal_id in ids
    assert len(vocab.labels) == 3
```

Also add: a merge whose `from` name is ambiguous (two labels named `Topic`, merge `{"into": "Cooking", "from": ["Topic"]}`) is skipped — all four labels survive.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_label_identity.py -q`
Expected: the first new test FAILS on current code — `prop_map = {lbl.name: lbl}` keeps only `topic_b`, and `vocab.labels = list(prop_map.values())` drops `topic_a` (per the doc, `categorization_service.py:281/:338`). If it unexpectedly passes, investigate before proceeding — do not skip to Step 3.

- [ ] **Step 3: Implement**

In `_apply_merge_map`: `prop_map: Dict[str, Label] = {lbl.proposal_id: lbl for lbl in vocab.labels}` plus `name_index: Dict[str, List[str]]` (name → list of proposal_ids). Resolve `into`/`from` names through `name_index`; a name resolving to != 1 id is skipped (count skips, print one structural line: number only, no names needed — but names here are tag names, not note content, so naming them is also acceptable). Pop/append by id; rebuild `vocab.labels = list(prop_map.values())` (now id-keyed, loses nothing). Mirror the same name→id guarded resolution in the gray-zone `merged_into` union-find block (~1163): key union-find nodes on `proposal_id`.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_label_identity.py tests/test_merge_approval.py tests/test_categorization_service.py tests/test_pipeline.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/categorization_service.py tests/test_label_identity.py
git commit -m "fix(categorize): key consolidation on proposal identity so same-named clusters survive"
```

---

### Task 4: Case-insensitive vault-tag reuse before sanitizing

`_sanitize_tag_name` turns a correctly-reused vault tag into a near-duplicate of itself (`iOS` → `Ios`) or drops it (`C#` → `''`). Match the LLM's answer against the vault list first and return the vault's own spelling on a hit.

**Files:**

- Modify: `app/services/categorization_service.py` (`_get_llm_tag_name`, which receives `existing_tags`; the sanitize call inside it)
- Test: `tests/test_naming.py` (extend — it already unit-tests the naming/sanitize behavior)

**Interfaces:**

- Consumes: `_get_llm_tag_name(..., existing_tags=...)` — find its exact signature and where the raw LLM answer meets `_sanitize_tag_name`.
- Produces: if the raw LLM answer (trimmed, and also its fence/JSON-unwrapped form — reuse the existing extraction so a wrapped answer still matches) equals an existing vault tag **case-insensitively**, return that vault tag verbatim, bypassing `_sanitize_tag_name`. Otherwise behavior is unchanged.

- [ ] **Step 1: Write the failing tests**

In `tests/test_naming.py`, following its existing test style (unit tests over the naming helpers — read the file's existing stubs for how `_get_llm_tag_name` is exercised; if it is only tested via `_sanitize_tag_name`, add a small async test with a stub LLM client the way `tests/test_pipeline.py` stubs one):

- LLM answers `'ios'`, vault contains `'iOS'` → result is exactly `'iOS'`.
- LLM answers `'C#'`, vault contains `'C#'` → result is exactly `'C#'` (today it sanitizes to `''` and falls back).
- LLM answers `'Gardening'`, vault contains `'iOS'` only → result is the sanitized `'Gardening'` (non-matching answers keep today's path).

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_naming.py -q`
Expected: the two vault-match tests FAIL (`Ios` / fallback instead of vault spelling).

- [ ] **Step 3: Implement**

In `_get_llm_tag_name`, immediately before the sanitize step: build `vault_by_casefold = {t.casefold(): t for t in (existing_tags or [])}`; check the raw answer's trimmed form and its unwrapped/extracted form against it; on hit, return the vault spelling. Keep the denylist check downstream operating on the returned name as today (a vault tag named `Misc` would be caught by the caller's denylist — acceptable and unchanged).

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_naming.py tests/test_pipeline.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/categorization_service.py tests/test_naming.py
git commit -m "fix(categorize): reuse vault tags with their own spelling instead of sanitizing them apart"
```

---

### Task 5: Frontend — stage decisions against `proposal_id`

Fixes the reported symptom directly: clicking accept/discard on a duplicate-named card staged the **first** same-named card (`resolveById` `findIndex` on `tag_name`), or nothing visible. Five sites key on the name; all move to `proposal_id`, with name fallback only for pending sets persisted before this fix — and restored sets get synthetic ids so even an already-broken saved set becomes individually clickable.

**Files:**

- Modify: `client/src/types/index.ts` (Proposal type gains `proposal_id?: string`)
- Modify: `client/src/hooks/useOrganize.ts` (`resolveById` ~441, `toActionsMap` ~144, `reattachActions` ~225, `mergeProposals` ~500, `restorePending` ~239, staged-actions bookkeeping)
- Modify: `client/src/components/Organize/ProposalCard.tsx` (`cardId` ~75)
- Modify: `client/src/components/Organize/ProposalDashboard.tsx` (React `key` ~125)
- Test: `client/src/hooks/__tests__/useOrganize.duplicates.test.ts` (create)

**Interfaces:**

- Consumes: backend frames now carry `proposal_id` (Tasks 1–2).
- Produces:

  - `Proposal.proposal_id?: string` (optional — restored pre-fix sets lack it).
  - A single helper in `useOrganize.ts`: `const proposalKey = (p: Proposal): string | undefined => p.proposal_id ?? p.tag_name;` — every identity comparison goes through it.
  - `resolveById(states, id)`: string ids match `proposalKey(s.proposal) === id` first, then the existing name/index fallbacks (restored old sets, dashboard cards) — order guarantees an id match always wins.
  - `ProposalCard`'s `cardId` = `proposal.proposal_id ?? proposal.tag_name ?? index`.
  - `ProposalDashboard` React `key` prefers `p.proposal_id` over the current name-based key.
  - `mergeProposals(sourceId, targetId)` operates on `proposalKey` matches (single card each), not `.map` over name matches. Check its call sites for what they pass and update them to pass the card id.
  - Staged actions: the internal `stagedActionsRef` map keys on `proposalKey`; **`toActionsMap` converts to the server's name-keyed contract at the PUT boundary** (id → `s.proposal.tag_name`), skipping info proposals exactly as today. Names are unique per run after Task 2, so the name-keyed lock stays unambiguous.
  - `reattachActions(fresh, staged)`: match staged decisions to fresh (final-frame) proposals by `proposal_id` first, falling back to `tag_name` for pre-fix persisted sets.
  - `restorePending`: after fetching, assign synthetic ids to any proposal lacking one — `proposal_id: p.proposal_id ?? \`restored-${index}\`` — so even an old duplicate-named pending set becomes individually addressable. (Staged actions restored from the server are name-keyed; reattach them by name as today — that ambiguity is inherent to old sets and harmless once new decisions are id-keyed.)

- [ ] **Step 1: Write the failing tests**

`client/src/hooks/__tests__/useOrganize.duplicates.test.ts` — this is the doc's frontend regression test. Model the setup on existing hook tests (`renderHook`, mock `fetch`). Drive the hook to hold two same-named proposals with distinct `proposal_id`s (the cleanest path: mock `fetch` for `API_ROUTES.ORGANIZE_PENDING` to return `{ proposals: [ {tag_name: 'Topic', proposal_id: 'a', note_ids: [], note_count: 1, sample_notes: [], confidence: 0.5}, {tag_name: 'Topic', proposal_id: 'b', ...} ], actions: {} }` and let `restorePending` load them). Then:

- `approveProposal('b')` → the state whose `proposal.proposal_id === 'b'` has `action: 'approve'`; the `'a'` card stays `'pending'`. Asserted on identity, not name or position.
- A restored set **without** ids (`proposals: [{tag_name: 'Topic', ...}, {tag_name: 'Topic', ...}]`) gets distinct synthetic ids, and approving the second card's key stages only the second.
- The PUT body sent to `API_ROUTES.ORGANIZE_PENDING_ACTIONS` (capture the debounced `fetch` call; use `vi.useFakeTimers` to flush the 400 ms debounce) is keyed by **tag name** — the server contract is unchanged.

Find the exact route constants and the hook's state accessors by reading `useOrganize.ts` first; assert through the hook's public return values (`proposals` array of `ProposalState`).

- [ ] **Step 2: Run to verify failure**

Run: `cd client && npx vitest run src/hooks/__tests__/useOrganize.duplicates.test.ts`
Expected: FAIL — approving `'b'` stages the first `'Topic'` (findIndex by name), and no synthetic ids exist.

- [ ] **Step 3: Implement**

Apply the Interfaces block above. Keep the existing dashboard-card index resolution in `resolveById` untouched (info/merge/assign cards still pass numeric indexes). Update every caller that builds a card identifier (`ProposalCard.tsx:75` and the handlers it feeds: approve/reject/rename/merge plumbing) to the new `cardId`. Read each touched function fully before editing — the hook is ~600 lines and the staging flow (`stageDecision`, `stagedActionsRef`, debounce) must keep its current shape.

- [ ] **Step 4: Run the frontend suite**

Run: `cd client && npx vitest run && npx tsc --noEmit && npm run lint`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add client/src
git commit -m "fix(organize): stage review decisions by proposal identity, not tag name"
```

---

### Task 6: Full verification + doc update

**Files:**

- Modify: `docs/feature-ideas/scoped-retagging-and-replacement.md` (Part 2 status)

- [ ] **Step 1: Run everything**

`uv run pytest tests/ -q` and `cd client && npx vitest run && npx tsc --noEmit && npm run lint && npm run build`.
Expected: all green; fix anything broken before proceeding.

- [ ] **Step 2: Update the doc**

In the feature-ideas doc, update the **Status** header line: Part 2 defects fixed (date, commit range), Part 1 still an idea. Do not rewrite the diagnosis — it documents why the code looks the way it does; add a short "Fixed 2026-07-30" note at the top of Part 2 listing the four fixes.

- [ ] **Step 3: Commit**

```bash
git add docs/feature-ideas/scoped-retagging-and-replacement.md
git commit -m "docs: mark the re-run categorization defects as fixed"
```
