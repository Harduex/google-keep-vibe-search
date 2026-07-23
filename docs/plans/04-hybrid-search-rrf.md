# Task 04 — Hybrid search via RRF fusion

## Goal
Fuse dense + BM25 with the existing RRF; remove ad-hoc keyword blending.

## Spec
In `search_service.search()`:
1. Dense search (existing embeddings) → ranked list A.
2. `bm25_search` → ranked list B.
3. Fuse with the EXISTING RRF implementation (same as image fusion): `score(d) = sum(1/(60 + rank_i(d)))`.
4. DELETE the old keyword-overlap blending code.
5. When image search is enabled, its results join the same RRF fusion as a third list.

## Checkpoint
5 test queries (2 Bulgarian, 3 English): hybrid results at least as relevant as dense-only (manual eyeball, record in commit body). A query using a rare term that appears verbatim in exactly one note ranks that note top-3.

## Commit
`task 04: hybrid dense+BM25 search fused with RRF`
Delete this file in the same commit.
