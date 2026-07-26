# Wave 8 — Release (SERIAL, 1 agent, two tasks in order)

Not parallel, and deliberately last: T37 sweeps **every** file for comment hygiene and audits **every**
unpushed commit, so it must observe the finished state of waves 1–7. It is the mirror image of T01 —
that task opened the plan with a mechanical sweep across all files (formatting only); this one closes
it with a mechanical sweep across all files (comments only) plus the gate that decides whether the
work is publishable. **T43 then rewrites the unpushed commit messages** and must run after T37 so it
can clean T37's own message too. Total ≈ 1 day.

**Was wave 7 until 2026-07-26**, renumbered when the pre-wave-6 audit turned four unowned follow-ups
into a real deployability wave (`wave-7-deployability.md`). Nothing about T37 changed; it just moved
back one place, because a comments-only AST-freeze over the whole repo has to observe the *final*
code, and wave 7 changes code.

**Added at the repo owner's request (2026-07-25; T43 on 2026-07-26), not derived from an audit
finding.** Neither task owns a `B*`/`A*`/`T*`/`H*`/`P*` id, so the coverage invariant in
`PLANS.md` § Verification is unaffected.

---

## T37 — Production-readiness comment sweep + pre-push safety audit

**Fixes:** — (owner request). **Depends on:** every task in waves 1–7.

**Owns:** every file (**comments only**), plus `docs/audit/PRE-PUSH-AUDIT.md` (new) and its own row in
`PLANS.md`. The comments-only restriction is what makes a whole-repo write set safe; see **Do not**.

### Do — Part 1: comment hygiene

Strip the plan's internal scaffolding out of the code, so a reader who has never seen `docs/plans/`
can still understand every comment.

1. **Remove plan coordinates.** Task codes (`T03`, `per T10`, `T24 replaces this`), wave and lane
   references, audit finding ids (`B5`, `P1`, `A9`) where they appear as bare cross-references, and
   any mention of orchestrator rulings or commit protocol. These are meaningless outside this plan.
2. **Keep the substance.** A comment explaining *what a value trades off* is load-bearing and stays —
   e.g. `RERANK_CANDIDATE_WINDOW`'s latency/recall note, and `MAX_VALUE_LEN`'s containment note in
   `app/core/redact.py`. Rewrite such comments to stand on their own reasoning rather than deleting
   them. The test is: would this sentence help a new contributor? Keep it. Does it only locate the
   change inside this plan? Cut it.
3. **Reconcile every task-code reference against whether that task actually shipped** — do not blanket
   delete. Some are deliberate records that have since gone stale, and a stale comment is worse than a
   noisy one because it is *false*. Known cases to check individually:
   - `app/parser.py` — `compute_notes_hash`'s note that list content is not yet hashed "until T24".
     T24 replaces the hashing scheme, so by this wave that sentence is either wrong or describes
     behaviour that no longer exists. Verify against the shipped code and rewrite or delete.
   - `app/services/agent/pydantic_agent.py` — `_log_agent_step`'s recorded decision that printing the
     user's question and generated probes is intentional. **The decision must survive**; only its task
     reference goes. Restate it as standalone rationale (user text, not note text; the debugging
     surface agent step-selection needs).
   - `app/core/redact.py` — module docstring citing findings P1–P3 and its originating task. Keep the
     *explanation* of why `str(e)` leaks note text, since that is the whole point of the module; drop
     the ids.
   - `app/services/search_service.py` — any comment describing it as the seam that "becomes the
     `Retriever` in Stage 4"; by this wave that either happened or did not.
4. **General production hygiene**, across `app/`, `tests/`, `scripts/`, `bench/` and `client/src/`:
   leftover debug `print`s, commented-out code, `TODO`/`FIXME` with no owner or no longer true,
   "for now" / "temporarily" hedges that misdescribe shipped behaviour, and comments that contradict
   the code beneath them. A `TODO` worth keeping becomes a line in `PLANS.md` § Proposed follow-ups
   instead.

**Do not** touch anything that is syntactically a comment but semantically code: `# type: ignore`,
`# noqa`, `# pragma: no cover`, `# fmt: off/on`, `eslint-disable`, `@ts-expect-error`, shebangs,
encoding declarations, licence headers, or docstrings that a test asserts on. Do not reword a
docstring that forms part of a public API contract. **No logic changes at all** — that is the
checkpoint.

### Do — Part 2: pre-push safety audit

Audit every commit not yet on the public remote, and produce a verdict. Use the
`git-ops:auditing-repo-for-leaks` skill if available; otherwise perform the equivalent manually and
say so.

Scope is `git log origin/master..HEAD` — **both diffs and commit messages**. Commit bodies are the
higher risk here: this plan required checkpoint evidence to be pasted into ~15 of them.

