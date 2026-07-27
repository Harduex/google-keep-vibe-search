# Pre-Push Safety Audit

**Range audited:** `origin/master..HEAD` — 16 commits, `9adc290` (oldest) .. `abc753b` (newest)
**`origin/master` at audit time:** `4862b6c` (fetched 2026-07-27)
**Date:** 2026-07-27
**Scanner:** gitleaks 8.21.2, self-test **PASS** (planted `AKIA…` / `ghp_…` key detected before any
clean result was trusted)

## Verdict

> **SAFE TO PUBLISH** — commit range `origin/master..HEAD` (`9adc290..abc753b`, 16 commits), as
> audited on **2026-07-27**. Zero hard findings. Nine advisories below, none publish-blocking, none
> requiring a history rewrite.

The verdict covers **committed objects only** — diffs *and* all 16 commit messages. It does not cover
the working tree, which was dirty at audit time, nor any commit made after `abc753b`. Re-run before
publishing if further commits land.

---

## Scope and method

This is a **delta audit**, not a first pass. A full-history audit ran 2026-07-26 (gitleaks, self-test
PASS, all refs plus stashes) with no hard findings, and everything up to `origin/master` is already
public. This pass exists so that the 16 new commits are audited *before* they are published.

**Never quote a finding.** Every check in this audit was run so that its output is a location, a file
name, a commit SHA, a category or a count — never the matched text. Where a pattern would have
printed content (paths, emails, `.env` values), the value was masked or reduced to a count before it
reached the terminal.

### Deviations from the `git-ops:auditing-repo-for-leaks` skill

The skill's `scripts/scan-history.sh` was **not run as-is**. Three reasons, all stated so a reader can
judge the substitution:

1. **No range parameter.** The script hardcodes `git rev-list --all` / `git log --all`. It answers
   "is this repo safe to publish", not "is this delta safe to publish". Substituted: gitleaks with
   `--log-opts="origin/master..HEAD"` for the delta, plus a full-history baseline run, plus manual
   range-restricted equivalents of its passes 2–6.
2. **Passes 2 and 6 print content.** Pass 2 prints the whole matching line for every machine-local
   path hit across every blob in history; pass 6 prints raw email addresses. Under this project's
   privacy boundary, a matching line from a blob could carry note text. Substituted with
   `grep -l` / `grep -c` / `sed`-masked equivalents.
3. **Pass 4 would false-positive on `.env.example`.** Its pattern `(^|/)\.env` matches
   `.env.example` and would report a HARD finding. Triaged manually — see **A9**.

Nothing else in the skill was skipped. Its self-test discipline was honoured in full: gitleaks was
proven to fire on a planted secret before any clean result was accepted.

Additionally, gitleaks was **not** run in `dir` mode over the working tree. That mode walks
`cache/` and would read real note data, and a false positive there prints a content snippet. The
working tree is out of scope regardless.

### Checked mechanically

