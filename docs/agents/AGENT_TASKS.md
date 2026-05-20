# Активные задачи (Active Tasks)

> **Последнее обновление:** 2026-05-20
> **Источники:** [`zoo.deepseek_2026-05-20_audit_report.md`](zoo.deepseek_2026-05-20_audit_report.md) (80 проблем), [`qwen.coder_audit_report_2026-05-20.md`](qwen.coder_audit_report_2026-05-20.md) (12 проблем)
> **Методология:** консолидация двух независимых аудитов с дедупликацией по принципу суперсета, верификация расхождений (pytest 185/185 passed — deepseek прав, 50 failing тестов qwen.coder опровергнуто)
> **Формат ID:** `T-{БЛОК}-{NN}: {КРАТКОЕ_ОПИСАНИЕ}`
> **Severity:** 🔴 Critical, 🟠 Major, 🟡 Minor
> **Источник:** 🅳 deepseek, 🅀 qwen, 🅳🅀 оба
> **Статус:** ⬜ — не начато, 🔄 — в работе. Выполненные задачи удаляются из списка.

---

## 1. Docker / Контейнеризация

| ID          | Severity | Задача                                                                                                                | Файлы                                                        | Источник   |
| ----------- | -------- | --------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------ | ---------- |
| T-DOCKER-01 | 🔴       | Исправить Docker multistage COPY-путь: `COPY --from=builder /root/.local` → `/usr/local/lib/python3.11/site-packages` | [`Dockerfile:72`](../../Dockerfile:72)                       | 🅳 C1       |
| T-DOCKER-02 | 🟠       | Docker healthcheck проверяет файл БД а не живость процесса бота; заменить на проверку процесса                        | [`Dockerfile:83`](../../Dockerfile:83)                       | 🅳 M13      |
| T-DOCKER-03 | 🟠       | Добавить проверку Redis в docker-compose healthcheck (на текущий момент проверяется только SQLite)                    | [`docker-compose.yml:41-46`](../../docker-compose.yml:41-46) | 🅀 Major #3 |
| T-DOCKER-04 | 🟠       | Создать `.dockerignore`: исключить `.git/`, `__pycache__/`, `.venv/`, `logs/`, `data/*.db`, `tests/`, `docs/`, `.env` | `.dockerignore` (отсутствует)                                | 🅀 Major #4 |
| T-DOCKER-05 | 🟠       | Синхронизировать healthcheck `start_period`: 60s в compose vs 30s в документированном значении                        | [`docker-compose.yml`](../../docker-compose.yml)             | 🅳 M30      |

## 2. CI/CD

| ID      | Severity | Задача                                                                                                                                                                 | Файлы                                                                    | Источник   |
| ------- | -------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ | ---------- |
| T-CI-01 | 🔴       | Исправить несуществующие версии actions: `checkout@v6` → `@v4`, `setup-python@v6` → `@v5`                                                                              | [`.github/workflows/ci.yml:23-26`](../../.github/workflows/ci.yml:23)    | 🅳 C2       |
| T-CI-02 | 🔴       | Добавить шаги `markdownlint` и `prettier --check` в CI                                                                                                                 | [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml)             | 🅳 C6       |
| T-CI-03 | 🟠       | Добавить `ruff format --check` в CI                                                                                                                                    | [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml)             | 🅳 M28      |
| T-CI-04 | 🟠       | Добавить шаг сборки Docker-образа в CI                                                                                                                                 | [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml)             | 🅳 M29      |
| T-CI-05 | 🟠       | Исправить CI-кэш: переход на чистый pip с `requirements.txt` (poetry export) и кэширование `~/.cache/pip`, либо оптимизация Poetry-кэша через `snok/install-poetry@v1` | [`.github/workflows/ci.yml:22-23`](../../.github/workflows/ci.yml:22-23) | 🅀 Major #5 |
| T-CI-06 | 🟠       | Добавить `check-merge-conflict` в pre-commit хуки                                                                                                                      | [`.pre-commit-config.yaml`](../../.pre-commit-config.yaml)               | 🅳 M37      |

## 3. Безопасность

