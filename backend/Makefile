# =============================================================================
# Ask La Trobe Policy DB Chatbot — developer commands
# =============================================================================

.DEFAULT_GOAL := help

# ─── Meta ───────────────────────────────────────────────────────────────
.PHONY: help
help: ## Show this help
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ─── Local dev (no Docker) ──────────────────────────────────────────────
.PHONY: install
install: ## Install Python deps into the current venv
	pip install -r requirements.txt

.PHONY: test
test: ## Run the test suite
	pytest

.PHONY: test-fast
test-fast: ## Run tests without coverage (faster)
	pytest --no-header -q --override-ini="addopts=-ra --strict-markers --strict-config --tb=short"
	
.PHONY: lint
lint: ## Run ruff linter
	ruff check app tests

.PHONY: format
format: ## Format code with ruff
	ruff format app tests

.PHONY: typecheck
typecheck: ## Run mypy
	mypy app

.PHONY: dev
dev: ## Run the API locally (reload)
	uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

.PHONY: frontend
frontend: ## Serve the frontend locally
	cd ../frontend && python -m http.server 5500

# ─── Database ───────────────────────────────────────────────────────────
.PHONY: db-create
db-create: ## Create the SQLite database
	python -m scripts.create_database

.PHONY: db-seed
db-seed: ## Seed test users
	python -m scripts.seed_users

.PHONY: ingest
ingest: ## Ingest all policies
	python -m scripts.ingest_policies

.PHONY: db-reset
db-reset: ## Wipe and recreate the local DB (destructive)
	rm -f storage/app.db
	rm -rf storage/qdrant storage/qdrant_test
	$(MAKE) db-create
	$(MAKE) db-seed

# ─── Docker ─────────────────────────────────────────────────────────────
.PHONY: docker-build
docker-build: ## Build the backend image
	docker build -t policy-db-chatbot-api:latest .

.PHONY: docker-up
docker-up: ## Start the full prod-like stack
	docker compose up -d

.PHONY: docker-down
docker-down: ## Stop the full stack
	docker compose down

.PHONY: docker-logs
docker-logs: ## Tail backend logs
	docker compose logs -f api

.PHONY: docker-dev
docker-dev: ## Start the lightweight dev stack
	docker compose -f docker-compose.dev.yml up -d

.PHONY: docker-dev-down
docker-dev-down: ## Stop the dev stack
	docker compose -f docker-compose.dev.yml down

.PHONY: docker-dev-logs
docker-dev-logs: ## Tail dev stack logs
	docker compose -f docker-compose.dev.yml logs -f api

.PHONY: docker-shell
docker-shell: ## Open a shell in the running API container
	docker compose exec api /bin/sh

.PHONY: docker-nuke
docker-nuke: ## Stop the stack and remove all volumes (DESTRUCTIVE)
	docker compose down -v