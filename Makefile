# One documented command to run the application: `make dev`.
# Everything else here is a quality gate that CI runs identically.

VENV := .venv
PY := $(VENV)/bin/python
BACKEND := backend
FRONTEND := frontend

.DEFAULT_GOAL := help
.PHONY: help install install-backend install-frontend lint typecheck test check contract findings lock lock-check dev clean

help: ## Show the available targets
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk -F':.*?## ' '{printf "  \033[1m%-18s\033[0m %s\n", $$1, $$2}'

install: install-backend install-frontend ## Install both halves

install-backend: ## Install the back end from the committed lockfile
	@command -v uv >/dev/null || { echo "uv is required: https://docs.astral.sh/uv/"; exit 1; }
# --locked fails rather than re-resolving if backend/uv.lock disagrees with
# pyproject.toml, so a dependency change cannot land without its lockfile.
# UV_PROJECT_ENVIRONMENT keeps the virtualenv at the repository root, where
# every other target already expects it.
	UV_PROJECT_ENVIRONMENT=$(CURDIR)/$(VENV) uv sync --project $(BACKEND) --extra dev --locked

install-frontend: ## Install the front end, once it exists
	@if [ -f $(FRONTEND)/package.json ]; then \
	  cd $(FRONTEND) && npm install; \
	else \
	  echo "skip: $(FRONTEND)/package.json does not exist yet (lands in P15)"; \
	fi

lint: ## Lint and format-check both halves
	$(VENV)/bin/ruff check $(BACKEND)
	$(VENV)/bin/ruff format --check $(BACKEND)
	@if [ -f $(FRONTEND)/package.json ]; then cd $(FRONTEND) && npm run lint; fi

typecheck: ## Type-check both halves
	cd $(BACKEND) && ../$(VENV)/bin/mypy
	@if [ -f $(FRONTEND)/package.json ]; then cd $(FRONTEND) && npm run typecheck; fi

test: ## Run both test suites
	cd $(BACKEND) && ../$(VENV)/bin/pytest
	@if [ -f $(FRONTEND)/package.json ]; then cd $(FRONTEND) && npm test -- --run; fi

check: lock-check lint typecheck test ## Everything CI runs

lock: ## Re-resolve backend/uv.lock after editing dependencies
	cd $(BACKEND) && uv lock

lock-check: ## Fail if the lockfile and pyproject.toml disagree
	cd $(BACKEND) && uv lock --check

contract: ## Regenerate the wire contract and its fixtures
	$(VENV)/bin/python scripts/export_contract.py
	$(VENV)/bin/python scripts/make_fixtures.py

findings: ## Regenerate docs/findings.md from the real input files
	$(PY) scripts/findings.py

dev: ## Run the API and the front end together (the one documented command)
	@echo "dev target lands in P19, once both halves exist"

clean: ## Remove build and cache artefacts
	rm -rf $(VENV) $(FRONTEND)/node_modules $(FRONTEND)/dist
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	rm -rf .mypy_cache .ruff_cache .pytest_cache
