# Resume checkpoint — audit remediation plan

**Paste this file's contents to a fresh agent to resume the plan.** It is written for someone with
none of the originating conversation's context.

**Last updated:** 2026-07-25, at the wave-2 barrier · `HEAD` = `3a26cb5` · **resume at wave 3**.

> Keep this current: refresh it at every wave barrier, in the barrier commit, alongside the
> `PLANS.md` § Status update. A stale resume file is worse than none — it will confidently point the
> next session at work that is already done.

---

## Goal

Execute the 37-task plan in `PLANS.md`, which remediates 46 findings from
`docs/audit/SYSTEM-OVERVIEW.md` and re-architects storage/ingestion. The driver dispatches one
subagent per lane, polices lane ownership, adjudicates blockers, and gates every commit.
`EXECUTION-PROTOCOL.md` is binding on the driver and on every agent — read it first.
Precedence: `AGENTS.md` > EXECUTION-PROTOCOL > wave file > PLANS.md.

## State

Waves 1–2 complete (13 task commits + 4 orchestrator commits), tree clean, branch `master`:

```
3a26cb5 docs(plans): retire the wave 1 and 2 spec files      <- HEAD
6bd0c24 docs(plans): close wave 2 and add wave 7
e0e1710 T09 merge proposal actually merges
46b3429 T05 BM25 inverted index + precompute
c4ced8a T07 seed tags from labels, enforce exclusions
859f857 T03 chat pipeline (B1 B5 B6 B7 B11)
7fa5ee9 chore(agents): drop duplicated .claude files (owner-initiated)
d0697d0 T08 path traversal
64a45c4 T06 parser list content + labels
440a3c7 T10 privacy redaction (new app/core/redact.py)
1894243 T04 reranker window
1c6859e fix(build): nvm prelude no-op when nvm absent
9921a8d docs(plans): close wave 1
e6f09ad T02 CI workflow + constant-drift tests
49420b8 T01 formatting baseline + make check/format split
```

T01–T10 are `done` in § Task index and § Status. Waves 3–7 untouched.
**Nothing has ever been pushed** — `origin/master` is still at `6dab505`, ~17 commits behind.

Barrier gate on a clean tree: `GOOGLE_KEEP_PATH=. make check` → **exit 0**, 216 pytest passed
(181 at wave 1 start), 9 vitest files / 45 tests, eslint 0 errors (2 pre-existing warnings in
`GalleryContext.tsx`, `ImageGallery/index.tsx`), tsc clean. PLANS.md invariants: overlaps 0,
46 findings none unowned.

## Next steps, in order

1. Read `wave-3-safety-net.md` (lanes F, G, R, T) and `EXECUTION-PROTOCOL.md` §1.3 for rounds.
   **Round 1 = T11 · T33 · T35, and T11 must run ALONE** — it creates `tests/conftest.py` plus the
   synthetic fixture corpus everything later imports. Round 2 = T12 · T13 · T36. Round 3 = T14.
2. Dispatch round 1 using the concurrency protocol below.
3. At the wave-3 barrier: run `make check` yourself, flip § Status, re-run both § Verification
   scripts, refresh this file, **delete `wave-3-safety-net.md` in the barrier commit**
   (EXECUTION-PROTOCOL §3 — grep for the filename first, see Gotchas), then **stop and report**.
   The owner wants a barrier stop before each new wave.

## The concurrency protocol — brief every lane agent with this

All lanes share ONE working tree. Lane ownership makes their *edits* disjoint but **not** their
*verification*. These rules worked in wave 2; reuse them verbatim.

- Edit only files in the task's `Owns:` list; read anything.
- During development run ONLY the task's own targeted tests. **Never `make check`** — it would pick
  up siblings' half-finished edits and produce meaningless failures.
- **Also require a non-mutating `uv run black --check` / `uv run isort --check-only` on owned files,
  named explicitly, before reporting ready.** Two wave-2 lanes tripped the formatting stage because
  this was missing: formatting is otherwise only checked inside `make check`, which they are barred
  from, so they had no sanctioned way to discover it.
- Phase 1 ends with the agent reporting `READY FOR GATE` and **stopping**. It does not commit.
- Wait until **all** lanes in the round report ready, then run `make check` yourself over the
  combined tree, then hand out **COMMIT TOKENS one at a time** via SendMessage. Only the token
  holder runs `make check` and commits.
