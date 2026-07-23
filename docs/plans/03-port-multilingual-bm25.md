# Task 03 — Port multilingual BM25 from agentic-notebook

## Goal
A Cyrillic-aware BM25 over cleaned note texts. PORT, do not reinvent.

## Spec
Source (MIT, owned by the user): https://github.com/Harduex/agentic-notebook — file `skills/agentic-notebook/scripts/search_index.py`. Clone it, then port into `app/services/search/bm25.py`:
1. The `tokenize()` function + helpers: Unicode word regex, CJK bigram ranges, light English stemming, casefolding. Do NOT replace with `.split()` or `rank_bm25` defaults — Cyrillic support is the point.
2. The BM25 scoring math with the source's k1/b values.
3. Storage adaptation: in-memory index built at ingest over `cleaned_text`, rebuilt via existing ingest hooks when notes change. No `.notebook/` dir, no pickle cache.

API: `bm25_search(query: str, k: int) -> list[tuple[note_id, float]]`.

## Checkpoint
Tests: (a) Bulgarian query matches a Bulgarian note; (b) "keyboards" matches a note containing "keyboard"; (c) scores finite and descending.

## Commit
`task 03: port multilingual BM25 index from agentic-notebook`
Delete this file in the same commit.
