SHELL := /bin/bash
NVM_SOURCE = [ -s "$$HOME/.nvm/nvm.sh" ] && . "$$HOME/.nvm/nvm.sh" && nvm install 20 && nvm use 20

.PHONY: setup dev dev-backend dev-frontend test lint build

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

lint:
	@echo "=== Linting/Formatting Python backend ==="
	uv run black app tests
	uv run isort app tests
	@echo "=== Linting Node frontend ==="
	cd client && $(NVM_SOURCE) && npm run lint

build:
	@echo "=== Building Node frontend ==="
	cd client && $(NVM_SOURCE) && npm run build

eval:
	@echo "=== Evaluating Categorization Pipeline ==="
	uv run python scripts/eval_categorization.py