| ID       | Severity | Задача                                                                                                                                                         | Файлы                                                                                                                | Источник   |
| -------- | -------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- | ---------- |
| T-SEC-01 | 🔴       | Убрать хардкод PII: заменить default-значения `DISCOVERY_PATIENT_ID_ADULT="2343192"` и `DISCOVERY_PATIENT_ID_CHILD="2509768"` на плейсхолдеры в `.env.example` | [`src/config.py:70-71`](../../src/config.py:70)                                                                      | 🅳 C3       |
| T-SEC-02 | 🟠       | Исправить `CSRF_TOKEN` в `.env.example` с `your_csrf_token_here` на статический `NOTPROVIDED`                                                                  | [`.env.example`](../../.env.example)                                                                                 | 🅳 M24      |
| T-SEC-03 | 🟠       | Изменить default `CSRF_TOKEN` в `config.py` на пустую строку с валидацией и warning-логом (решение qwen)                                                       | [`src/config.py:82`](../../src/config.py:82)                                                                         | 🅀 Major #6 |
| T-SEC-04 | 🟡       | Добавить фильтр санитизации чувствительных данных в логах (user IDs, cookie, CSRF-токены, URL с аутентификацией); использовать `logging.Filter` для маскировки | [`src/middleware/logging.py`](../../src/middleware/logging.py), [`src/utils/logging.py`](../../src/utils/logging.py) | 🅀 Minor #6 |

## 4. API-клиент (`src/api/zdrav_client.py`)

| ID       | Severity | Задача                                                                                                                                    | Файлы                                                                  | Источник |
| -------- | -------- | ----------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- | -------- |
| T-API-01 | 🔴       | Добавить retry-цикл (3 попытки) в `fetch_patient_id` по образцу `fetch_speciality_list`                                                   | [`src/api/zdrav_client.py:156-193`](../../src/api/zdrav_client.py:156) | 🅳 C4     |
| T-API-02 | 🔴       | Добавить поля `doctor_form-history_id: ""` и `doctor_form-appointment_type: ""` в payload `check_slots` (требование спецификации)         | [`src/api/zdrav_client.py:294-298`](../../src/api/zdrav_client.py:294) | 🅳 C5     |
| T-API-03 | 🟠       | Добавить обработку 403/429 статусов в `fetch_speciality_list`                                                                             | [`src/api/zdrav_client.py`](../../src/api/zdrav_client.py)             | 🅳 M1     |
| T-API-04 | 🟠       | Добавить обработку 403/429 статусов в `fetch_all_doctors`                                                                                 | [`src/api/zdrav_client.py`](../../src/api/zdrav_client.py)             | 🅳 M2     |
| T-API-05 | 🟠       | Добавить обработку 403/429 статусов в `fetch_clinic_list`                                                                                 | [`src/api/zdrav_client.py`](../../src/api/zdrav_client.py)             | 🅳 M3     |
| T-API-06 | 🟠       | Исправить вводящее в заблуждение сообщение об ошибке в `fetch_patient_id` — всегда `api-timeout`, должно быть специфичным для типа ошибки | [`src/api/zdrav_client.py:190`](../../src/api/zdrav_client.py:190)     | 🅳 M8     |
| T-API-07 | 🟠       | Добавить `exc_info=True` при логировании ошибок API во всех методах клиента                                                               | [`src/api/zdrav_client.py`](../../src/api/zdrav_client.py)             | 🅳 M9     |

## 5. Конфигурация

| ID       | Severity | Задача                                                                                                                                                                                          | Файлы                                                                                  | Источник |
| -------- | -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- | -------- |
| T-CFG-01 | 🟠       | Синхронизировать openapi.yaml `AppConfig`: добавить 15 полей из Settings                                                                                                                        | [`docs/openapi.yaml`](../../docs/openapi.yaml), [`src/config.py`](../../src/config.py) | 🅳 M5     |
| T-CFG-02 | 🟠       | Добавить 7 недостающих ключей в `.env.example`: `CHECK_INTERVAL`, `DISCOVERY_INTERVAL`, `CLEANUP_INTERVAL`, `SLOT_DETAIL_THRESHOLD`, `SLOT_COMPACT_THRESHOLD`, `DENTAL_CLINIC_ID`, `SIGNUP_URL` | [`.env.example`](../../.env.example)                                                   | 🅳 M12    |
| T-CFG-03 | 🟡       | Добавить 4 чувствительных поля конфигурации в `AppConfig` (openapi.yaml)                                                                                                                        | [`docs/openapi.yaml`](../../docs/openapi.yaml)                                         | 🅳 Minor  |
| T-CFG-04 | 🟡       | Исправить несогласованное поведение `get_config()` при отсутствии соединения с БД                                                                                                               | [`src/config.py`](../../src/config.py)                                                 | 🅳 Minor  |

