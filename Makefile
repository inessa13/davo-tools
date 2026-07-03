# Run from repository root (see shared agent policy: no `make -C`).
VENV ?= .venv
UV ?= uv
LINT_PATH ?= davo tests
LIB_TEST_PYTHONS ?= 3.8 3.9 3.10 3.11 # 3.12 3.13 3.14
# Prefer PYTHON from env / command line; else .venv if present; else python3 on PATH.
PY = $(if $(strip $(PYTHON)),$(PYTHON),$(shell test -x $(CURDIR)/$(VENV)/bin/python && echo "$(CURDIR)/$(VENV)/bin/python" || echo python3))

.PHONY: help test tests test-lib venv coverage lint

help:
	@echo "davo-tools — Make targets"
	@echo ""
	@echo "  make help      — this message (default when you run \`make\` with no goal)"
	@echo "  make venv      — create virtualenv at VENV ($(VENV)) and pip install -e \".[test,lint]\""
	@echo "                  uses $(UV) when on PATH, else python3 -m venv + pip"
	@echo "  make test      — run pytest (alias: make tests)"
	@echo "  make test-lib  — install Python $(LIB_TEST_PYTHONS) with uv and run tests for each version"
	@echo "  make coverage  — pytest with coverage for package \`davo\` (terminal table + htmlcov/)"
	@echo "  make lint      — ruff check, isort --check-only, pylint (default: davo tests)"
	@echo "                  use LINT_PATH to lint a specific path, e.g. make lint LINT_PATH=davo/services/photo/pdf.py"
	@echo ""
	@echo "Variables:  VENV=$(VENV)   UV=$(UV)   PY=$(PY)   LINT_PATH=$(LINT_PATH)"
	@echo "            LIB_TEST_PYTHONS=$(LIB_TEST_PYTHONS)"

test:
	$(PY) -m pytest

test-lib:
	@if ! command -v "$(UV)" >/dev/null 2>&1; then \
		echo "Error: \`$(UV)\` is required for test-lib target" >&2; \
		exit 1; \
	fi
	@status=0; \
	"$(UV)" python install $(LIB_TEST_PYTHONS) || exit $$?; \
	for py in $(LIB_TEST_PYTHONS); do \
		venv=".venv-lib-$$py"; \
		echo ""; \
		echo "==> [$$py] creating $$venv"; \
		if ! "$(UV)" venv "$$venv" -p "$$py" -c ; then \
			status=1; \
			continue; \
		fi; \
		echo "==> [$$py] installing test dependencies"; \
		if ! "$(UV)" pip install --python "$$venv/bin/python" -e ".[test]" -q ; then \
			status=1; \
			continue; \
		fi; \
		echo "==> [$$py] running tests"; \
		if ! "$$venv/bin/python" -m pytest -p no:warnings ; then \
			status=1; \
		fi; \
		rm -rf "$$venv"; \
	done; \
	exit $$status

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
