# Task 05 — Content-hash embedding cache

## Goal
Never re-embed unchanged notes; free VRAM after encoding.

## Spec
Create `app/services/tagging/embed.py`:
- Cache: JSON file at `cache/tag_embeddings.json` (path = code constant `TAG_EMBED_CACHE`, NOT env). Key `sha256(cleaned_text)` hex → embedding list.
- `embed_notes(cleaned_texts) -> np.ndarray`: load cache, encode only missing (truncate each text to 2000 chars, batch 64, `normalize_embeddings=True`), save cache, return array in input order.
- After encoding: `del model; gc.collect(); torch.cuda.empty_cache()`.

## Checkpoint
Run twice on the same 20 notes: second run logs "0 to embed" and returns an identical array (assert in test with a small real model or a stubbed encoder).

## Commit
`task 05: embedding cache keyed by content hash`
Delete this file in the same commit.