| Check | Tool | Result |
|---|---|---|
| Scanner self-test | gitleaks on a throwaway repo with a planted key | **PASS** (exit 1 = fires) |
| Secrets, range | `gitleaks git --log-opts="origin/master..HEAD"` | exit 0, no leaks |
| Secrets, per-commit | gitleaks × 16, one commit each | all exit 0 |
| Secrets, full history baseline | `gitleaks git` on this branch | 259 commits, no leaks |
| Secrets, local-only backup branch | gitleaks over `backup/pre-history-rewrite --not --remotes=origin` | 52 commits, no leaks |
| Private key material | `git grep -lI 'BEGIN … PRIVATE KEY'` over `git rev-list --all` | none |
| Commit bodies: paths / emails / `Title:`/`Snippet:` / key shapes / password literals / `cache/` paths / private keys | regex battery over `git log --format=%B`, counts only | 0 / 0 / 0 / 0 / 0 / 0 / 0 |
| Added lines: machine-local paths | `git diff origin/master..HEAD`, added lines only | 0 |
| Added lines: `Title:` / `Snippet:` shapes | same | 1 hit, benign (**A5**) |
| Added lines: emails | same, domains only | 0 real (only `@pytest.fixture`-style decorator false positives) |
| Employer domain sweep | range diffs + messages + whole tree at `HEAD` | 0 hits |
| Real username sweep | tree at `HEAD`, range messages, range added lines | 0 / 0 / 0 |
| Ever-committed `cache/` or export artefacts | `git log --all --name-only` | none |
| Ever-committed `.npz/.npy/.pt/.db/.sqlite/.dump/.pem/.key/.p12/.env` | `git log --all --name-only` | none |
| Binary files in range | `git diff --numstat` (`-`/`-` rows) | none |
| Blobs > 200 KB at `HEAD` | `git ls-tree -r -l` | 2, both lockfiles (**A7**) |
| Redaction regression in `app/` | `git grep` at `HEAD` for `str(e)`, `repr(e)`, `traceback.print_exc/format_exc`, `{e}`/`{exc}`/`{err}` f-string interpolation, `detail=`/`logger.*` with a bare exception var, over all 80 `.py` files | **gate empty** — see below |
| `.gitignore` coverage | read at `HEAD` + `bench/.gitignore` | complete (**A9** context) |
| Lockfile registries / auth tokens | `package-lock.json`, `uv.lock` | only `registry.npmjs.org`, `files.pythonhosted.org`, `download-r2.pytorch.org`; 0 `_authToken`/`_auth=`/`token=` |

**Redaction regression, verified independently of wave 7's claim.** At `HEAD`, across all 80 Python
files in `app/`, the grep gate returns exactly two hits, both at `app/core/redact.py:4-5` — inside
the module docstring, which quotes the forbidden patterns in order to explain why they leak. Zero
executable occurrences. Every exception that reaches an HTTP body, a stream frame or a log line
routes through `safe_exc(e)` / `safe_meta(...)`: verified at `app/core/exceptions.py`,
`app/ingest.py`, `app/routes/{chat,embeddings,imports,search,tags}.py`,
`app/services/session_service.py`. Run at `HEAD`, not against the working tree (a sibling lane is
mid-edit).

**One gitleaks counter discrepancy, resolved.** The range scan reported "15 commits scanned" for a
16-commit range. Per-commit scanning identified the missing one as `2e20ca5`, whose diff is
`0 insertions / 308 deletions` (it deletes the wave-6 spec). gitleaks scans added lines, so a
pure-deletion commit yields nothing to scan. Its message was read in full by hand; its diff
introduces no content. Not a gap.

### Checked by eye

- **All 653 lines of all 16 commit messages, read in full.** This was the higher-risk half of the
  range and it was not skipped, sampled, or inferred from greps.
- Every distinct added string literal ≥ 35 characters in the range's Python and TypeScript source and
  test files (~60 strings across 16 files), judged for whether it could be real note text.
- `.env.example` (values masked), `.gitignore`, `bench/.gitignore`, `.claude/settings.json`,
  `bench/baselines/*.json` (key names only).
- The two files at `HEAD` containing `/home/…`-shaped strings.

### Limits — what a reader should re-run before trusting this later

1. **Working tree and untracked files were not audited.** Re-run after the tree is clean.
2. **Only `origin/master..HEAD` was delta-audited.** Any commit after `abc753b` is uncovered.
3. **Stashes were not re-scanned in this pass** (8 entries exist; the driver's shared-tree rules put
   the stash list off-limits, and they belong to a human). The 2026-07-26 full-history audit covered
   them and found nothing. Stashes are not published by a branch push.
4. **Other local branches beyond `master` were not delta-audited** except `backup/pre-history-rewrite`
   (**A2**). They are already on `origin` or out of scope for a `master` push.
