# Scoped Retagging & Tag Replacement — Feature Idea

**Status:** Idea (not designed, not implemented). Part 2 below — the confirmed re-run
defects — is diagnosed and ready to implement independently of the scope/write-mode design.
**Created:** 2026-07-27
**Updated:** 2026-07-30 — re-running Auto-Categorize over already-categorized notes was
investigated; the near-duplicate tags in problem 1 now have confirmed root causes, and the
review UI turned out to mis-route accept/discard clicks whenever they occur. See Part 2.
**Seed:** "Add 'replace my tags with this run's tags' — currently it can easily get cluttered. I may want to retag newly imported notes and not apply the other tags to all the other notes."
**Seed (2026-07-30):** "After I pressed Auto-Categorize Notes over already categorized notes I had duplicated tags listed, and when I pressed accept / discard on a tag it was addressed in the header count, but the tag showed no selected state. Also — will accepting these create duplicates of tags I already have, and what exactly does it tag?"

## The problem

Applying a categorization run is **purely additive**. `apply_proposals`
(`app/routes/organize.py:138-146`) calls `NoteService.tag_notes`, which appends to a note's
tag list and never removes anything. There is no path that says "these tags supersede what
that note had".

Two consequences, both of which get worse the more often you run the pipeline:

1. **Clutter / duplication.** Clustering is recomputed from embeddings on every run, so a
   note can land in a cluster named slightly differently than last time (manifest reuse at
   `categorization_service.py:952` limits this, but only for clusters stable at ≥0.9 cosine).
   The note keeps both tags. Nothing dedupes near-synonyms after the fact; the tag manager's
   merge is a manual, one-pair-at-a-time fix. **Part 2 pins down where the near-duplicate
   names actually come from** — it is not only clustering drift.
2. **No way to retag a subset.** After importing new notes, the intent is "tag _these_". But
   a run clusters and tags the whole corpus, so applying it also drops new tags on 14k notes
   that were already organized. The only lever today is granularity, which changes cluster
   size, not scope.

---

# Part 1 — Scope & write mode (the original feature idea)

## What the feature should offer

Two related capabilities, worth designing together because they share the "scope + write
mode" concept:

- **Scope selection:** run/apply against a subset — newly imported notes (no tags yet),
  notes matching a filter, or an explicit selection. Untouched notes keep their tags.
