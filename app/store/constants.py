"""Hardcoded tuning constants for the store.

Per ``EXECUTION-PROTOCOL.md`` §5 (frozen configuration) no env vars are added;
each constant here carries a one-line trade-off comment so a future reader can
see what it trades off without grepping the proposal.
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