## 6. Документация / Spec-First

| ID       | Severity | Задача                                                                                                                                            | Файлы                                                                                          | Источник              |
| -------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- | --------------------- |
| T-DOC-01 | 🟠       | Добавить таблицу `monitoring_log` в openapi.yaml                                                                                                  | [`docs/openapi.yaml`](../../docs/openapi.yaml)                                                 | 🅳 M4                  |
| T-DOC-02 | 🟠       | Документировать 6 веб-дашборд эндпоинтов в openapi.yaml (paths + схемы: `DashboardSummary`, `UserInfo`, `ClinicInfo`, `LogEntry`, `HealthStatus`) | [`docs/openapi.yaml`](../../docs/openapi.yaml)                                                 | 🅳 M6, 🅀 Major #2      |
| T-DOC-03 | 🟠       | Заменить inline-определение `ClinicListRequest` на `$ref` в openapi.yaml                                                                          | [`docs/openapi.yaml`](../../docs/openapi.yaml)                                                 | 🅳 M7                  |
| T-DOC-04 | 🟠       | Полная ресинхронизация ARCHITECTURE.md: добавить модули `filters/`, `i18n/`, `web/` в дерево                                                      | [`docs/ARCHITECTURE.md`](../../docs/ARCHITECTURE.md)                                           | 🅳 M14                 |
| T-DOC-05 | 🟠       | ARCHITECTURE.md: добавить зоны ответственности для `middleware/` (4 модуля)                                                                       | [`docs/ARCHITECTURE.md`](../../docs/ARCHITECTURE.md)                                           | 🅳 M15-M18, 🅀 Major #1 |
| T-DOC-06 | 🟠       | ARCHITECTURE.md: добавить зоны ответственности для `web/` (7 файлов)                                                                              | [`docs/ARCHITECTURE.md`](../../docs/ARCHITECTURE.md)                                           | 🅳 M19                 |
| T-DOC-07 | 🟠       | ARCHITECTURE.md: добавить зоны ответственности для `filters/` и `i18n/`                                                                           | [`docs/ARCHITECTURE.md`](../../docs/ARCHITECTURE.md)                                           | 🅳 M20                 |
| T-DOC-08 | 🟠       | ARCHITECTURE.md: исправить структуру тестов и имена `.roo/rules/`                                                                                 | [`docs/ARCHITECTURE.md`](../../docs/ARCHITECTURE.md)                                           | 🅳 M21                 |
| T-DOC-09 | 🟠       | ARCHITECTURE.md: расширить Mermaid-граф — добавить 15+ узлов (`middleware.*`, `web.*`, `filters.*`, `i18n.*`) и связи                             | [`docs/ARCHITECTURE.md`](../../docs/ARCHITECTURE.md)                                           | 🅳 M22                 |
| T-DOC-10 | 🟠       | Сгенерировать недостающие JSON-схемы в `docs/schemas/` (~16 из 28 отсутствуют)                                                                    | [`docs/schemas/`](../../docs/schemas/)                                                         | 🅳 M23                 |
| T-DOC-11 | 🟡       | Добавить Pydantic request-модели для тел запросов (сейчас сырые `dict`)                                                                           | [`src/api/models.py`](../../src/api/models.py)                                                 | 🅳 Minor               |
| T-DOC-12 | 🟡       | Синхронизировать nullable: `LastDate`/`NearestDate` nullable в коде, не-nullable в openapi.yaml                                                   | [`docs/openapi.yaml`](../../docs/openapi.yaml), [`src/api/models.py`](../../src/api/models.py) | 🅳 Minor               |
| T-DOC-13 | 🟡       | Документировать `PatientInfo.clinic_id` в `DB_Patient` (openapi.yaml)                                                                             | [`docs/openapi.yaml`](../../docs/openapi.yaml)                                                 | 🅳 Minor               |
| T-DOC-14 | 🟡       | Исправить устаревшие номера строк в описаниях openapi.yaml                                                                                        | [`docs/openapi.yaml`](../../docs/openapi.yaml)                                                 | 🅳 Minor               |
| T-DOC-15 | 🟡       | Добавить `ClinicInfo` TypedDict с discovery-полями                                                                                                | [`src/database/types.py`](../../src/database/types.py)                                         | 🅳 Minor               |
| T-DOC-16 | 🟡       | Добавить `contact` (email/url) и заполнить `RateLimitConfig.properties` в openapi.yaml                                                            | [`docs/openapi.yaml`](../../docs/openapi.yaml)                                                 | 🅳 Minor               |
| T-DOC-17 | 🟡       | Создать `docs/knowledge/clinic_list.md` и добавить в `_INDEX.md`                                                                                  | [`docs/knowledge/`](../../docs/knowledge/)                                                     | 🅳 Minor               |

