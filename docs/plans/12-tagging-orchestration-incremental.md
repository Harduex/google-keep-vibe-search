# Task 12 — Tagging orchestration + incremental mode + manifest

## Goal
Wire tasks 02-11 into one pipeline; add manifest, incremental mode, tag-name stability.

## Spec
`app/services/tagging/pipeline.py`, exact order:
load → clean → embed(cache) → cluster → centroids → c-TF-IDF(cleaned) → sample → name(sequential) → dedupe(auto) → gray-zone(LLM→dashboard) → assign → apply+proposals → save manifest.

Manifest `cache/tag_manifest.json`: run date, constants snapshot, per-cluster {tag, size, centroid, keywords}.

Incremental mode (flag/param, NOT env): new/changed notes only (hash vs cache) → embed → assign vs manifest centroids. NO clustering, NO LLM. If >20% of vault is new: log "recommend full re-run", proceed anyway.

Stability: on full re-runs, match new centroids to manifest centroids; cosine >= 0.9 → REUSE old tag, skip LLM for that cluster.

## Checkpoint
(1) Full run clean. (2) Immediate second full run: >=95% of notes keep primary tag. (3) One new note + incremental: correct existing tag, zero LLM calls (verify via logs). (4) VRAM peak < 12 GB. Record all four in commit body.

## Commit
`task 12: tagging pipeline orchestration, manifest, incremental mode`
Delete this file in the same commit.
