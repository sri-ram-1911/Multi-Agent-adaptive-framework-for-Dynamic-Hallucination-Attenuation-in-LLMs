.DEFAULT_GOAL := help
COMPOSE := docker compose
API := $(COMPOSE) exec -T api

.PHONY: help up up-obs down logs build migrate seed bootstrap-models train-models test lint fmt eval shell frontend-dev

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

.env: ## Create .env from the template if missing
	@test -f .env || (cp .env.example .env && echo "created .env — set OPENAI_API_KEY")

up: .env ## Start core stack (db, redis, api, frontend)
	$(COMPOSE) up -d --build
	$(MAKE) migrate

up-obs: .env ## Start core stack + observability (prometheus, grafana, otel-collector)
	$(COMPOSE) --profile obs up -d --build
	$(MAKE) migrate

down: ## Stop everything
	$(COMPOSE) --profile obs down

logs: ## Tail api logs
	$(COMPOSE) logs -f api

build: ## Rebuild images
	$(COMPOSE) build

migrate: ## Run DB migrations
	$(API) alembic upgrade head

seed: ## Load sample corpus + benchmark
	$(API) python -m scripts.seed_kb
	$(API) python -m scripts.seed_benchmark

bootstrap-models: ## Download HF models + train sklearn artifacts
	$(API) python -m scripts.bootstrap_models

train-models: ## (Re)train ML artifacts only
	$(API) python -m app.ml.train_risk_model
	$(API) python -m app.ml.train_claim_type_clf
	$(API) python -m app.ml.train_source_quality
	$(API) python -m app.ml.train_policy

test: ## Run backend test suite
	$(API) pytest -q

demo: ## Deterministic offline demo (no DB / network / models)
	cd backend && python -m scripts.demo --mock

demo-real: ## Real ML/DL demo — local models, no DB, no API key (first run downloads ~1.7GB)
	cd backend && python -m scripts.demo --real

lint: ## Ruff + mypy
	$(API) ruff check app scripts tests
	$(API) mypy app

fmt: ## Ruff format
	$(API) ruff format app scripts tests

eval: ## Run evaluation harness (MA-AHAF vs baseline)
	$(API) python -m scripts.run_eval --dataset data/benchmark/benchmark.jsonl

shell: ## Shell into api container
	$(COMPOSE) exec api bash

frontend-dev: ## Run the dashboard in dev mode (host)
	cd frontend && npm install && npm run dev
