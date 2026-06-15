# =============================================================================
# Makefile - unified task interface for lenreg-ticket-bot
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
#   make apply-heuristics      - Apply city heuristic to patients
#   make apply-heuristic-types - Apply heuristic types to doctors
# =============================================================================

POETRY := python -m poetry

.PHONY: install lint format test check run clean lock verify-pyproject apply-heuristics apply-heuristic-types seed-db

install:
	$(POETRY) install
	npm install
	python -m pre_commit install

lint:
	python -m ruff check src
	python -m mypy src
	npx markdownlint "specs/**/*.md" ".roo/**/*.md" "*.md"

format:
	python -m ruff format src
	npx prettier --write "specs/**/*.md" ".roo/**/*.md" "*.md"

test:
	python -m pytest tests/ -v

# Full CI cycle: lint + format check + test
check:
	python -m ruff check src
	python -m mypy src
	npx markdownlint "specs/**/*.md" ".roo/**/*.md" "*.md"
	python -m ruff format --check src
	npx prettier --check "specs/**/*.md" ".roo/**/*.md" "*.md"
	python -m pytest tests/ -v

run:
	python -m src.main

# Platform detection for clean target (Windows PowerShell vs Unix)
ifeq ($(OS),Windows_NT)
CLEAN_CACHE_DIRS  = powershell -NoProfile -Command "Remove-Item -Recurse -Force -Path __pycache__, .pytest_cache, .mypy_cache, .ruff_cache, logs -ErrorAction SilentlyContinue"
CLEAN_PYCACHE_ALL = powershell -NoProfile -Command "Get-ChildItem -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue"
CLEAN_PYC         = powershell -NoProfile -Command "Get-ChildItem -Recurse -Filter *.pyc | Remove-Item -Force -ErrorAction SilentlyContinue"
CLEAN_DB          = powershell -NoProfile -Command "Remove-Item -Force -Path data/*.db -ErrorAction SilentlyContinue"
CLEAN_TMP         = powershell -NoProfile -Command "Remove-Item -Force -Path .tmp_* -ErrorAction SilentlyContinue"
else
CLEAN_CACHE_DIRS  = rm -rf __pycache__ .pytest_cache .mypy_cache .ruff_cache logs
CLEAN_PYCACHE_ALL = find . -type d -name __pycache__ -exec rm -rf {} +
CLEAN_PYC         = find . -type f -name '*.pyc' -delete
CLEAN_DB          = rm -f data/*.db
CLEAN_TMP         = rm -f .tmp_*
endif

clean:
	$(CLEAN_CACHE_DIRS)
	$(CLEAN_PYCACHE_ALL)
	$(CLEAN_PYC)
	$(CLEAN_DB)
	$(CLEAN_TMP)

lock:
	$(POETRY) lock

verify-pyproject:
	$(POETRY) check

apply-heuristics:
	python scripts/apply_city_heuristic.py

apply-heuristic-types:
	python scripts/apply_heuristic_types.py

seed-db:
	docker compose exec bot python scripts/seed_data.py data/bot.db data/seed/clinics_doctors.json --force
