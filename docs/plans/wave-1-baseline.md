# Wave 1 — Baseline (SERIAL, 1 agent)

Not parallel: T01 reformats 17 files across `app/`, which would collide with every other lane. It
must land alone, first, so no later task fights the formatter. Total ≈ ½ day.

---

## T01 — Formatting baseline + `make check` / `make format` split

**Fixes:** H2 · the 2 committed eslint errors · 17 black-unformatted + 6 isort-unsorted files.

**Owns:** every file (formatting changes only), `Makefile`, `.pre-commit-config.yaml`.
The `Makefile` is the one file this task may change non-mechanically (steps 3 and 5).

**Do**
1. `uv run black app tests && uv run isort app tests` — mechanical, no logic changes.
2. `cd client && npx eslint . --fix`, then hand-fix what remains in
   `client/src/components/Chat/ChatMessage.tsx` (missing `{}` after `if` at :67; prettier at :145).
3. Split the Makefile target that currently mutates code:
   - `make format` → black, isort, `npm run fix` (write mode — what `make lint` does today).
   - `make check` → `black --check`, `isort --check-only`, `eslint .`, `tsc -b`, `pytest`,
     `vitest run`. Non-mutating, non-zero exit on any failure.
   - keep `make lint` as an alias of `make check` so existing habits fail loudly instead of silently
     rewriting files.
4. Add a `setup` step that runs `pre-commit install`, and note it in the README dev section.
5. Add exactly one line to the `Makefile`: `-include bench/bench.mk`. Wave 1 owns the `Makefile`, and
   Wave 3's Lane T owns `bench/bench.mk`, so this hook is what lets Lane T ship `make bench*` targets
   without two lanes editing the same file (`EXECUTION-PROTOCOL.md` §2.5). The leading `-` makes it a
   no-op until that file exists, so it is inert in this commit — verify `make check` still works.

**Do not** change any logic, rename anything, or "tidy up while in there". A reviewer must be able to
verify this commit with `git show --stat` plus a re-run of the formatters.

**Checkpoint**
```
make check          # exits 0
git stash && make format && git diff --exit-code    # exits 0 (formatters are idempotent)
```

**Commit:** `chore: formatting baseline and non-mutating make check`

---

## T02 — CI workflow + fix the 3 red tests

**Fixes:** H1, B9. **Depends on:** T01.

**Owns:** `.github/workflows/ci.yml` (new), `tests/test_coverage.py`, `tests/test_decision.py`.

**Do**
1. `.github/workflows/ci.yml` — on push + PR, single job, Ubuntu:
   - `astral-sh/setup-uv`, `uv sync --all-groups`; `actions/setup-node` with node 20
     (`client/package.json` requires `>=20.19.0`), `npm ci` in `client/`.
   - run `make check` with `GOOGLE_KEEP_PATH=.` in the env.
   - cache the uv and npm stores; keep total runtime under ~5 min. Torch cu121 is the long pole — if
     the wheel download dominates, cache `~/.cache/uv` aggressively and note the runtime in the
     commit body rather than switching to CPU wheels (that is T32's call, not this task's).
2. Fix the three failures. They are **constant drift, not logic bugs** — `app/services/agent/constants.py`
   moved `QUERY_MAX_CHARS` 200→500, `MAX_QUERIES_PER_STEP` 3→5, and `MAX_COLLECTED_NOTES`, while the
   tests still assert the old numbers:
   - `test_decision.py::test_search_decision_rejects_over_long_query`
   - `test_decision.py::test_search_decision_rejects_more_than_3_distinct_queries`
   - `test_coverage.py::test_coverage_note_limit_stop`

   Import the constants and assert **relative to them** (`"a" * (QUERY_MAX_CHARS + 1)`,
   `MAX_QUERIES_PER_STEP + 1` queries, `MAX_COLLECTED_NOTES` collected embeddings) so the next
   constant change cannot silently re-break them. Do not change the constants to match the tests.

**Checkpoint**
```
GOOGLE_KEEP_PATH=. uv run pytest -q     # 0 failed; the 3 previously-red tests now pass, count otherwise unchanged
make check                              # exits 0
```
Plus: CI green on the branch — paste the run URL in the commit body.

**Commit:** `ci: add pipeline and fix constant-drift test failures`
