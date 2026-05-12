# Project Instructions

This file contains foundational instructions, architecture rules, and workflows for the `zdrav.lenreg` project. All Python and Markdown standards are defined in `.roo/rules/system_standards.md`.

## Architecture

- **Entry point:** [`src/main.py`](src/main.py) — сборка бота aiogram, запуск фоновых задач, graceful shutdown.
- **Configuration:** [`src/config.py`](src/config.py) — pydantic-settings из `.env` + переопределение из БД (таблица `config`).
- **API client:** [`src/api/zdrav_client.py`](src/api/zdrav_client.py) — httpx-клиент с rate limiting, retry, ротацией User-Agent.
- **Database:** SQLite (WAL-режим) через `aiosqlite`. [`src/database/database.py`](src/database/database.py) — ядро, [`src/database/manager.py`](src/database/manager.py) — in-memory кэш, [`src/database/doctor_manager.py`](src/database/doctor_manager.py) — кэш врачей.
- **Conventions:** абсолютные импорты с префиксом `src.`, все стандарты — в [`.roo/rules/`](.roo/rules/).

## Agent Rules

- **Перед анализом структуры проекта** — прочитать [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).
- **Перед завершением сессии** — обновить [`docs/agents/SESSION_LOG.md`](docs/agents/SESSION_LOG.md) и [`docs/agents/AGENT_TASKS.md`](docs/agents/AGENT_TASKS.md).
- **API-данные** сохранять в [`docs/knowledge/`](docs/knowledge/), поддерживать актуальность [`docs/knowledge/_INDEX.md`](docs/knowledge/_INDEX.md).
- **Игнорировать:** `.venv/`, `__pycache__/`, `.history/`, `.vscode/`, `logs/`, `data/`, `.pytest_cache/`, `.git/`.
- **Конфиденциальные данные** — только в `.env`.

## Key Files

| File                                                               | Purpose                        |
| ------------------------------------------------------------------ | ------------------------------ |
| [`.roo/rules/system_standards.md`](.roo/rules/system_standards.md) | Python + Markdown standards    |
| [`.roo/rules/coding.md`](.roo/rules/coding.md)                     | Coding conventions             |
| [`.roo/rules/env.md`](.roo/rules/env.md)                           | `.env` / `.env.example` rules  |
| [`.roo/rules/logging.md`](.roo/rules/logging.md)                   | Session logging rules          |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)                     | Project tree, dependency graph |
| [`docs/agents/AGENT_TASKS.md`](docs/agents/AGENT_TASKS.md)         | Task backlog                   |
| [`docs/knowledge/_INDEX.md`](docs/knowledge/_INDEX.md)             | API knowledge base index       |
