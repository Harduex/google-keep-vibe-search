# Task 01 — Constants modules + frozen-config guard

## Goal
Create the two constants files all later tasks import. Add a test that fails if `.env.example` ever changes.

## Spec
Create `app/services/tagging/constants.py`:
```python
UMAP_N_COMPONENTS = 10
UMAP_N_NEIGHBORS = 15
UMAP_MIN_DIST = 0.0
HDBSCAN_MIN_CLUSTER_SIZE = 12
HDBSCAN_MIN_SAMPLES = 5
SAMPLE_CENTRAL_DOCS = 4
SAMPLE_DIVERSE_DOCS = 4
SAMPLE_DOC_SNIPPET_CHARS = 300
TAG_MERGE_AUTO = 0.85        # >= : merge silently
TAG_MERGE_GRAY_LOW = 0.60    # [0.60, 0.85) : LLM adjudicates -> dashboard approval
MULTILABEL_SIMILARITY = 0.60
NOISE_RESCUE_SIMILARITY = 0.50
CONFIDENCE_AUTO_APPLY = 0.70
MAX_TAGS_PER_NOTE = 3
RANDOM_SEED = 42
```
Create `app/services/agent/constants.py`:
```python
COVERAGE_SIM_THRESHOLD = 0.45
COVERAGE_MIN_NOTES = 3
NOVELTY_MIN_RATIO = 0.34
QUERY_MAX_CHARS = 200
MAX_QUERIES_PER_STEP = 3
TOOL_RETRIES = 2
STEP_TIMEOUT_SECONDS = 60
MAX_COLLECTED_NOTES = 40
```
Add `tests/test_env_frozen.py`: store `sha256(.env.example)` as a constant in the test; test fails if the hash changes (message: "config is frozen — use constants.py").

## Checkpoint
Both modules import. `pytest tests/test_env_frozen.py` passes. `git diff .env.example` empty.

## Commit
`task 01: add constants modules and frozen-config guard`
Delete this file in the same commit.
