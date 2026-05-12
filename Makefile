# Run from repository root (see shared agent policy: no `make -C`).
VENV ?= .venv
UV ?= uv
LINT_PATH ?= davo tests
# Prefer PYTHON from env / command line; else .venv if present; else python3 on PATH.
PY = $(if $(strip $(PYTHON)),$(PYTHON),$(shell test -x $(CURDIR)/$(VENV)/bin/python && echo "$(CURDIR)/$(VENV)/bin/python" || echo python3))

.PHONY: help test tests venv coverage lint

help:
	@echo "davo-tools — Make targets"
	@echo ""
	@echo "  make help      — this message (default when you run \`make\` with no goal)"
	@echo "  make venv      — create virtualenv at VENV ($(VENV)) and pip install -e \".[test,lint]\""
	@echo "                  uses $(UV) when on PATH, else python3 -m venv + pip"
	@echo "  make test      — run pytest (alias: make tests)"
	@echo "  make tests     — same as make test"
	@echo "  make coverage  — pytest with coverage for package \`davo\` (terminal table + htmlcov/)"
	@echo "  make lint      — ruff check, isort --check-only, pylint (default: davo tests)"
	@echo "                  use LINT_PATH to lint a specific path, e.g. make lint LINT_PATH=davo/services/photo/pdf.py"
	@echo ""
	@echo "Variables:  VENV=$(VENV)   UV=$(UV)   PYTHON=$(if $(strip $(PYTHON)),$(PYTHON),<unset>)   LINT_PATH=$(LINT_PATH)"

test tests:
	$(PY) -m pytest

coverage:
	$(PY) -m pytest \
		-W ignore \
		--disable-warnings \
		--cov=davo \
		--cov-branch \
		--cov-report=term \
		--cov-report=html

lint:
	@status=0; \
	$(PY) -m ruff check $(LINT_PATH) || status=$$?; \
	$(PY) -m isort --check-only --diff $(LINT_PATH) || status=$$?; \
	$(PY) -m pylint $(LINT_PATH) || status=$$?; \
	exit $$status

venv:
	@if command -v "$(UV)" >/dev/null 2>&1; then \
		"$(UV)" venv "$(VENV)"; \
		"$(UV)" pip install --python "$(CURDIR)/$(VENV)/bin/python" -e ".[test,lint]"; \
	else \
		echo "Note: install uv for faster venv+install (https://docs.astral.sh/uv/getting-started/installation/)" >&2; \
		python3 -m venv "$(VENV)"; \
		"$(VENV)/bin/pip" install -U pip; \
		"$(VENV)/bin/pip" install -e ".[test,lint]"; \
	fi
