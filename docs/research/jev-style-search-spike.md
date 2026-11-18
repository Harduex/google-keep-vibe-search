# RM-01 · Evaluate local Jev-style decisions for search

Determine whether a locally runnable typed decision model can help people find more relevant notes in search or chat within a 12 GiB GPU memory budget. A Jev-style model scores predefined choices or propositions given evidence. TypeSafe AI's hosted Jev is a reference for the interface. [TypeSafe AI documentation](https://docs.typesafe.ai/introduction)

## Candidates and use cases

- Check [OpenJev](https://github.com/razorback16/openjev), [Bongard Mini](https://huggingface.co/AgentBull/bongard-mini), and a small open model scored by option logits as described in [Releasing the Inner Jev](https://arxiv.org/abs/2610.17205). Verify the license for code and weights, text and Bulgarian support, and local runtime and memory requirements before selecting one or two candidates. Test a compatible decision checkpoint through [LM Studio's local System One endpoint](https://lmstudio.ai/docs/developer/jev-compat/systemone) if it simplifies serving.
- Start with relevance reranking over the same retrieved candidates. Compare against the current cross-encoder and a simple score-fusion control. Keep the original query and ranker available as a fallback.
- If reranking leaves a clear opportunity, test one decision at a time for agent routing, choosing between supplied query rewrites, or deciding whether to continue gathering evidence. Keep user-selected tags and date filters binding. The existing LLM still generates wording and answers.
- Record other uses such as citation-support checks or tag suggestions as hypotheses. Consider embedding replacements only as a separate ablation with a multilingual embedding baseline.

## Evidence and decision

1. Freeze the current retrieval configuration, candidate pool, and held-out query set before testing. Reuse [the retrieval evaluations](../../bench/README.md) and their metrics. Include labeled synthetic English, Bulgarian, and mixed-language queries with exact matches, paraphrases, filters, hard negatives, and questions with no answer. Use public benchmark corpora for additional comparisons. Keep the real export and cache outside the experiment and call `bench.assert_cache_isolated()` before running a benchmark.
2. Compare variants on the same queries. Report Recall@10, nDCG@10, and MRR overall and by language and query type, plus p95 latency and peak VRAM. For agent changes, also report evidence recall, unsupported-answer rate, valid citations, and retrieval steps. If using a confidence threshold, calibrate it on a separate set and record abstentions and fallbacks.
3. Pre-register the improvement target and uncertainty analysis. Recommend adoption only if the candidate improves a declared user outcome and search quality does not decline overall or on an evaluated language or query slice. Treat inconclusive slices, filter violations, and regressions on known must-find queries as a reason to keep the existing path.
4. Record a reproducible go/no-go decision with model revisions, runtime settings, paired results, and failure categories. Keep results free of note text and prompts. A positive spike supports a separate implementation decision.
