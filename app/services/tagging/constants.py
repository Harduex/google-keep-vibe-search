UMAP_N_COMPONENTS = 10
UMAP_N_NEIGHBORS = 15
UMAP_MIN_DIST = 0.0
HDBSCAN_MIN_CLUSTER_SIZE = 12
HDBSCAN_MIN_SAMPLES = 5
SAMPLE_CENTRAL_DOCS = 4
SAMPLE_DIVERSE_DOCS = 4
SAMPLE_DOC_SNIPPET_CHARS = 300
TAG_MERGE_AUTO = 0.85  # >= : merge silently
TAG_MERGE_GRAY_LOW = 0.60  # [0.60, 0.85) : LLM adjudicates -> dashboard approval
MULTILABEL_SIMILARITY = 0.60
NOISE_RESCUE_SIMILARITY = 0.50
CONFIDENCE_AUTO_APPLY = 0.70
MAX_TAGS_PER_NOTE = 3
# Keep a label only if the note scores at least this fraction of its OWN best match.
# An absolute threshold alone cannot separate "this note belongs to several topics" from
# "this note is vaguely near everything": raising it to shed weak matches orphans the
# notes that sit between clusters, and lowering it to rescue those orphans re-floods the
# well-matched notes with tags. This is relative, so each note is judged against itself.
# 1.0 = only ties with the best match; 0.0 = disabled (cap alone decides).
RELATIVE_TAG_MARGIN = 0.85
# Absolute floor for the orphan rescue below. A note that clears no per-label threshold
# gets its single best label if it reaches this, instead of falling into Uncategorized.
# Lower it to shrink the uncategorized share, at the cost of weaker tags; the notes it
# newly catches are, by definition, the ones nothing matched well.
ASSIGNMENT_FLOOR = 0.45
RANDOM_SEED = 42

# When True, consolidation stops *applying* merges and proposes them instead: every pair
# the pipeline wanted to merge becomes an approve/reject card, so rejecting one is a real
# per-merge opt-out. Default False, which keeps the historical behaviour exactly — most
# merges are applied during the run (>= TAG_MERGE_AUTO silently, and gray-zone pairs once
# the LLM adjudicates them), and only the leftovers reach the user as cards.
MERGE_REQUIRES_APPROVAL = False