## 7. Качество кода

| ID        | Severity | Задача                                                                                                           | Файлы                                                                            | Источник   |
| --------- | -------- | ---------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- | ---------- |
| T-CODE-01 | 🟠       | Заменить синхронный `tempfile.NamedTemporaryFile` на `aiofiles` в `export.py` (блокирует event loop)             | [`src/services/export.py:53`](../../src/services/export.py:53)                   | 🅳 M10      |
| T-CODE-02 | 🟠       | Заменить `# mypy: ignore-errors` на весь файл `redis.py` точечными `# type: ignore` с комментариями              | [`src/utils/redis.py:8`](../../src/utils/redis.py:8)                             | 🅳 M11      |
| T-CODE-03 | 🟡       | Рефакторинг избыточных импортов в `main.py`: вынести в отдельные модули, применить lazy imports, factory-функции | [`src/main.py:1-40`](../../src/main.py:1-40)                                     | 🅀 Minor #2 |
| T-CODE-04 | 🟡       | Типизировать callback_data через `aiogram.utils.callback_factory.CallbackData`; добавить фильтры валидации       | [`src/handlers/`](../../src/handlers/), [`src/keyboards/`](../../src/keyboards/) | 🅀 Minor #5 |
| T-CODE-05 | 🟡       | Подавление ошибок WAL checkpoint: добавить `exc_info=True` в логирование                                         | [`src/database/database.py`](../../src/database/database.py)                     | 🅳 Minor    |
| T-CODE-06 | 🟡       | Подавление ошибок сидирования БД: добавить `exc_info=True`                                                       | [`src/database/migrations.py`](../../src/database/migrations.py)                 | 🅳 Minor    |
| T-CODE-07 | 🟡       | `except Exception` в `_send_notification`: заменить на конкретные типы + `exc_info=True`                         | [`src/services/error_notifier.py`](../../src/services/error_notifier.py)         | 🅳 Minor    |
| T-CODE-08 | 🟡       | Прямой доступ к `db._db` в обход `DatabaseManager` в `cleanup.py`: заменить на менеджер                          | [`src/services/cleanup.py`](../../src/services/cleanup.py)                       | 🅳 Minor    |
| T-CODE-09 | 🟡       | Заменить `Any` на конкретные типы в `schema_watcher.py`                                                          | [`src/services/schema_watcher.py`](../../src/services/schema_watcher.py)         | 🅳 Minor    |
| T-CODE-10 | 🟡       | Добавить type hint для параметра `limiter` в `doctor_discovery.py`                                               | [`src/services/doctor_discovery.py`](../../src/services/doctor_discovery.py)     | 🅳 Minor    |

## 8. Тесты

