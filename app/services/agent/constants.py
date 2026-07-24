COVERAGE_SIM_THRESHOLD = 0.45
COVERAGE_MIN_NOTES = 3
NOVELTY_MIN_RATIO = 0.34
QUERY_MAX_CHARS = 500
MAX_QUERIES_PER_STEP = 5
TOOL_RETRIES = 3
STEP_TIMEOUT_SECONDS = 60
MAX_COLLECTED_NOTES = 250
# Cross-encoder candidate window for agent-mode context assembly: how many of the notes the
# agent collected get scored by the cross-encoder before the set is capped to
# `chat_context_notes`. Larger = better final ordering but one cross-encoder forward pass per
# candidate, paid on every agent-mode chat turn.
AGENT_RERANK_CANDIDATE_WINDOW = 20
