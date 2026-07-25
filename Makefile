SHELL := /bin/bash
# Pin node 20 via nvm when nvm is installed. When it is not (CI runners get node from
# actions/setup-node, on PATH, with no nvm), this is a no-op instead of a failure: the old
# `[ -s ... ] && ...` chain returned exit 1 when the file was missing, which failed the make
# recipe line before npm/tsc ever ran. A real nvm error still propagates — this is not `|| true`.
NVM_SOURCE = if [ -s "$$HOME/.nvm/nvm.sh" ]; then . "$$HOME/.nvm/nvm.sh" && nvm install 20 && nvm use 20; fi

.PHONY: setup dev dev-backend dev-frontend test lint format check build eval eval-retrieval

setup:
	@echo "=== Setting up Python backend ==="
	uv sync --all-groups
	@echo "=== Setting up Node frontend ==="
	cd client && $(NVM_SOURCE) && npm ci
	@if [ ! -f .env ]; then \
		echo "Creating .env from .env.example..."; \
		cp .env.example .env; \
		echo "IMPORTANT: Edit .env and set GOOGLE_KEEP_PATH to your Google Keep export folder."; \
	fi
	@echo "=== Installing git hooks ==="
	uv run pre-commit install

dev:
	@echo "Starting backend and frontend..."
	bash scripts/dev.sh

dev-backend:
	uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

dev-frontend:
	cd client && $(NVM_SOURCE) && npm run dev

test:
	@echo "=== Testing Python backend ==="
	GOOGLE_KEEP_PATH=. uv run pytest
	@echo "=== Testing Node frontend ==="
	cd client && $(NVM_SOURCE) && npm run test

# Mutating: rewrites files in place. Do not use to satisfy the `make check` gate.
format:
	@echo "=== Formatting Python backend ==="
	uv run black app tests
	uv run isort app tests
	@echo "=== Formatting/Linting Node frontend ==="
	cd client && $(NVM_SOURCE) && npm run fix

# Non-mutating: the CI/checkpoint gate. Never writes to the tree.
check:
	@echo "=== Checking Python formatting ==="
	uv run black --check app tests
	uv run isort --check-only app tests
	@echo "=== Linting Node frontend ==="
	cd client && $(NVM_SOURCE) && npm run lint
	@echo "=== Type-checking Node frontend ==="
	cd client && $(NVM_SOURCE) && npx tsc -b
	@echo "=== Testing Python backend ==="
	GOOGLE_KEEP_PATH=. uv run pytest
	@echo "=== Testing Node frontend ==="
	cd client && $(NVM_SOURCE) && npm run test

# Alias so the old habit fails loudly (non-zero exit) instead of silently rewriting files.
lint: check

build:
	@echo "=== Building Node frontend ==="
	cd client && $(NVM_SOURCE) && npm run build

eval:
	@echo "=== Evaluating Categorization Pipeline ==="
	PYTHONPATH=. GOOGLE_KEEP_PATH=. uv run python scripts/eval_categorization.py

# Tier-1 retrieval ablation over the synthetic fixture corpus: fast, deterministic, safe to
# run on every change. Tier 2 (real models, real corpora) lives in bench/ — see bench/README.md.
eval-retrieval:
	@echo "=== Evaluating Retrieval Signals (fixture corpus) ==="
	PYTHONPATH=. GOOGLE_KEEP_PATH=. uv run python scripts/eval_retrieval.py

-include bench/bench.mk
