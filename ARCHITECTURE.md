# ARCHITECTURE.md — lenreg_ticket_bot

## Дерево директорий

```
zdrav.lenreg/                          # Корень проекта (только конфигурационные файлы)
├── src/                               # Весь исходный код приложения
│   ├── __init__.py
│   ├── config.py                      # Настройки (pydantic-settings, .env)
│   ├── main.py                        # Точка входа: сборка бота, запуск фоновых задач
│   ├── api/
│   │   ├── __init__.py
│   │   ├── models.py                  # Pydantic-модели ответов API zdrav.lenreg.ru
│   │   └── zdrav_client.py           # HTTP-клиент для API zdrav.lenreg.ru
│   ├── database/
│   │   ├── __init__.py
│   │   ├── database.py                # SQLite-движок: соединение, таблицы, CRUD
│   │   ├── manager.py                 # DatabaseManager — адаптер с in-memory кэшем
│   │   ├── doctor_manager.py          # DoctorManager — кэш справочника врачей
│   │   └── migrations.py             # Миграции схемы БД (versioned)
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── common.py                  # Основные обработчики: /start, выбор пациента/клиники/врача, toggle
│   │   └── registration.py           # FSM-сценарий регистрации пациента (ФИО → дата → псевдоним)
│   ├── keyboards/
│   │   ├── __init__.py
│   │   └── inline.py                 # Inline-клавиатуры Telegram (пациенты, города, клиники, врачи)
│   ├── middleware/
│   │   ├── __init__.py
│   │   └── ratelimit.py             # Per-user rate limiting middleware (sliding window, TTLCache)
│   ├── services/
│   │   ├── __init__.py
│   │   ├── cleanup.py                # Фоновый цикл автоудаления старых сообщений (TTL)
│   │   ├── doctor_discovery.py       # Фоновый цикл discovery врачей из API → БД
│   │   ├── error_notifier.py         # ErrorNotifier: NTFY + Sentry (singleton)
│   │   ├── healthcheck.py            # HealthMetrics + healthcheck_loop + /status report
│   │   └── monitor.py               # Фоновый цикл мониторинга слотов + классификация изменений
│   └── utils/
│       ├── __init__.py
│       ├── cache.py                  # Кэш мониторинга (файловый JSON) + spam_cache
│       └── helpers.py                # Форматирование ФИО, специальностей, extract_msg_id, is_child, is_cabinet
├── tests/                             # Тесты (структура не менялась)
│   ├── conftest.py
│   ├── test_cache.py
│   ├── test_database_manager.py
│   ├── test_doctor_discovery.py
│   ├── test_doctor_manager.py
│   ├── test_keyboards.py
│   ├── test_monitor_classify.py
│   ├── test_monitor_full.py
│   └── test_zdrav_client.py
├── scripts/                           # Утилитарные скрипты (не менялись)
│   ├── apply_city_heuristic.py
│   ├── apply_heuristic_types.py
│   └── run_tests.py
├── docs/                              # Документация и база знаний
│   ├── AGENT_TASKS.md
│   ├── SESSION_LOG.md
│   └── knowledge/                     # База знаний API
│       ├── _INDEX.md
│       ├── appointment_list.md
│       ├── check_patient.md
│       ├── doctor_list.md
│       └── speciality_list.md
├── pyproject.toml                     # ruff config
├── pytest.ini                         # pytest config
├── pyrightconfig.json                 # pyright config
├── .env / .env.example                # Переменные окружения
├── .gitignore
├── .pre-commit-config.yaml            # pre-commit хуки
├── requirements.txt
├── README.md
└── ARCHITECTURE.md                    # Этот файл
```

## Зоны ответственности

| Пакет | Зона ответственности |
|---|---|
| `src/config.py` | Загрузка и валидация настроек из `.env` через pydantic-settings. Переопределение значений из БД (config table). |
| `src/main.py` | Сборка и запуск: инициализация БД, API-клиента, бота aiogram, регистрация middleware и роутеров, запуск фоновых задач, graceful shutdown. |
| `src/api/` | Модели Pydantic для десериализации JSON-ответов API zdrav.lenreg.ru. HTTP-клиент `ZdravClient` с rate limiting (aiolimiter), retry, переиспользуемой сессией httpx. |
| `src/database/` | SQLite-движок (`Database`): WAL-режим, миграции, CRUD пользователей/пациентов/мониторинга/клиник/врачей/конфигов. `DatabaseManager` — потокобезопасный in-memory кэш с атомарными операциями. `DoctorManager` — кэш справочника врачей. |
| `src/handlers/` | Обработчики команд и callback-запросов Telegram через aiogram Router. `common.py` — навигация пациент→город→клиника→врач, toggle мониторинга. `registration.py` — FSM-сценарий добавления пациента. |
| `src/keyboards/` | Построение inline-клавиатур: пациенты, города/районы, клиники, врачи, подтверждение удаления, регистрация. |
| `src/middleware/` | `UserRateLimitMiddleware` — per-user rate limiting (sliding window) через TTLCache. |
| `src/services/` | Фоновые asyncio-циклы: `monitor_loop` — проверка слотов, классификация изменений, уведомления; `discovery_loop` — загрузка врачей из API; `healthcheck_loop` — мониторинг здоровья API; `cleanup_loop` — автоудаление старых сообщений; `error_notifier` — отправка ошибок в NTFY/Sentry. |
| `src/utils/` | `cache.py` — атомарный файловый кэш слотов (swap_cache_key) и spam_cache для защиты от двойных нажатий. `helpers.py` — форматирование ФИО/специальностей, определение ребёнка/кабинета, псевдонимы специальностей. |

