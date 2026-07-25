.PHONY: bench-fetch bench bench-compare bench-accept

# Tier-2 benchmarks: real models over real corpora. Minutes and a GPU, so these are
# deliberately NOT part of `make check` or CI (see bench/README.md).

bench-fetch:
	@echo "=== Fetching benchmark corpora ==="
	uv run python -c "from bench.corpora import fetch_all; fetch_all()"

bench:
	@echo "=== Retrieval signal ablation ==="
	GOOGLE_KEEP_PATH=. uv run python -m bench.run_retrieval
	@echo "=== Tagging quality ==="
	GOOGLE_KEEP_PATH=. uv run python -m bench.run_tagging

bench-compare:
	@echo "=== Benchmarks vs committed baselines ==="
	GOOGLE_KEEP_PATH=. uv run python -m bench.compare

bench-accept:
	@echo "=== Promoting the current run to the baseline ==="
	GOOGLE_KEEP_PATH=. uv run python -m bench.accept