5. **gitleaks is a signature scanner.** A clean run means no *known-shape* credential. It cannot
   recognise note text, and note text is this repo's real risk — which is why the note-text checks
   above are pattern sweeps plus a manual read, not a scanner result.

---

## Hard findings

**None.** No secrets, no private key material, no committed `.env`, no database dumps, no model
weights, no `cache/` or `$GOOGLE_KEEP_PATH` content, no note text, no prompt text, no third-party
PII. **No history rewrite is required.**

For clarity, since a rewrite is a materially heavier remedy than an edit: nothing in this range would
need `git filter-repo`, a force-push, or credential rotation. Every advisory below is fixable with an
ordinary commit, or is simply acceptable as-is.

## Advisories

Severity scale: **MEDIUM** = act before publishing; **LOW** = fix when convenient; **INFO** = record
only, no action needed.

### A1 — Plan docs state the wrong `origin/master` SHA — **MEDIUM (accuracy, not a leak)**

`docs/plans/PLANS.md`, `docs/plans/RESUME.md` and `docs/plans/wave-8-release.md:173` all state that
`origin/master` is `6250507`. It is `4862b6c`, which contains `6250507` as an ancestor. Any future
audit, coverage check, or "what is unpushed" calculation that trusts those docs will compute the
wrong range and silently over- or under-scan.

*Remediation:* correct the SHA in all three documents at the wave barrier. Not this task's write set.
*Severity is MEDIUM because it degrades the next audit, not because it discloses anything.*

### A2 — Local-only branch `backup/pre-history-rewrite` holds 55 commits unreachable from any origin ref — **MEDIUM**

`refs/heads/backup/pre-history-rewrite` (`b3e6f0f`, 188 commits) exists locally with no remote
counterpart. 55 of its commits are reachable from no `origin` ref. Its name says a history rewrite
happened at some point; a rewrite is normally performed *to remove something*, and this branch is the
pre-removal copy.

Scanned as part of this audit: gitleaks over those unreachable commits — 52 commits scanned, **no
leaks found**. So this is a caution about publication mechanics, not a known leak.

*Remediation:* publish with an explicit refspec — `git push origin master`. **Never `git push --all`
or `git push --mirror`**, either of which would publish this branch and undo whatever the rewrite
achieved. Once the owner is satisfied the rewrite is settled, deleting the local backup branch removes
the hazard permanently.

### A3 — Repo owner's personal git identity in all 16 commits — **INFO**

Author/committer is `Harduex <…@gmail.com>` on every commit in the range — a personal address, not an
employer address. This is inherent to git and is already present in the 259 published commits.
Explicitly checked and confirmed: **no employer domain appears anywhere** in the range's diffs,
messages, or the tracked tree at `HEAD`.

*Remediation:* none. Expected and acceptable.

### A4 — Placeholder machine-local paths in two files — **INFO**

`README.md:55` and `scripts/setup.ps1:31` contain `/home/…/Takeout/Keep`- and
`C:\Users\…\Takeout\Keep`-shaped example paths. Both are **placeholders**: the PowerShell one
interpolates `$env:USERNAME` at runtime, and the real account name appears **nowhere** in the tracked
tree, in the range's commit messages, or in the range's added lines (three separate sweeps, all zero).
Neither file was touched in this range, and **zero** machine-local paths were added anywhere in the
range — including in commit bodies, which was the specific worry.

*Remediation:* none.

### A5 — `Title:`/`Snippet:` shape appears once in the range — **INFO**

One added line matches the note-sample shape: `tests/test_redaction.py:5`, inside the module
docstring. It names the shape in order to document what the redaction module prevents. It contains no
note content.

### A6 — Fixture and example strings are synthetic — **INFO**

Every added string literal ≥ 35 characters in the range's Python and TypeScript source and test files
was read. All are assertion messages, docstrings, test names, or obviously fabricated fixture text.
No tracked data file exists under `tests/`; `bench/baselines/*.json` (313 B and 1308 B) hold only
numeric metrics for two public datasets, and `bench/corpora/` is gitignored. Nothing is derived from
the real corpus.