## Граф зависимостей (Mermaid)

```mermaid
graph TD
    CFG[src.config.py]

    subgraph API
        MODELS[src.api.models]
        CLIENT[src.api.zdrav_client]
    end

    subgraph DB
        DB_CORE[src.database.database]
        DB_MGR[src.database.manager]
        DB_DOC[src.database.doctor_manager]
        DB_MIG[src.database.migrations]
    end

    subgraph Handlers
        H_COMMON[src.handlers.common]
        H_REG[src.handlers.registration]
    end

    subgraph Services
        SVC_DISC[src.services.doctor_discovery]
        SVC_MON[src.services.monitor]
        SVC_HC[src.services.healthcheck]
        SVC_CLN[src.services.cleanup]
        SVC_ERR[src.services.error_notifier]
    end

    subgraph Utils
        UTIL_CACHE[src.utils.cache]
        UTIL_HELP[src.utils.helpers]
    end

    KB[src.keyboards.inline]
    MW[src.middleware.ratelimit]
    ENTRY[src.main.py]

    MODELS --> CLIENT
    CFG --> CLIENT
    CFG --> DB_CORE
    CFG --> DB_MIG
    CFG --> SVC_ERR
    CFG --> SVC_DISC
    CFG --> SVC_MON
    CFG --> SVC_HC
    CFG --> SVC_CLN
    CFG --> UTIL_CACHE
    CFG --> H_COMMON
    CFG --> H_REG
    CFG --> MW

    DB_CORE --> DB_MGR
    DB_CORE --> DB_DOC
    DB_CORE --> DB_MIG

    CLIENT --> H_COMMON
    CLIENT --> H_REG
    CLIENT --> SVC_DISC
    CLIENT --> SVC_MON
    CLIENT --> SVC_HC
    CLIENT --> ENTRY

    DB_MGR --> H_COMMON
    DB_MGR --> H_REG
    DB_MGR --> SVC_MON
    DB_MGR --> SVC_HC
    DB_MGR --> SVC_CLN
    DB_MGR --> ENTRY

    DB_DOC --> SVC_DISC
    DB_DOC --> ENTRY

    SVC_DISC --> H_COMMON
    SVC_DISC --> ENTRY
    SVC_HC --> H_COMMON
    SVC_HC --> SVC_MON
    SVC_HC --> ENTRY
    SVC_MON --> ENTRY
    SVC_CLN --> ENTRY
    SVC_ERR --> ENTRY

    UTIL_CACHE --> H_COMMON
    UTIL_CACHE --> SVC_MON
    UTIL_HELP --> H_COMMON
    UTIL_HELP --> SVC_MON
    UTIL_HELP --> SVC_CLN
    UTIL_HELP --> KB
    UTIL_HELP --> DB_CORE

    KB --> H_COMMON
    KB --> H_REG
    MW --> ENTRY
    H_COMMON --> ENTRY
    H_REG --> ENTRY
```

## Ключевые архитектурные решения

1. **Все импорты — абсолютные с префиксом `src.`** (например, `from src.config import settings`). Это исключает коллизии и делает зависимости явными.

2. **Конфигурация через pydantic-settings** с двухуровневым переопределением: `.env` → `Settings` → БД (таблица `config`).

3. **SQLite с WAL-режимом** — асинхронный доступ через `aiosqlite`, миграции через самописный механизм `MIGRATIONS`.

4. **DatabaseManager** — потокобезопасный in-memory кэш поверх `Database` с атомарными read-modify-write операциями под `asyncio.Lock`.

5. **Фоновые задачи** запускаются как `asyncio.Task` и корректно останавливаются через `task.cancel()` + `asyncio.gather(return_exceptions=True)`.

6. **Rate limiting** на двух уровнях: API-клиент (`aiolimiter.AsyncLimiter`) и Telegram-хендлеры (`UserRateLimitMiddleware` с TTLCache).

7. **Тесты** используют временные SQLite-файлы в `tests/test_data/`, очищаемые после сессии.

## Конфигурационные файлы

| Файл | Назначение |
|---|---|
| `.env` | Реальные секреты и настройки (в `.gitignore`) |
| `.env.example` | Шаблон с публичными значениями и плейсхолдерами |
| `pyproject.toml` | Конфигурация ruff: линтинг + форматирование, `src = ["src"]` |
| `pytest.ini` | `asyncio_mode = auto`, `pythonpath = .` |
| `pyrightconfig.json` | `venvPath: "."`, `venv: ".venv"`, `rootPath: "."` |
| `.pre-commit-config.yaml` | Хуки: trailing-whitespace, end-of-file, ruff, mypy (`-p src -p scripts -p tests`) |
| `requirements.txt` | Зависимости проекта |