Check for:
1. **Note or prompt text** from the real corpus — the single most important category. Includes
   `Title: … / Snippet: …` shaped fragments and anything resembling `format_note_sample` output.
2. **Secrets** — API keys, tokens, passwords; any `.env` content; anything in a CI workflow that
   echoes a secret.
3. **PII and work identity** — personal or employer email addresses, real names beyond the repo
   owner's own git identity, third-party personal data.
4. **Machine-local absolute paths** — e.g. `/home/<user>/...` build paths. Several agents reported
   full paths during this plan; verify none reached a commit message or a source file.
5. **`cache/` or `$GOOGLE_KEEP_PATH` content**, in any form, including fixtures accidentally derived
   from real notes rather than authored synthetically.
6. **Binaries, DB dumps, model weights, `*.npz`, large files** committed by accident. Report anything
   over ~1 MB with a justification for why it belongs.
7. **`.gitignore` coverage** still holds for `cache/`, `*.log`, `.env`, `.venv`, `node_modules/`, and
   any `bench/corpora/` payloads that should not be redistributed.
8. **Redaction regression** — re-run the repo-wide equivalent of the guard added in wave 2: no
   `str(e)` / `repr(e)` / `traceback.print_exc()` on an LLM-adjacent path anywhere in `app/`, not just
   in the one file that originally leaked.

**When you find a leak, report its location — file, commit, line — and its category. Never quote the
offending content** into the report, the commit body, or your reply. That would move the leak rather
than fix it.

Write `docs/audit/PRE-PUSH-AUDIT.md`: per-finding severity, remediation for each, and a single
explicit verdict line — **SAFE TO PUBLISH** or **NOT SAFE TO PUBLISH** — with the commit range and
date it applies to. A finding that requires history rewriting (a secret in an old commit) must say so
plainly, since that is a different and heavier remedy than an edit.

### Do — Part 3: stop

**Never `git push`.** The repo is local-only by the owner's decision and publishing is theirs alone.
Deliver the verdict and stop. Do not offer to push; do not stage a push.

**Checkpoint**
```
# 1. comments only — no executable code changed anywhere (the load-bearing check)
#
# Docstrings are AST nodes, and this task legitimately rewrites some of them, so a
# naive ast.dump comparison reports a false failure. Blank every docstring on both
# sides first: what survives is executable code, which must be byte-identical.
python3 - <<'PY'
import ast, subprocess

def strip_docstrings(tree):
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = getattr(node, 'body', None)
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                and isinstance(body[0].value.value, str):
            body[0].value.value = ''
    return tree

files = subprocess.run(['git', 'diff', '--name-only', 'HEAD', '--', 'app', 'tests', 'scripts', 'bench'],
                       capture_output=True, text=True).stdout.split()
bad = []
for f in [f for f in files if f.endswith('.py')]:
    old = subprocess.run(['git', 'show', f'HEAD:{f}'], capture_output=True, text=True).stdout
    try:
        a = ast.dump(strip_docstrings(ast.parse(old)))
        b = ast.dump(strip_docstrings(ast.parse(open(f).read())))
    except SyntaxError:
        bad.append(f'{f} (syntax error)'); continue
    if a != b:
        bad.append(f)
print("executable code identical:", not bad, "| offenders:", bad or "none")
PY

# 2. no plan coordinates left in shipped code (review every hit; expect zero)
grep -rnE '\b(T0[1-9]|T[123][0-9])\b|\bwave [1-7]\b|\blane [A-Z]\b' app/ client/src/ scripts/ bench/ \
  --include='*.py' --include='*.ts' --include='*.tsx'

# 3. the floor still passes, unchanged
make check          # exits 0, same test counts as the previous commit

# 4. the audit exists and reaches a verdict
grep -E 'SAFE TO PUBLISH|NOT SAFE TO PUBLISH' docs/audit/PRE-PUSH-AUDIT.md
```
Check 1 is the one that matters: a comments-only sweep must leave every Python AST byte-identical. If
a file legitimately cannot satisfy it, that file is a logic change and does not belong in this task.
For `client/src/**`, `tsc -b` plus `vitest` inside `make check` is the equivalent guard.

State the test counts before and after in the commit body; they must be identical.

**Commit:** `chore(release): strip plan-internal comments and audit history for publish safety`

---

## T43 — Rewrite the unpushed commit messages for a public reader

**Fixes:** — (owner request, 2026-07-26). **Depends on:** T37 — runs **after** it, so it can clean
T37's own message too. Runs alone on a quiet tree; this rewrites history.

**Owns:** commit messages in `git log origin/master..master` only. **No tree changes whatsoever** —
that is the checkpoint.

