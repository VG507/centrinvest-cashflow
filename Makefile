.PHONY: help install test test-backend test-frontend build eval clean

VENV ?= backend/.venv
PYTHON := $(shell [ -f $(VENV)/bin/python ] && echo $(VENV)/bin/python || (command -v python3 2>/dev/null || echo python3))
PYTEST := $(shell [ -f $(VENV)/bin/pytest ] && echo $(VENV)/bin/pytest || (command -v pytest 2>/dev/null || echo pytest))

help:
	@echo "Bank «Center-invest» Cash Flow Intelligence Platform"
	@echo ""
	@echo "Available commands:"
	@echo "  make install        Install backend and frontend dependencies"
	@echo "  make test           Run full test suite (151 backend + 29 frontend tests)"
	@echo "  make test-backend   Run 151 backend regression and verification tests"
	@echo "  make test-frontend  Run 29 frontend unit tests"
	@echo "  make build          Compile production frontend bundle"
	@echo "  make eval           Execute benchmark evaluation on reference statement"
	@echo "  make clean          Remove build caches and temporary artifacts"

install:
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install --upgrade pip
	$(VENV)/bin/pip install -e "backend/.[dev]"
	cd frontend && npm ci

test: test-backend test-frontend

test-backend:
	PYTHONPATH=backend $(PYTEST) backend/tests/

test-frontend:
	cd frontend && npm test

build:
	cd frontend && npm run build

eval:
	PYTHONPATH=backend $(PYTHON) scripts/evaluate_control_dataset.py --file fixtures/statements/C001_logistics.csv

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf frontend/dist frontend/.vite .coverage coverage/ data/control_audit_summary.json
