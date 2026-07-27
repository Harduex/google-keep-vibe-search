"""Hardcoded tuning constants for the store.

These are deliberately hardcoded rather than exposed as environment variables:
they are internal tuning knobs, not deployment configuration. Each one carries a
one-line comment saying what it trades off, so a future reader can retune it
without having to reverse-engineer the intent.
"""

# SQLite schema version. Bump on any breaking schema change; a migration reads
# this from ``index_state`` to decide whether it needs to run.
SCHEMA_VERSION = 1

# When the ratio of free rows to capacity in a VectorStore exceeds this, a
# compaction pass rewrites the ``.npy`` with only live rows. Higher = fewer
# rewrites but more wasted address space; lower = tighter footprint but more
# write churn on a churny corpus.
COMPACTION_FREE_RATIO = 0.5

# Initial row capacity for a fresh VectorStore matrix. Small corpora stay
# tight; capacity doubles on demand, so 5k docs is ~7 doublings from 64.
VECTOR_INITIAL_CAPACITY = 64