- An agent hitting a red gate **outside its write set** must report and stop. It is explicitly
  forbidden from judging or fixing it. The driver adjudicates — `git status` maps dirty paths to
  lanes. This is what stops "that's another lane's breakage" from becoming a rationalisation.
- Stage explicit paths only. Never `git add -A`/`.`/`-a`; never stash/restore/checkout/reset/clean/
  amend. **A pre-existing `stash@{0}` "On notes-tagging" belongs to the owner — never touch the
  stash list.**
- Agents touch `PLANS.md` only in the commit phase, and only their own § Task index row — this
  removes the status-file race entirely. **They leave § Status alone; the driver flips it.**
- Commit message first line = the spec's `Commit:` line verbatim. **No trailers.** One task = one
  commit, straight to `master`.
- **NEVER push**, in any lane, ever.

## Decisions & constraints

- **Local-only, never push.** Publishing is the owner's decision at the end of the plan, and a leak
  audit is a mandatory precondition of any push — now T37's job.
- **T02's CI-green checkpoint is recorded as pending, not passed.** `ci.yml` has never run on a
  runner. Never invent a run URL.
- **§5 config is frozen for lanes:** no new env vars, no `.env`/`.env.example` edits. New tuning
  values are hardcoded constants in the relevant `constants.py` with a one-line trade-off comment.
- **The owner changed runtime config mid-wave-2:** `CHAT_CONTEXT_NOTES` 250 → **20**,
  `AGENT_MAX_STEPS` 50 → **8**. This matters: T03 fixed B7, so `AGENT_MAX_STEPS` now actually takes
  effect (previously ignored — the function default of 5 always won). At 50 it would have turned a
  5-step agent loop into a 50-step one. B6's context cap is effective for the first time
  (20 < `MAX_COLLECTED_NOTES=250`).
- **LLM egress is local:** `llm_provider=openai` but `api_base=http://localhost:1234/v1`
  (LM Studio), so notes never leave the machine. Fragile — with the `openai/` prefix, clearing
  `LLM_API_BASE_URL` would fall back to api.openai.com and take every note in the prompt with it.
  Nothing asserts the base URL is loopback.
- **`github.com/Harduex/deep-semantic-search` is NOT adopted** (owner decision, 2026-07-25). Do not
  propose swapping it in — it would replace much of what waves 5–6 restructure.
- **Two ownership-gap rulings already made** (§2.5, "matrix gap, not a violation", on the basis that
  no sibling lane owned the path): Lane B owns `app/services/search/constants.py` (created by T04);
  Lane C was authorised to extend `DummyNoteService` in `tests/test_ready_route.py`. Both recorded
  in § Proposed follow-ups; the matrix still needs a fixing pass.
- **The owner may read `.env`; agents may not.** Use the config object:
  `GOOGLE_KEEP_PATH=. uv run python -c "from app.core.config import settings as s; print(s.chat_context_notes)"`.
  `.env` is also covered by a permission deny rule, so Read/Bash against it fails regardless.
- **Briefing discipline: require agents to name the source they actually observed.** T03 wrote "this
  machine's `.env` sets CHAT_CONTEXT_NOTES to 250" having only read `settings.chat_context_notes` —
  an attribution overclaim, not a boundary breach, but the kind that erodes trust in reports.

## Key locations & commands

- `PLANS.md` — wave graph, ownership matrix, § Task index (State column), § Status,
  § Proposed follow-ups (11 entries), § Verification (2 invariant scripts, re-run after editing).
- `EXECUTION-PROTOCOL.md` — §1.3 dispatch rounds, §2 ownership, §3 commits + wave-file deletion
  policy, §4 gates and the two-tier measurement rule, §5 frozen config, §6 privacy, §7 no scope
  creep, §8 reporting.
- Remaining specs: `wave-3-safety-net.md`, `wave-4-deprecations.md`, `wave-5-store.md`,
  `wave-6-unify-and-quality.md`, `wave-7-release-readiness.md`. Waves 1–2 files are deleted (policy).
- `23-live-acceptance-signoff.md` is superseded; T18 deletes it.
- Gate: `GOOGLE_KEEP_PATH=. make check` — black --check, isort --check-only, eslint, tsc -b, pytest,
  vitest. Non-mutating, ~2 min. `make format` is the mutating one; `make lint` aliases `make check`.
  Never use a mutating target to satisfy a gate.
