# Resume checkpoint — audit remediation plan

**Paste this file's contents to a fresh agent to resume the plan.** It is written for someone with
none of the originating conversation's context.

**Last updated:** 2026-07-25, at the wave-3 barrier · `HEAD` = `031d05a` · **resume at wave 4**.

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

Waves 1–3 complete (20 task commits + 5 orchestrator commits), tree clean, branch `master`:

```
031d05a chore(plan): complete Wave 3 barrier and remove wave-3-safety-net spec      <- HEAD
2addd76 test: privacy-safe categorization eval and fix the make eval target (T14)
b041f9a test(bench): signal ablation, tagging correctness, and baseline regression gate (T36)
1a1f168 test: retrieval eval harness with golden query set (T13)
3bf8221 test: end-to-end API integration coverage for the wave-2 fixes (T12)
0afe107 test(bench): real-corpus loaders, scale generator, and shared metrics (T35)
dc36b16 test(client): cover the chat and organize NDJSON stream parsers (T33)
d33dc33 test: synthetic fixture corpus and deterministic model stubs (T11)
3a26cb5 docs(plans): retire the wave 1 and 2 spec files
```

T01–T14, T33, T35, T36 are `done` in § Task index and § Status. Waves 4–7 untouched.
**Nothing has ever been pushed** — `origin/master` is still at `6dab505`.

Barrier gate on a clean tree: `GOOGLE_KEEP_PATH=. make check` → **exit 0**, 227 pytest passed
(181 at wave 1 start), 11 vitest files / 57 tests, eslint 0 errors (2 pre-existing warnings in
`GalleryContext.tsx`, `ImageGallery/index.tsx`), tsc clean. PLANS.md invariants: overlaps 0,
46 findings none unowned.

## Next steps, in order

1. Read `wave-4-deprecations.md` (lanes H, I, J, K) and `EXECUTION-PROTOCOL.md` §1.3 for rounds.
   **Round 1 = T15 (Lane H), T16 (Lane I), T17 (Lane J), T18 (Lane J), T19 (Lane K)**.
   **Round 2 = T20 (Lane K)** — depends on T19 parity gate passing.
2. Dispatch Round 1 using the concurrency protocol below.
3. At the wave-4 barrier (after T20): run `make check` yourself, flip § Status, re-run both § Verification
   scripts, refresh this file, **delete `wave-4-deprecations.md` in the barrier commit**, then **stop and report**.
   The owner wants a barrier stop before each new wave.

## The concurrency protocol — brief every lane agent with this

All lanes share ONE working tree. Lane ownership makes their *edits* disjoint but **not** their
*verification*. These rules worked in waves 2 & 3; reuse them verbatim.

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
- Remaining specs: `wave-4-deprecations.md`, `wave-5-store.md`, `wave-6-unify-and-quality.md`, `wave-7-release-readiness.md`. Waves 1–3 files are deleted (policy).
- Gate: `GOOGLE_KEEP_PATH=. make check`.
