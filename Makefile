# =============================================================================
# Makefile - unified task interface for zdrav.lenreg
# =============================================================================
# This Makefile delegates to PowerShell on Windows; on Linux/macOS it runs
# the commands directly via Poetry.
#
# Usage:
#   make install      - Install all dependencies (Poetry + npm + pre-commit)
#   make lint         - Run all linters (ruff, mypy, markdownlint)
#   make format       - Auto-format code and markdown
#   make test         - Run pytest
#   make check        - Full CI cycle: lint + format(check) + test
#   make run          - Start the bot
#   make clean        - Remove cache/temp directories
#   make lock         - Regenerate poetry.lock
#   make verify-pyproject - Validate pyproject.toml (Poetry check)
# =============================================================================

POETRY := python -m poetry

.PHONY: install lint format test check run clean lock verify-pyproject

install:
	$(POETRY) install
	npm install
	python -m pre_commit install

lint:
	python -m ruff check src
	python -m mypy src
	npx markdownlint "docs/**/*.md" ".roo/**/*.md" "*.md"

format:
	python -m ruff format src
	npx prettier --write "docs/**/*.md" ".roo/**/*.md" "*.md"

test:
	python -m pytest tests/ -v

# Full CI cycle: lint + format check + test
check:
	python -m ruff check src
	python -m mypy src
	npx markdownlint "docs/**/*.md" ".roo/**/*.md" "*.md"
	python -m ruff format --check src
	npx prettier --check "docs/**/*.md" ".roo/**/*.md" "*.md"
	python -m pytest tests/ -v

run:
	python -m src.main

clean:
	rm -rf __pycache__ .pytest_cache .mypy_cache .ruff_cache
	find src -type d -name __pycache__ -exec rm -rf {} +
	find tests -type d -name __pycache__ -exec rm -rf {} +

lock:
	$(POETRY) lock

verify-pyproject:
	$(POETRY) check