- **Write mode:** `add` (today's behaviour) vs `replace` — for every note in scope, the
  run's tags become that note's tag set, with previous tags removed.

## Open questions to resolve before designing

- **What exactly does `replace` clear?** All tags on the note, or only tags the pipeline
  itself created in earlier runs? Google Keep labels are imported as tags on load
  (`seed_tags_from_labels`), and clobbering the user's own labels would be data loss from
  their point of view. Provenance is not currently tracked per assignment — the tag map is
  `note_id -> [names]`, with no origin field. This may be the real blocker.
- **Is `replace` reversible?** `tags.json` gets a `.bak` on write, but that is one
  generation deep and not surfaced in the UI. A destructive mode probably needs an explicit
  undo or a dry-run diff ("N notes will lose tags X, Y") before it is safe to ship.
- **Does incremental mode already cover the "new notes" case?** `categorize_incremental`
  assigns from manifest centroids with zero LLM calls. Scoping it to untagged notes might
  deliver most of the value at a fraction of the effort — worth checking before building
  scope selection from scratch.
- **Where does scope live in the UI?** A selector next to granularity, or a separate
  "Retag these notes" action starting from the notes list's current filter?

## Adjacent cleanup this would enable

- Bulk dedupe of near-synonym tags (embedding similarity over tag prototypes already exists
  in consolidation: `gray_zone_merge_proposals`) as a standalone tag-manager action, rather
  than only inside a full run.
- A "tags created by run N" grouping, which requires the same per-assignment provenance the
  `replace` question raises.

---

# Part 2 — Confirmed defects when re-running over already-tagged notes

Diagnosed 2026-07-30 with synthetic runs only (60 fake notes, stub LLM — never the real
corpus). Independently shippable and worth doing **before** Part 1: re-running is the
workflow Part 1 exists to make safe, and it is currently mis-reporting what it will do.

## Root cause: proposals are keyed by tag name, and tag names are not unique

A synthetic 4-cluster run whose stub LLM names every cluster `Topic`:

```
streamed `proposal` frames : [('Topic',24), ('Topic',20), ('Topic',8), ('Topic',8)]
final `label_updates` frame: [('Topic',23), ('Topic 2',20), ('Topic 3',8), ('Topic 4',8), ('Uncategorized',1)]
```

Collisions are only repaired at the very end, by `_deduplicate_name`
(`app/services/categorization_service.py:1806`, called at `:1375`) — after every streamed
card the user has already been reviewing.

Why they happen, and why specifically on a re-run over already-categorized notes:

1. **Manifest reuse has no uniqueness constraint.** `_reuse_manifest_tag`
   (`categorization_service.py:127`) returns the _first_ stored centroid above
   `MANIFEST_REUSE_SIMILARITY` (0.90); nothing stops two different fresh clusters from
   reusing the same previous tag. This path only exists once `tag_manifest.json` from a
   prior run exists — i.e. exactly the "already categorized" case.
2. **The naming prompt asks for reuse, per cluster, with no cross-cluster check.** Existing
   vault tags are appended with "reuse one if it fits well" (`categorization_service.py:573`)
   and each cluster is named independently.

## Defect 1 — accept / discard stages the wrong card (CONFIRMED)

`ProposalCard.tsx:75` sends `cardId = proposal.tag_name`; `useOrganize.ts:441`
(`resolveById`) resolves it with `findIndex` → **first match wins**. Streamed proposals are
prepended (`useOrganize.ts:365`), so the _topmost_ duplicate always absorbs the click.

Reproduced with a temporary vitest harness: two streamed `'Topic'` cards, click the lower
one → the upper card gets `action: 'approve'`, the clicked card stays `'pending'`,
`actionablCount` goes to 1. That is the reported symptom exactly — header count moves, card
shows no selected state. (The repro was deleted after diagnosis; commit it as the regression
test listed below.)

The same name-keying breaks four more things:

| Site                                     | Effect                                                                                                                      |
| ---------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| `useOrganize.ts:509` (`mergeProposals`)  | `.map` over name matches — a staged merge hits **every** same-named card at once                                            |
| `useOrganize.ts:144` (`toActionsMap`)    | N clusters collapse to one lock key, so the server-side consolidation lock under-locks                                      |
| `useOrganize.ts:229` (`reattachActions`) | one decision is reapplied to every same-named card in the final frame — a decision on cluster X silently lands on cluster Y |
| `ProposalDashboard.tsx:125`              | `tag_name` is the React `key` → duplicate keys, so card-local state (`isExpanded`, `isRenaming`) can bleed between cards    |

**The broken state can outlive the run.** The partial set is persisted pre-dedup
(`app/routes/organize.py:50-57`, every `PARTIAL_PERSIST_EVERY` = 5 proposals). If a run is
cancelled or errors during naming, no `label_updates` frame ever lands, and `restorePending`
(`useOrganize.ts:239`) hands the duplicate-named set back on remount.

## Defect 2 — consolidation collapses same-named clusters (PLAUSIBLE, not reproduced)

Consolidation runs _before_ `_deduplicate_name` and keys its dicts on names:

- `merged_into = {lbl.name: lbl.name}` (`categorization_service.py:1163`) gives N same-named
  labels a single union-find node.
- `_apply_merge_map`'s `prop_map = {lbl.name: lbl}` (`categorization_service.py:281`) keeps
  only the last same-named label, then `vocab.labels = list(prop_map.values())` (`:338`)
  writes that back unconditionally.

So a run with duplicate names _and_ at least one applied merge drops the earlier same-named
clusters from the vocabulary. The synthetic run applied 0 merges, so this is code-read
rather than observed — but it is the same root cause and belongs in the same pass.

## Defect 3 — `_sanitize_tag_name` prevents the reuse it asks for (CONFIRMED)

The existing-tags hint reaches the LLM raw, but the answer goes through `_sanitize_tag_name`
(`categorization_service.py:185`), which `.title()`-cases, strips punctuation and caps at
3 words:

```
'iOS'                              -> 'Ios'
'C#'                               -> ''            (dropped entirely)
'3d printing'                      -> '3D Printing'
'machine learning notes and ideas' -> 'Machine Learning Notes'
```

So a vault tag the LLM correctly chose to reuse comes back as a **near-duplicate of itself**
(`Ios` beside `iOS`), or is dropped and replaced by the keyword fallback. This is a direct,
confirmed source of the clutter in problem 1 above.

## What the pipeline actually does (answers worth putting into UI copy)

- **Approving an exact-name match does _not_ duplicate a tag.** `NoteService.tag_notes`
  (`app/services/note_service.py:274`) appends the string only if absent, and there is no tag
  registry — tags are per-note string lists. Approving `Cooking` when `Cooking` exists just
  adds those notes to the existing tag. A _near_ match does create a second tag: via the
  `_deduplicate_name` suffix (`Topic 2` is a brand-new tag beside `Topic`) or via Defect 3.
- **The card does not tag the cluster it previews.** Mid-run a card shows HDBSCAN cluster
  members; the final `label_updates` frame replaces `note_ids` with the output of
  `_assign_labels_via_embeddings` (`categorization_service.py:1517`) — a corpus-wide
  re-assignment. Per note: cosine against each tag's prototype (0.5 × embedding of tag
  name + keywords, 0.5 × seed centroid, normalized); keep tags clearing that tag's own
  threshold (10th percentile of its seeds' similarities × `GLOBAL_ASSIGNMENT_THRESHOLD` 0.75);
  keep only those within `RELATIVE_TAG_MARGIN` (0.85) of the note's own best score; cap at
  `MAX_TAGS_PER_NOTE` (3). A note clearing nothing gets its best tag if it reaches
  `CATCH_ALL_THRESHOLD` (0.5), as a review-queue card, else Uncategorized. In the synthetic
  run the top card went 24 → 23 notes between the streamed and final frames, so **the count
  shown mid-run is not what gets applied**.

This is also the answer to "does a re-run re-tag everything?" — yes: every full run
reassigns the whole corpus against the new vocabulary, which is precisely why Part 1's scope
selector is wanted.

## The fix, in dependency order

1. **Stable proposal identity (fixes Defect 1).** Emit a `proposal_id` on every `proposal`
   and `label_updates` entry (cluster index or uuid, assigned when the `Label` is created,
   preserved through consolidation). Key `cardId`, `resolveById`, `toActionsMap`,
   `reattachActions`, `mergeProposals` and the React `key` on it instead of `tag_name`, with
   name lookup kept only as a fallback for restored pre-`proposal_id` sets.
   - `toActionsMap` feeds the server lock list, which is tag-name-keyed by contract
     (`app/routes/organize.py:111`, `load_pending_actions`). Decide whether the lock list
     moves to ids too, or the client maps id → name at that boundary.
2. **Dedupe names at stream time**, so two identical cards are never shown: track used names
   during the naming loop and suffix (or re-ask) on collision _before_ emitting the
   `proposal` frame, rather than at `:1375`.
3. **Key consolidation on identity, not name** (fixes Defect 2).
4. **Case-insensitive reuse of vault tags** (fixes Defect 3): match the LLM's answer against
   the existing tag list before sanitizing, and return the vault's own spelling on a hit.

Regression tests to commit with the fix:

- Backend: a `categorize` run whose LLM returns one name for every cluster emits **unique**
  `tag_name`s in its streamed `proposal` frames.
- Frontend: with two same-named proposals in the list, approving the second stages the
  second — asserted on the identity, not the name.