| ID        | Severity | Задача                                                                                                                           | Файлы                                                                                                | Источник   |
| --------- | -------- | -------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- | ---------- |
| T-TEST-01 | 🟠       | Расширить тесты API-клиента: `fetch_clinic_list`, retry на сетевые ошибки, rate limiter, Pydantic-валидация                      | [`tests/api/test_zdrav_client.py`](../../tests/api/test_zdrav_client.py)                             | 🅳 M25      |
| T-TEST-02 | 🟠       | Расширить тесты DatabaseManager: покрыть ~60% непокрытых методов, изолированное тестирование Database                            | [`tests/database/test_database_manager.py`](../../tests/database/test_database_manager.py)           | 🅳 M26      |
| T-TEST-03 | 🟠       | Добавить тесты обработчиков: edge cases с ошибками API, `from_user=None`, `del_p_no`                                             | [`tests/handlers/`](../../tests/handlers/)                                                           | 🅳 M27      |
| T-TEST-04 | 🟡       | Создать тесты для web-дашборда: `tests/web/test_api.py`, `test_dashboard.py`, `test_auth.py`, интеграционный тест `create_app()` | [`src/web/`](../../src/web/)                                                                         | 🅀 Minor #1 |
| T-TEST-05 | 🟡       | Добавить тест ошибки API в `process_bday` (регистрация)                                                                          | [`tests/handlers/test_handlers_registration.py`](../../tests/handlers/test_handlers_registration.py) | 🅳 Minor    |
| T-TEST-06 | 🟡       | Добавить тест частичного сбоя API в мониторинге                                                                                  | [`tests/services/test_monitor_full.py`](../../tests/services/test_monitor_full.py)                   | 🅳 Minor    |
| T-TEST-07 | 🟡       | Исправить дублирование фабрик в `test_handlers_registration.py`                                                                  | [`tests/handlers/test_handlers_registration.py`](../../tests/handlers/test_handlers_registration.py) | 🅳 Minor    |
| T-TEST-08 | 🟡       | Расширить тесты `export.py`: несколько пользователей, спецсимволы                                                                | [`tests/services/test_export.py`](../../tests/services/test_export.py)                               | 🅳 Minor    |
| T-TEST-09 | 🟡       | Добавить edge cases с пустыми данными в `test_keyboards.py`                                                                      | [`tests/keyboards/test_keyboards.py`](../../tests/keyboards/test_keyboards.py)                       | 🅳 Minor    |
| T-TEST-10 | 🟡       | Удалить устаревшую фикстуру `clear_spam_cache`                                                                                   | [`tests/conftest.py`](../../tests/conftest.py)                                                       | 🅳 Minor    |
| T-TEST-11 | 🟡       | Исправить синхронные операции в асинхронной фикстуре `temp_db_path`                                                              | [`tests/conftest.py`](../../tests/conftest.py)                                                       | 🅳 Minor    |
| T-TEST-12 | 🟡       | Добавить логирование при ошибке очистки в `pytest_sessionfinish`                                                                 | [`tests/conftest.py`](../../tests/conftest.py)                                                       | 🅳 Minor    |

## 9. Инструменты / Инфраструктура

| ID        | Severity | Задача                                                                                             | Файлы                                                                      | Источник          |
| --------- | -------- | -------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- | ----------------- |
| T-TOOL-01 | 🟠       | Добавить `prettier` в `devDependencies` package.json (сейчас только markdownlint-cli)              | [`package.json`](../../package.json)                                       | 🅳 M31, 🅀 Minor #3 |
| T-TOOL-02 | 🟠       | Исправить Makefile `clean`: обеспечить совместимость с Windows (PowerShell)                        | [`Makefile`](../../Makefile)                                               | 🅳 M32             |
| T-TOOL-03 | 🟡       | Задокументировать требование Node 18 для `markdownlint-cli` v0.44                                  | [`README.md`](../../README.md)                                             | 🅳 M33             |
| T-TOOL-04 | 🟡       | Убрать глобальное подавление `DeprecationWarning` в pytest.ini (или оставить с явным комментарием) | [`pytest.ini`](../../pytest.ini)                                           | 🅳 M34             |
| T-TOOL-05 | 🟡       | Устранить дублирование `filterwarnings` между pytest.ini и pyproject.toml                          | [`pytest.ini`](../../pytest.ini), [`pyproject.toml`](../../pyproject.toml) | 🅳 M35             |
| T-TOOL-06 | 🟡       | Повысить `pyrightconfig.json` `typeCheckingMode` с `"basic"` до `"strict"`                         | [`pyrightconfig.json`](../../pyrightconfig.json)                           | 🅳 M36             |
| T-TOOL-07 | 🟡       | Исправить конфликт конфигурации pytest (WARNING: ignoring pytest config in pyproject.toml)         | [`pyproject.toml`](../../pyproject.toml)                                   | 🅀 Minor #4        |
| T-TOOL-08 | 🟡       | Заполнить placeholder-поля в package.json (`description`, `repository`)                            | [`package.json`](../../package.json)                                       | 🅳 Minor           |

---

## Сводка

| Severity    | Количество | Блоки                                                                                           |
| ----------- | ---------- | ----------------------------------------------------------------------------------------------- |
| 🔴 Critical | 6          | Docker (1), CI (2), Security (1), API (2)                                                       |
| 🟠 Major    | 37         | Docker (3), CI (3), Security (2), API (5), Config (2), Docs (6), Code (2), Tests (3), Tools (2) |
| 🟡 Minor    | 37         | Security (1), Config (2), Docs (7), Code (6), Tests (9), Tools (6)                              |
| **Всего**   | **80**     |                                                                                                 |
