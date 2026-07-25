# Benchmarks (tier 2)

Real models over real corpora, to answer questions the unit suite cannot: *does each
retrieval signal earn its place, and did tagging get better or just more stable?*

Tier 1 is `scripts/eval_retrieval.py` (`make eval-retrieval`) — the same ablation over the
30 synthetic fixture notes with stubs, fast and deterministic, suitable for every change.
Tier 2 is this directory, and it is deliberately not part of `make check` or CI.

## Commands

| Command | What it does |
|---|---|
| `make bench-fetch` | Downloads SciFact (~3 MB) and 20 Newsgroups. Run once. |
| `make bench` | Runs both suites and prints the tables. Writes `bench/.run/*.json`. |
| `make bench-compare` | Runs both suites, then diffs against `bench/baselines/`. Non-zero on regression. |
| `make bench-accept` | Promotes the current run to the baseline. Never called by the other targets. |

Sample sizes are capped for runtime and can be overridden: `BENCH_DOCS`,
`BENCH_QUERIES`, `BENCH_SEED`. A baseline records the sample it was taken at, and
`compare.py` refuses to compare runs whose samples differ — the numbers are not
comparable across sample sizes.

## What the numbers mean, and do not mean

- **Domain shift.** Medical abstracts and newsgroup posts are not personal notes. This
  measures the engine: *deltas transfer, absolute numbers do not.* Every report prints
  this line in its header.
- **Not a CI gate.** Real models want a GPU and minutes. Never wire these into
  `make check`.
- **Gameable.** Tuning the pipeline to maximise NMI on 20 Newsgroups could easily make
  tagging worse on personal notes. The baseline is a **tripwire and an ablation tool, not
  an optimisation target.**
- **Grouping, not naming.** `run_tagging.py` scores the clusters, not the tag names: this
  corpus has no ground-truth names to score against, so the LLM is never called and
  `llm_calls` is 0 by construction.
- **decomposition and CRAG are not measured.** Both need an LLM call per query; the
  ablation reports them as skipped rather than folding them in silently. `full` is
  therefore equal to `plus_rerank` in this configuration.

## No baseline is committed yet

The baselines this directory shipped with were **placeholders** — hand-written round
numbers that the runners then reproduced verbatim, so `compare.py` compared constants to
themselves and could never fail. They have been deleted along with the stub runners.

`make bench-compare` now exits non-zero when there is nothing to compare against, because
an unmeasured run is not a passing run. To establish a real baseline: run `make bench`,
read the tables, and if they look right run `make bench-accept` and commit the two
baseline files on their own, with the reason and the machine in the commit message.

## Privacy

`bench/__init__.py` refuses to import when `GOOGLE_KEEP_PATH` points at anything other
than `.`, and the runners write only into `bench/.run/` (gitignored). No benchmark ever
touches the real export or `cache/`.
