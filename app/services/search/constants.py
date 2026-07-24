# Cross-encoder candidate window: how many top fused (RRF) results get sent through the
# reranker. Larger = better recall/precision from the cross-encoder but higher per-query
# latency (the cross-encoder does one forward pass per candidate). Notes beyond this
# window are appended after reranking in their original fused-RRF order, so `max_results`
# (e.g. MAX_RESULTS=300) is never truncated down to this window's size.
RERANK_CANDIDATE_WINDOW = 50
