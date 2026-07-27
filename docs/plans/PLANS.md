# Implementation Plan — &lt;name of this body of work&gt;

> **This file is a blank template.** The plan that filled it — an audit remediation and
> re-architecture, 8 waves, 43 tasks — completed on 2026-07-27 and was stripped from the working
> tree deliberately. It is not lost: `git log -- docs/plans/PLANS.md` lists every revision, and
> `git show <stripping-commit>^:docs/plans/PLANS.md` prints the finished plan in full.
>
> Fill the sections below for the next plan and delete this block. Keep § Verification as it is —
> those two scripts are the machinery, not the content.

**One paragraph: what this plan changes, and what "done" means.** Name the source of truth the tasks
trace back to (an audit document, a ticket, a design spec). A plan whose tasks trace to nothing has
no way to prove it covered everything.

**Structure:** work is grouped into **waves** (strictly ordered, hard barriers) and inside a wave
into **lanes**. Every lane owns a disjoint set of files, so lanes in a wave run **concurrently, one
agent per lane** — except where a task depends on another lane's output, which splits a wave into
**rounds** (`EXECUTION-PROTOCOL.md` §1.3). Tasks inside a lane are serial. A lane never edits a file
it does not own. One agent may also work the lanes serially; the rules are identical either way.

---

## Wave graph

A **wave** is a hard barrier: every task in it lands, the gate is green on the combined tree, and the
wave's spec file is deleted before the next wave is dispatched. Waves exist to make the dependency
edges that *cannot* be parallelised explicit.

```
wave 1  <what this wave establishes, and why nothing else can start first>
   |
wave 2  <...>
```

State each wave's precondition in one line. If you cannot name what would break by running the next
wave early, it probably is not a separate wave.

## Lane ownership matrix

A **lane** is the set of paths one agent owns for one wave. Two lanes in the same wave must have
**provably disjoint** write sets — § Verification invariant 1 checks this mechanically, so keep the
row format (backtick-quoted paths) or the check silently stops seeing your rows.

| Wave | Lane | Owns (paths) | Tasks |
|---|---|---|---|
| 1 | **A** &lt;short name&gt; | `path/one.py`, `path/two.py`, `tests/test_one.py` | T01 |

Disjoint write sets make lane *edits* safe. They do **not** make lane *verification* safe: one tree
means one test suite, and a change to a shared choke point breaks tests belonging to no lane. That is
the driver's to adjudicate, never the lane's. A file no lane owns but a lane needs **to do its own
declared task** is a gap in the plan — grant it to that lane for that task, and record the grant
here. "Unassigned" is not "free to edit", and correctly diagnosing another lane's breakage is the
report, not the mandate to fix it.

## Task index

| Task | Wave/Lane | Round | Summary | Fixes | Est. | State |
|---|---|---|---|---|---|---|
| T01 | 1 A | 1 | &lt;one line&gt; | &lt;finding id, or —&gt; | ½ d | todo |

`Fixes` is what invariant 2 reads. A task that fixes nothing (an owner request) is fine — write `—`
and say so, rather than weakening the coverage check to accommodate it.

## Status

| Wave | Lanes | Rounds | State |
|---|---|---|---|
| 1 | A B | T01·T02 → T03 | todo |

The driver flips this row at the barrier. Lane agents never touch it — that removes the race without
needing a lock.

## Proposed follow-ups

Work discovered while executing, recorded instead of built (`EXECUTION-PROTOCOL.md` §7). One line
each, naming the task that found it and why it was not done then.

| From | Proposal |
|---|---|

**Still open, carried over from the completed plan.** These are real work, not history:

