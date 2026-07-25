# Resume checkpoint — audit remediation plan

**Paste this file's contents to a fresh agent to resume the plan.** It is written for someone with
none of the originating conversation's context.

**Last updated:** 2026-07-25, at the wave-4 barrier · `HEAD` = `24ff6d8` · **resume at wave 5**.

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

Waves 1–4 complete (26 task commits + 7 orchestrator commits), tree clean, branch `master`:

```
24ff6d8 chore(plan): complete Wave 4 barrier and remove wave-4-deprecations spec      <- HEAD
cb73ef5 refactor(chat): single agentic path, remove the legacy mode flag (T20)
150bcc3 refactor(agent): retrieve through the shared orchestrator (T19)
56f3b48 refactor: delete unused AgentTools and repair doc references (T17, T18)
6e3d546 refactor(chat): drop the no-op topic input for tag and date scoping (T16)
ba80742 refactor: remove KMeans clusters tab, colour the 3D map by tag (T15)
031d05a chore(plan): complete Wave 3 barrier and remove wave-3-safety-net spec
2addd76 test: privacy-safe categorization eval and fix the make eval target (T14)
```

T01–T20, T33, T35, T36 are `done` in § Task index and § Status. Waves 5–7 untouched.
**Nothing has ever been pushed** — `origin/master` is still at `6dab505`.

Barrier gate on a clean tree: `GOOGLE_KEEP_PATH=. make check` → **exit 0**, 220 pytest passed
(181 at wave 1 start), 11 vitest files / 57 tests, eslint 0 errors (2 pre-existing warnings in
`GalleryContext.tsx`, `ImageGallery/index.tsx`), tsc clean. PLANS.md invariants: overlaps 0,
46 findings none unowned.

## Next steps, in order

1. Read `wave-5-store.md` (lanes L1–L6) and `EXECUTION-PROTOCOL.md` §1.3 for rounds.
   **Round 1 = T21 SERIAL (Lane L1 — Domain model)**.
   **Round 2 = T22 (Lane L2 — SQLite store + mmapped vector store) · T23 (Lane L3 — Importer protocol)**.
   **Round 3 = T24 (Lane L4 — Ingest API) · T25 (Lane L5 — Index apply)**.
   **Round 4 = T26 SERIAL (Lane L6 — Cutover)**.
2. Dispatch Round 1 using the concurrency protocol below.
3. At the wave-5 barrier (after T26): run `make check` yourself, flip § Status, re-run both § Verification
   scripts, refresh this file, **delete `wave-5-store.md` in the barrier commit**, then **stop and report**.
   The owner wants a barrier stop before each new wave.

## The concurrency protocol — brief every lane agent with this

All lanes share ONE working tree. Lane ownership makes their *edits* disjoint but **not** their
*verification*. These rules worked in waves 2, 3 & 4; reuse them verbatim.

- Edit only files in the task's `Owns:` list; read anything.
- During development run ONLY the task's own targeted tests. **Never `make check`** — it would pick
  up siblings' half-finished edits and produce meaningless failures.
- **Also require a non-mutating `uv run black --check` / `uv run isort --check-only` on owned files,
  named explicitly, before reporting ready.**
- Phase 1 ends with the agent reporting `READY FOR GATE` and **stopping**. It does not commit.
- Wait until **all** lanes in the round report ready, then run `make check` yourself over the
  combined tree, then hand out **COMMIT TOKENS one at a time** via SendMessage. Only the token
  holder runs `make check` and commits.
- An agent hitting a red gate **outside its write set** must report and stop. It is explicitly
  forbidden from judging or fixing it. The driver adjudicates — `git status` maps dirty paths to
  lanes.
- Stage explicit paths only. Never `git add -A`/`.`/`-a`; never stash/restore/checkout/reset/clean/
  amend.
- Agents touch `PLANS.md` only in the commit phase, and only their own § Task index row. **They leave § Status alone; the driver flips it.**
- Commit message first line = the spec's `Commit:` line verbatim. **No trailers.** One task = one
  commit, straight to `master`.
- **NEVER push**, in any lane, ever.

## Decisions & constraints

- **Local-only, never push.** Publishing is the owner's decision at the end of the plan, and a leak
  audit is a mandatory precondition of any push — now T37's job.
- **§5 config is frozen for lanes:** no new env vars, no `.env`/`.env.example` edits. New tuning
  values are hardcoded constants in the relevant `constants.py` with a one-line trade-off comment.
- **LLM egress is local:** `llm_provider=openai` but `api_base=http://localhost:1234/v1`
  (LM Studio), so notes never leave the machine.
- **`github.com/Harduex/deep-semantic-search` is NOT adopted** (owner decision, 2026-07-25).
- **The owner may read `.env`; agents may not.** Use the config object.

## Key locations & commands

- `PLANS.md` — wave graph, ownership matrix, § Task index (State column), § Status.
- `EXECUTION-PROTOCOL.md` — §1.3 dispatch rounds, §2 ownership, §3 commits + wave-file deletion policy, §4 gates.
- Remaining specs: `wave-5-store.md`, `wave-6-unify-and-quality.md`, `wave-7-release-readiness.md`. Waves 1–4 files are deleted (policy).
- Gate: `GOOGLE_KEEP_PATH=. make check`.