The one borderline item: `tests/test_naming.py` and commit `85c2f26` each cite a single generic
two-word tag string as an example of a sanitiser bug. A tag name of that generality is not
identifying and is not note content.

### A7 — Two files over 200 KB — **INFO**

`uv.lock` (859 KB) and `client/package-lock.json` (303 KB), both modified in this range, are the only
blobs above 200 KB reachable from `HEAD`. Both are text lockfiles and belong in the repo. No binary
file is touched anywhere in the range; no `.npz`, `.npy`, `.pt`, `.safetensors`, `.db`, `.sqlite`,
`.dump`, `.pem`, `.key`, `.p12` or `.env` has ever been committed in the repo's history.

### A8 — Commit `921dddc` subject reads "drop baked secrets" — **INFO (misleading, not a leak)**

The subject invites a reader to assume a credential was committed and later removed — which would
imply a history rewrite. It did not happen. The body makes clear the change removed a `COPY .env`
instruction from the Dockerfile, i.e. it stopped a *build* from baking an untracked file into an
image. Independently confirmed: no `.env` file appears in the name list of any commit in the repo's
entire history.

*Remediation:* none required. Worth knowing so nobody re-opens this as a suspected leak.

### A9 — `.env.example` is tracked and trips the standard `.env` heuristic — **INFO**

`.env.example` is tracked (deliberately — `.gitignore` ignores `.env` and `.env.*` and then re-includes
`!.env.example`). Any scanner using the common `(^|/)\.env` pattern, including the audit skill's own
pass 4, will report it as a hard finding. Triaged: of five uncommented keys, only three carry values —
`LLM_PROVIDER`, `LLM_API_BASE_URL`, `LLM_MODEL`. `LLM_API_KEY` and `GOOGLE_KEEP_PATH` are **empty**.
No value is a credential and none is a machine-local path. The file was not touched in this range.

`.gitignore` coverage verified complete for every path the spec names: `cache/` (plus `cache.bak*` and
`cache-*/`), `*.log`, `.env`/`.env.*`, `.venv`, `node_modules`, and `bench/corpora/` via
`bench/.gitignore`. `*.npz` is not listed by extension but is covered in practice — embeddings live
inside the ignored `cache/`, and no `.npz` is tracked.

### A10 — One plan coordinate survives in a client test name — **INFO (cross-task note)**

`client/src/hooks/__tests__/useOrganize.test.ts` has a `describe()` **string literal** carrying a task
code. The comment-hygiene sweep is scoped to comments, so a comments-only pass cannot reach it, but
the wave checkpoint's grep for plan coordinates in `client/src/**/*.ts` will flag it. Not a leak —
recorded so it is triaged deliberately rather than discovered at the gate.

### A11 — Plan coordinates throughout the 16 commit messages — **INFO**

Task codes, wave numbers, lane letters and audit finding ids appear throughout the range's commit
bodies. This is noise, not disclosure, and the retired T43 already ruled that rewriting published
history for it is not worth the cost. Recorded for completeness only.

---

## What the commit messages actually contain

Since the driver's specific concern was that checkpoint evidence was pasted into roughly fifteen
commit bodies, and since a SAFE verdict that had not read them would be worse than no verdict: all 16
were read end to end (653 lines).

They contain test counts, timings, before/after latency figures, eval metric values, file and symbol
names, grep commands with their *empty* output, and design rationale. Several explicitly label their
checkpoint block "redacted — counts only, no note/prompt text". Every `GOOGLE_KEEP_PATH=` occurrence
(6) assigns the literal `.`, never a real export path. One body discloses a cache-hygiene incident by
**file name** (`tag_manifest.json` and friends) with no content. The only network literals are
`localhost:8000` and `127.0.0.1`.

No note text. No prompt text. No sampled note titles or snippets. No credentials. No emails beyond the
committer's own. No machine-local paths.
