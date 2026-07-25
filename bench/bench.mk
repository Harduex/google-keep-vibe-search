.PHONY: bench-fetch

bench-fetch:
	@echo "=== Fetching benchmark corpora ==="
	uv run python -c "from bench.corpora import fetch_all; fetch_all()"