| From | Proposal |
|---|---|
| T40 | `EntityService` is the dominant cold-start cost — **17.1 s of a 21.3 s boot at 2900 notes** with a cold cache dir (~0.4 s warm). It is eager by design, since `app/search.py` folds its signal into every query, but `lifespan.py` builds it through the whole-corpus legacy constructor while a content-addressed `build`/`apply` interface sits unused on `entity_service.py`. The largest remaining performance win in this codebase. |
| T40 | `ChunkingService.load_or_compute_embeddings` (`chunk_embeddings.npz`) is the last legacy whole-corpus embedding pair; its sibling was deleted from `app/search.py`. Migrating it to the `VectorStore` closes the "two implementations of one thing" finding completely. |
| T40 | CLIP image-search init costs ~1.5–2.0 s of boot, inside `VibeSearch.from_model` when `enable_image_search` is set — i.e. on the search path. Worth deciding whether it must precede `ready`, since text search does not use it. |
| T34 | `app/services/entity_service.py` `except Exception: return False` in `_is_cache_valid()` swallows everything, making a corrupt cache and a bug indistinguishable. Catch `(OSError, json.JSONDecodeError)`, log the type via `safe_exc`, let the rest propagate. |
| T34 | Sessions store citations in messages, but the client's `loadSession` discards them on reload. Needs a client change. |
| T31 | `LoadingScreen.tsx` still carries inert utility-class strings from the removed CSS framework — dead, harmless, delete when next touching the file. |
| T10 | Migrate the tagging pipeline's ad-hoc `print` + `llm_failures.log` writes to a named stdlib logger, so redaction is enforced by one handler rather than per-call discipline. |
| T09 | `app/routes/organize.py` still accepts the action string `"merge"`, which the client no longer emits. Dead literal, safe to delete. |
| T02 | The CI-green half of the original bootstrap checkpoint is still unverified pending a push to `origin`. |

## Verification

Two invariants any parallel plan must keep. **Re-run both after editing this file**, and paste the
output — a result copied forward from last time is not a check.

**Invariant 2 needs a source-of-truth document to read.** It scans `docs/audit/*.md` for rows shaped
`| B12 | ... |` and checks each id is mentioned somewhere in `docs/plans/`. With no active plan and no
new audit, it finds nothing to check and prints `unowned: none` — a vacuous pass, not a real one. It
becomes a real signal the moment you drop an audit into `docs/audit/` and start filling in § Task
index. Point it at a different directory if your source of truth lives elsewhere.

```bash
# 1. no two lanes in the same wave own the same path
#    Widen the wave range whenever a wave is added. This read `[1-6]` while waves 7 and 8 existed,
#    so it printed `overlaps: 0` without ever having read those rows. A scan that cannot see the
#    wave you are closing is not a check.
python3 - <<'PY'
import re, collections
waves = collections.defaultdict(dict)
for l in open('docs/plans/PLANS.md'):
    m = re.match(r'^\| ([1-8]) \| (\*\*)?([A-Z0-9]+|—)', l)
    if not m: continue
    c = [x.strip() for x in l.strip().strip('|').split('|')]
    waves[c[0]][c[1]] = set(re.findall(r'`([^`]+)`', c[2]))
bad = 0
for w, lanes in sorted(waves.items()):
    seen = {}
    for lane, paths in lanes.items():
        for p in paths:
            if p in seen: print(f"!! wave {w}: {p} in {seen[p]} and {lane}"); bad += 1
            seen[p] = lane
print("overlaps:", bad)
PY

# 2. every finding in the source-of-truth document is owned by a task
#    A finding split into lettered parts (B3 -> B3a/B3b) counts as owned when every part is:
#    `\bB3\b` does not match "B3a", so suffixed forms are matched explicitly. This script once
#    printed `unowned: ['B3']` while the barrier notes claimed "none" — the claim had been copied
#    forward without the script being re-run.
#
#    Deleting a wave spec at its barrier can orphan a finding whose only mention was in that file.
#    Run this with the spec excluded BEFORE deleting it, and re-anchor anything that would be lost.
python3 - <<'PY'
import re, glob
plan = "".join(open(f).read() for f in glob.glob('docs/plans/*.md'))
audit = "".join(open(f).read() for f in glob.glob('docs/audit/*.md'))
ids = set(re.findall(r'^\| (B\d+|A\d+|T\d+|H\d+|P\d+) \|', audit, re.M))
def owned(i):
    return re.search(rf'\b{i}\b', plan) or re.search(rf'\b{i}[a-z]\b', plan)
print("unowned:", sorted(i for i in ids if not owned(i)) or "none")
PY
```