- `app/core/redact.py` (from T10) — `safe_exc(e)` (type + status only, never the message) and
  `safe_meta(**kw)`. The sanctioned way to log anything LLM-adjacent.

## Gotchas learned in waves 1–2

- **`lifespan.py` is a startup choke point that defeats the ownership matrix.** T07 added
  `note_service.seed_tags_from_labels()` and broke `tests/test_ready_route.py` — a file **no**
  wave-2 lane owned. Every lane's targeted tests passed and the combined gate still went red.
  Expect a repeat in wave 5 (L6/T26 owns `lifespan.py`). `DummyNoteService` there is the only
  `NoteService` double that drives the real lifespan; T07 verified this exhaustively.
- **Grep for a wave file's name before deleting it.** `app/parser.py`'s `compute_notes_hash`
  docstring cited `docs/plans/wave-2-bug-sweep.md`; it was rewritten to stand alone in the same
  commit rather than left dangling.
- **Docstrings are AST nodes.** T37's checkpoint originally asserted plain AST-identity and failed
  on a legitimate docstring edit; it now blanks docstrings on both sides first. Any "is this
  comment-only?" check needs the same treatment.
- **`node` is not on PATH in non-interactive shells here** — the Makefile's `NVM_SOURCE` prelude
  supplies it. Raw `npx vitest` outside `make` can fail with node v22.9.0 against jsdom's
  `engines: ^22.12.0`; `nvm use v20.20.2` fixes it. `1c6859e` made the prelude a no-op when nvm is
  absent (it previously returned exit 1 and failed the recipe line before npm ever ran).
- **"Fixed but inert" is a real failure mode here.** Both B5 and B6 landed green while doing nothing
  in production. B5 only went live because T07 named the attribute exactly `note_service`, which
  `ChatService._tag_lookup()` resolves via
  `getattr(self.retrieval.search_service, "note_service", None)`. Watch for a green suite proving a
  fix that production never reaches.
- **Verify agent claims — they are mostly excellent but not uniformly accurate.** T03 caught a stale
  test-count baseline the driver was carrying (198 committed vs 207 in-tree); T04 correctly rejected
  a formatting claim the driver mis-attributed to it. Cheap, high-value checks: `git show --stat`,
  grep for trailers, AST-compare for "formatting/comment only" claims, and re-run the checkpoint.

## Open items

- **`make check` exits 0 but CI has never run.** T02's workflow pins `actions/checkout@v7`,
  `actions/setup-node@v7`, `astral-sh/setup-uv@c771a70` (verified = tag v9.0.0). The nvm blocker
  that would have failed it is fixed, but green CI is unproven.
- **§ Proposed follow-ups has 11 entries**, notably: ~11 remaining LLM-adjacent `str(e)` sites
  across 8 files (several stream raw provider exceptions to the browser — the same P1 class T10
  fixed), queued as **one** dedicated task rather than piecemeal cross-lane edits; `rank-bm25`
  possibly a dead dependency (T32 owns `pyproject.toml`); `pre-commit` invoked by `make setup` but
  never declared as a dependency.
- **Wave 4's T19 parity gate is a stop-and-report gate**, and two-tiered: it needs
  `make eval-retrieval` (T13) **and** `bench/run_retrieval.py` (T36) in both modes. If agent mode
  does not match or beat legacy on **both** the golden set and the real-corpus bench, **do not start
  T20**. Do not rationalise past it.
- **Two checkpoints must be run by the owner, not an agent** (§6): T26's
  `scripts/migrate_to_store.py --dry-run` over a copy of the real cache dir, and T32's
  `docker compose` bring-up. An agent prepares them and stops.
- **T18 note:** the owner deliberately deleted `.claude/agents/{explore,test-writer}.md` and
  `.claude/rules/{python,typescript}.md` (committed in `7fa5ee9`). This pre-empts T18 step 3
  (collapse the duplicated instruction pairs, finding H4) — `.github/instructions/*` is the
  surviving canonical copy. T18 must **not** report them missing or restore them.
- **Model assignment the owner chose:** Sonnet for mechanical, well-specified tasks; Opus for T27
  (tagging merge), T22/T24/T25/T26 (store), T19/T20 (parity gate + legacy deletion), plus T03, T10
  and T37. Dispatch via the Agent tool — it has **no** effort parameter, so lanes inherit the
  session's effort. Keep the session at medium or above for anything touching the privacy boundary
  or a parity gate.
