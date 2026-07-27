# Scoped Retagging & Tag Replacement — Feature Idea

**Status:** Idea (not designed, not implemented)
**Created:** 2026-07-27
**Seed:** "Add 'replace my tags with this run's tags' — currently it can easily get cluttered. I may want to retag newly imported notes and not apply the other tags to all the other notes."

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
   merge is a manual, one-pair-at-a-time fix.
2. **No way to retag a subset.** After importing new notes, the intent is "tag *these*". But
   a run clusters and tags the whole corpus, so applying it also drops new tags on 14k notes
   that were already organized. The only lever today is granularity, which changes cluster
   size, not scope.

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