**Why this is safe here, and would not be elsewhere:** all 58 commits in this range are **unpushed**.
Rewriting them costs nothing — no forks, no clones, no cached SHAs, no CI re-runs. The published
history (up to `origin/master` = `6dab505`) is **out of scope and must not be touched**; the audit of
2026-07-26 already cleared it, and rewriting public history does not un-publish anything.

**The situation, measured 2026-07-26** over the 58 commits (47 touching code, 11 docs-only):

| What | Count |
|---|---|
| Subject lines carrying plan coordinates (`T38`, `wave-5`, `Lane K`) | 12 of 58 |
| Body lines referencing a task code `T\d\d` | 104 |
| Body lines referencing a wave | 38 |
| Body lines referencing a lane | 29 |
| Body lines naming `PLANS.md` / `EXECUTION-PROTOCOL.md` / `RESUME.md` | 27 |
| Body lines mentioning the orchestrator / driver | 10 |
| Body lines mentioning a checkpoint, or pasting gate output | 13 / 68 |

So ~46 subjects already read fine in public; the noise is concentrated in the bodies.

**Do**
1. **Keep the engineering, drop the coordinates.** Every commit must still say *what changed and
   why*. Replace "T24 replaces the hashing scheme" with what the change actually does. Delete
   "Lane L4", "round 2", "READY FOR GATE", "commit token", barrier and driver language outright — it
   describes how this plan was executed by agents, which no reader of the repo can act on.
2. **Keep pasted gate output where it is evidence, compress where it is noise.** A before/after
   regression proof is genuinely useful in a commit body. A full 30-line pytest summary is not —
   reduce it to the line that carries information (`328 passed, 1 skipped`). Do not delete evidence
   that a fix was verified; that is the most valuable thing in these messages.
3. **Rewrite the 12 offending subjects.** Prefer the conventional-commit form already in use
   (`fix(scope): …`). `docs(wave-5): finalize barrier documentation…` becomes something a
   contributor can parse without the plan.
4. **The 11 docs-only commits** are plan bookkeeping — barrier commits, RESUME refreshes. They cannot
   be made meaningful to an outside reader because their entire content is plan-internal. **Do not
   squash or drop them** (that would rewrite the tree, and the plan docs are a legitimate part of
   this repo's history); just give them honest subjects, e.g.
   `docs: record implementation-plan progress`.
5. **Leave the author identity and dates alone.** No `--reset-author`, no date rewriting: that
   fabricates provenance.

**Mechanics** Use a non-interactive message-only rewrite —
`git filter-branch --msg-filter` over `origin/master..HEAD`, or `git rebase` with a prepared message
map. **Take a backup ref first** (`git branch backup/pre-t43`) and keep it until the checkpoint
passes. Never `git push`, never `--force` anything at a remote.

**The consequence to handle, not discover:** rewriting messages changes **every SHA** in the range.
`PLANS.md`, `RESUME.md` and the audit docs cite specific SHAs, and every one of those citations
becomes dangling — as happened once already when the housekeeping commits were distributed. Either
re-point them in a **follow-up commit after the rewrite** (they are then stable, since that commit is
the new tip), or replace them with subject-line references that survive a rewrite. Decide which, do
it, and say which you chose — leaving 20-odd dangling SHAs in the plan docs is exactly the kind of
quiet rot this wave exists to prevent.

**Checkpoint**
```
# 1. the tree is byte-identical — this is a message-only rewrite
git diff backup/pre-t43 HEAD --stat        # expect: empty output
git rev-list --count origin/master..HEAD   # expect: 58, unchanged

# 2. the coordinates are gone from the range
git log origin/master..HEAD --format='%s%n%b' | grep -icE '\b(T[0-9]{2}|wave[- ][0-9]|lane [A-Z])\b|orchestrator|commit token|READY FOR GATE'
# expect: 0

# 3. the published history is untouched
git rev-parse origin/master                # still 6dab505
git log --format='%H' -1 6dab505           # still reachable, unchanged

# 4. no dangling SHA citations left in the plan docs
for sha in $(grep -ohE '\b[0-9a-f]{7,40}\b' docs/plans/*.md docs/audit/*.md | sort -u); do
  git cat-file -e "$sha^{commit}" 2>/dev/null || echo "DANGLING: $sha"
done
# expect: no DANGLING lines (or an explicit note saying they were replaced by subject references)

# 5. the gate still passes, unchanged
GOOGLE_KEEP_PATH=. make check
```
Check 1 is the load-bearing one: a message rewrite that alters a single byte of the tree is a
different task and must be reverted from `backup/pre-t43`.

**Commit:** no new commit for the rewrite itself (it *is* the history). The SHA re-pointing follow-up,
if you choose that route, commits as
`docs(plans): re-point commit references after the message rewrite`
