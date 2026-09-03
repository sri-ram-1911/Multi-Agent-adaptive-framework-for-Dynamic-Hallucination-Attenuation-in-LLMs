.DEFAULT_GOAL := help
COMPOSE := docker compose
API := $(COMPOSE) exec -T api

.PHONY: help up up-obs down logs build migrate seed bootstrap-models train-models test lint fmt eval eval-local eval-openai capture dashboard-openai retrain finalize-report demo demo-real shell frontend-dev

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

eval: ## Run evaluation harness in the Docker stack (MA-AHAF vs baseline)
	$(API) python -m scripts.run_eval --dataset data/benchmark/benchmark.jsonl

eval-local: ## Run evaluation with NO Postgres (local corpus + configured provider)
	cd backend && python -m scripts.eval_local --limit 40

eval-openai: ## Full 77-item eval on gpt-4o-mini (needs OPENAI_API_KEY in backend/.env)
	cd backend && MAAHAF_LLM__PROVIDER=openai python -m scripts.eval_local --limit 77 --timeout 180

capture: ## Write 5 real gpt-4o-mini traces to demo_traces.json
	cd backend && MAAHAF_LLM__PROVIDER=openai MAAHAF_MAX_REVISION_LOOPS=1 python -m scripts.capture_traces

dashboard-openai: ## Serve the dashboard running the pipeline on gpt-4o-mini
	cd backend && MAAHAF_LLM__PROVIDER=openai python -m scripts.serve_demo

retrain: ## Retrain risk_model + calibrator from the latest eval run's labels
	cd backend && python -m app.ml.retrain_from_eval

finalize-report: ## Fill docs/final-report.md section 4 from the latest eval + retrain
	cd backend && python -m scripts.finalize_report

shell: ## Shell into api container
	$(COMPOSE) exec api bash

frontend-dev: ## Run the dashboard in dev mode (host)
	cd frontend && npm install && npm run dev
