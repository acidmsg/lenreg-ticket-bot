<!-- markdownlint-disable MD024 -->

# Архив сессий разработки

Полная хронология всех сессий за 2026-05-01 — 2026-05-19. Активный лог последней сессии — в [`SESSION_LOG.md`](SESSION_LOG.md).

---

## 2026-05-19 — Исправление 4 записей MINOR технического долга

### Выполненные задачи

| ID        | Описание                                                                      | Файлы                                            |
| --------- | ----------------------------------------------------------------------------- | ------------------------------------------------ |
| MIN-001   | Исправлена опечатка `"сте – клянный"` → `"стеклянный"` в маппинге settlements | [`database.py:84`](src/database/database.py:84)  |
| MIN-002-A | Добавлен docstring про опечатку API `Spesiality` в `SpecialityItem`           | [`models.py:62-69`](src/api/models.py:62)        |
| MIN-011   | Улучшена эвристика `is_cabinet()`: ключевые слова, цифры, дефисы, отчества    | [`helpers.py:116-172`](src/utils/helpers.py:116) |
| MIN-012   | Улучшена `shorten_fio()`: фильтр пустых частей, 2-словные ФИО, fallback       | [`helpers.py:174-202`](src/utils/helpers.py:174) |

### Изменённые файлы

- [`src/database/database.py`](src/database/database.py) — строка 84
- [`src/api/models.py`](src/api/models.py) — строки 62–69
- [`src/utils/helpers.py`](src/utils/helpers.py) — строки 116–202

### Результаты проверок

- Ruff: 0 errors
- Тесты `tests/utils/`: 15/15 passed

---

## 2026-05-19 — Синхронизация `.env` с `.env.example`

### Выполненные задачи

#### Добавление отсутствующих ключей в `.env`

В `.env` добавлены 12 ключей, присутствующих в `.env.example`:

| Категория                    | Ключи                                                                  |
| ---------------------------- | ---------------------------------------------------------------------- |
| Redis                        | `REDIS_URL`                                                            |
| Пороги слотов                | `SLOT_DETAIL_THRESHOLD`, `SLOT_COMPACT_THRESHOLD`                      |
| Metrics / API Versioning     | `METRICS_PORT`, `API_VERSION`, `API_VALIDATE_RESPONSES`                |
| i18n                         | `BOT_LANGUAGE`                                                         |
| Schema Change Detection (F8) | `SCHEMA_CHECK_INTERVAL`, `SCHEMA_CHECK_ENABLED`                        |
| Web Dashboard (F5)           | `WEB_DASHBOARD_ENABLED`, `WEB_DASHBOARD_PORT`, `WEB_DASHBOARD_API_KEY` |

Каждый ключ вставлен в соответствующую секцию согласно порядку, указанному в задаче.

### Изменённые файлы

- `.env` — добавлено 12 ключей в 6 секциях (Redis, пороги, Metrics/API Versioning, i18n, F8, F5)

### Результаты проверок

| Инструмент       | Результат                                         |
| ---------------- | ------------------------------------------------- |
| Сравнение ключей | Все ключи из `.env.example` присутствуют в `.env` |

---

## 2026-05-19 — Реализация детектора изменений API (F8) — Code

### Выполненные задачи

1. **Шаг 1:** Создан [`scripts/generate_api_schemas.py`](scripts/generate_api_schemas.py) — скрипт генерации эталонных JSON Schema для 12 Pydantic-моделей из [`src/api/models.py`](src/api/models.py).
2. **Шаг 2:** Запущен скрипт — созданы 12 `.json` файлов в [`docs/schemas/`](docs/schemas/):
   - `CheckPatientResponse.json`, `CheckPatientData.json`, `SpecialityListResponse.json`, `SpecialityItem.json`, `DoctorListResponse.json`, `DoctorItem.json`, `AppointmentListResponse.json`, `AppointmentSlot.json`, `ClinicListResponse.json`, `ClinicItem.json`, `DateInfo.json`, `ApiError.json`
3. **Шаг 3:** Создан [`src/services/schema_watcher.py`](src/services/schema_watcher.py) с компонентами:
   - [`load_reference_schemas()`](src/services/schema_watcher.py:139) — загрузка эталонных схем из `docs/schemas/`
   - [`compare_schemas()`](src/services/schema_watcher.py:89) — рекурсивный diff двух JSON Schema (type, properties, required, additionalProperties, items, anyOf)
   - [`_describe_type()`](src/services/schema_watcher.py:80) / [`_normalize_anyof()`](src/services/schema_watcher.py:86) — вспомогательные функции
   - [`validate_endpoint_schema()`](src/services/schema_watcher.py:171) — тестовый запрос + валидация + сравнение для одного эндпоинта
   - [`_call_endpoint()`](src/services/schema_watcher.py:204) — диспетчеризация вызовов ZdravClient (с цепочками для doctor_list/appointment_list)
   - [`schema_check_loop()`](src/services/schema_watcher.py:297) — фоновый asyncio-цикл проверки всех 5 эндпоинтов
4. **Шаг 4:** В [`src/services/error_notifier.py`](src/services/error_notifier.py) добавлен метод:
   - [`notify_schema_change(endpoint, diffs)`](src/services/error_notifier.py:126) — NTFY (priority=high, tag=api_schema_change) + Sentry (capture_message, level=warning)
5. **Шаг 5:** В [`src/services/metrics.py`](src/services/metrics.py) добавлены:
   - Gauge `zdrav_api_schema_drift` (label: endpoint)
   - Counter `zdrav_api_schema_changes_total` (label: endpoint)
   - Методы [`set_schema_drift()`](src/services/metrics.py:190) и [`inc_schema_changes()`](src/services/metrics.py:195)
6. **Шаг 6:** В [`src/config.py`](src/config.py) добавлены:
   - Параметры `SCHEMA_CHECK_INTERVAL` (3600) и `SCHEMA_CHECK_ENABLED` (True)
   - Константы `CONFIG_KEY_SCHEMA_CHECK_INTERVAL` / `CONFIG_KEY_SCHEMA_CHECK_ENABLED`
   - Маппинг в `load_config_from_db()`
   - Запись в [`.env.example`](.env.example)
7. **Шаг 7:** В [`src/main.py`](src/main.py) добавлен импорт `schema_check_loop` и запуск фоновой задачи в `_start_background_tasks()` при `settings.SCHEMA_CHECK_ENABLED`.
8. **Шаг 8:** Проверки:
   - Ruff: 0 ошибок на новых/изменённых файлах
   - Pytest: 142 passed (1 предсуществующий failure: `test_doctor_discovery.TestFetchSpecialties.test_success_returns_parsed_list`)

### Изменённые файлы

| Файл                              | Действие |
| --------------------------------- | -------- |
| `scripts/generate_api_schemas.py` | Создан   |
| `src/services/schema_watcher.py`  | Создан   |
| `src/services/error_notifier.py`  | Изменён  |
| `src/services/metrics.py`         | Изменён  |
| `src/config.py`                   | Изменён  |
| `src/main.py`                     | Изменён  |
| `.env.example`                    | Изменён  |
| `docs/schemas/` (12 файлов)       | Созданы  |
| `docs/agents/SESSION_LOG.md`      | Изменён  |
| `docs/agents/SESSION_ARCHIVE.md`  | Изменён  |
| `docs/agents/AGENT_TASKS.md`      | Изменён  |

### Результаты проверок

| Инструмент   | Результат                                    |
| ------------ | -------------------------------------------- |
| ruff check   | 0 errors on new/modified files               |
| pytest       | 142 passed (1 pre-existing failure excluded) |
| markdownlint | ✅                                           |
| prettier     | ✅                                           |

---

## 2026-05-14 (Полный аудит проекта — Code Review)

### Задача

Проведён всесторонний аудит всего проекта с сохранением результата в [`code_review.md`](code_review.md). Анализ охватил 7 разделов: архитектура, качество кода, производительность, безопасность/наблюдаемость, инфраструктура/DX, пробелы и план действий.

### Выполненные задачи

- Прочитан и проанализирован **каждый файл исходного кода** (~25 файлов, ~3500 строк Python): `src/`, `tests/`, `docs/`, конфигурационные файлы
- Создан [`code_review.md`](code_review.md) — подробный аналитический отчёт с:
  - Оценкой архитектуры (чистая слоёная, SSOT в openapi.yaml)
  - 7 замечаний по качеству кода (B1-B7)
  - 3 проблемы производительности (P1-P3), включая **критическую** P2
  - 5 замечаний по безопасности/наблюдаемости (S1-S5)
  - 5 проблем инфраструктуры/DX (I1-I5)
  - 8 функциональных пробелов (M1-M8)
  - Планом действий: 3 CRITICAL, 4 HIGH, 12 LOW задач
- Общая оценка проекта: **7.5/10**

### Топ-3 критических проблемы

| #   | Проблема                                                                                                                | Файл                                                |
| --- | ----------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------- |
| C1  | Последовательные проверки в `monitor_loop` — при 100+ пользователях цикл >30 мин. Нужен `asyncio.gather` + `Semaphore`. | [`monitor.py:110-204`](src/services/monitor.py:110) |
| C2  | Нет CI/CD pipeline (`.github/workflows/`) — тесты и линтинг только локально.                                            | отсутствует                                         |
| C3  | Нет graceful degradation без Redis — бот падает при старте, если Redis недоступен.                                      | [`main.py:240-244`](src/main.py:240)                |

### Изменённые файлы

| Файл                                                               | Действие  |
| ------------------------------------------------------------------ | --------- |
| [`code_review.md`](code_review.md)                                 | Создан    |
| [`docs/agents/SESSION_LOG.md`](docs/agents/SESSION_LOG.md)         | Переписан |
| [`docs/agents/SESSION_ARCHIVE.md`](docs/agents/SESSION_ARCHIVE.md) | Изменён   |

---

## 2026-05-14 (Точечная доводка standards.md + создание Entry Point .clinerules)

### Задача

Финальная полировка системы правил после рефакторинга: возврат утерянных упоминаний (`call.message`, `strict`) в [`standards.md`](.roo/rules/standards.md) и создание файла-маршрутизатора [`.clinerules`](.clinerules) в корне проекта.

### Выполненные задачи

- В [`.roo/rules/standards.md`](.roo/rules/standards.md:12) в раздел «Типизация» возвращено упоминание `strict` — строка 12
- В [`.roo/rules/standards.md`](.roo/rules/standards.md:35) в раздел «Обработка ошибок» возвращено упоминание `call.message` — строка 35
- Создан [`.clinerules`](.clinerules:1) — точка входа (Rule Router), маршрутизирующая агента к трём доменным файлам правил

### Изменённые файлы

| Файл                                                 | Действие    |
| ---------------------------------------------------- | ----------- |
| [`.roo/rules/standards.md`](.roo/rules/standards.md) | Изменён (2) |
| [`.clinerules`](.clinerules)                         | Создан      |

---

## 2026-05-13 (диагностика падения бота + защита от недоступности прокси)

### Анализ ошибки в [`logs/error.log`](logs/error.log)

**Задача:** Прочитать error.log, найти причину падения бота.

**Корневая причина:** SOCKS5 прокси `172.21.160.1:10808` был недоступен в момент старта.
Aiogram вызывает `bot.me()` → `aiohttp_socks.ProxyConnector` → `OSError: [WinError 121] Превышен таймаут семафора`.

Полный трейс:

```text
src/main.py:135 → asyncio.run(main())
  src/main.py:114 → dp.start_polling(bot)
    aiogram dispatcher.py:377 → bot.me()
      aiogram bot.py:504 → session.__call__()
        aiohttp_socks connector.py:79 → ProxyConnectionError
          asyncio windows_events.py:804 → OSError: [WinError 121]
```

**Диагностика:**

- Прокси `172.21.160.1:10808` недоступен (curl test failed)
- `PROXY_URL` в `.env` был закомментирован пользователем после падения
- Указан новый адрес прокси: `172.17.16.1:10808`
- Прокси обязателен — Telegram API недоступен в стране пользователя

### Реализованные защиты в [`src/main.py`](src/main.py)

| Защита                              | Функция                       | Строки  |
| ----------------------------------- | ----------------------------- | ------- |
| Healthcheck прокси перед стартом    | `_check_proxy_connectivity()` | 54-71   |
| Retry для `bot.me()`                | `_bot_me_with_retry()`        | 74-97   |
| Отложенный запуск фоновых задач     | `_start_background_tasks()`   | 100-141 |
| Retry для `AiohttpSession` с прокси | цикл в `main()`               | 183-200 |
| Парсинг host:port из proxy URL      | `_parse_proxy_host_port()`    | 35-39   |

**Изменённые файлы:**

| Файл                           | Действие                                                 |
| ------------------------------ | -------------------------------------------------------- |
| [`.env`](.env:5)               | `PROXY_URL=socks5://172.17.16.1:10808` (новый адрес)     |
| [`src/main.py`](src/main.py:1) | Полный рефакторинг: healthcheck, retry, отложенные таски |

**Результаты тестов:** ruff check — All checks passed. mypy — только pre-existing errors в других файлах.

### Автоопределение прокси (авто-обнаружение IP)

**Задача:** Прокси (HAPP Proxy Utilities в Docker/WSL2) меняет IP при перезагрузке
Docker/WSL2, потому что Docker использует случайные подсети из `172.16.0.0/12`.
Решение: сканировать подсети `172.17-31.0.0/16` на порту 10808 при старте бота.

**Реализованные функции в [`src/main.py`](src/main.py):**

| Функция                       | Строки | Назначение                                       |
| ----------------------------- | ------ | ------------------------------------------------ |
| `_probe_host()`               | 46-63  | TCP-проба одного хоста с семафором и таймаутом   |
| `_generate_docker_gateways()` | 66-84  | Генерация ~240 gateway IP (фазы 1+2)             |
| `_discover_proxy()`           | 87-114 | Параллельное сканирование, возврат socks5:// URL |

**Интеграция в `main()`** (строки 258-270): если хост в `PROXY_URL` = `"auto"`,
вызывается `_discover_proxy()`. При неудаче — `ConnectionError` с понятным сообщением.

**Изменённые файлы:**

| Файл                             | Действие                                        |
| -------------------------------- | ----------------------------------------------- |
| [`.env`](.env:7)                 | `PROXY_URL=socks5://auto:10808`                 |
| [`.env.example`](.env.example:7) | Комментарий про автоопределение + `auto:10808`  |
| [`src/main.py`](src/main.py:33)  | +3 константы, +3 функции, интеграция в `main()` |

**Результаты линтинга:** ruff — All checks passed. mypy — Success: no issues found. ruff format — 3 files already formatted.

---

## 2026-05-12 (исправление markdownlint-ошибок)

### Исправление markdownlint-нарушений в SESSION_ARCHIVE.md ✅

**Задача:** Исправить 41 markdownlint violation в [`docs/agents/SESSION_ARCHIVE.md`](SESSION_ARCHIVE.md:1), выявленные VSCode Problems tab.

**Исправленные ошибки:**

| Правило | Суть                                | Кол-во | Метод исправления                                            |
| ------- | ----------------------------------- | ------ | ------------------------------------------------------------ |
| MD058   | Таблицы без пустых строк            | 5      | Пустые строки перед таблицами                                |
| MD060   | Стиль разделителей таблиц: `\|-\|-` | ~15    | Заменено на `\| --- \|` (spaces вокруг разделителей)         |
| MD038   | Пробел внутри инлайн-кода           | 1      | `` `Ошибка API (fetch_speciality_list): ` `` → `` `...):` `` |
| MD024   | Дубликат H2 `2026-05-11` (5)        | 5      | Уникальные контекстные суффиксы                              |
| MD024   | Дубликат H3 `Изменённые файлы` (9)  | 8      | `markdownlint-disable-next-line MD024` перед повторными H3   |

**Изменённые файлы:**

| Файл                                                     | Действие                              |
| -------------------------------------------------------- | ------------------------------------- |
| [`docs/agents/SESSION_ARCHIVE.md`](SESSION_ARCHIVE.md:1) | Исправлены MD038, MD058, MD060, MD024 |

**Результаты тестов:** Не запускались

---

## 2026-05-12 (приведение файлов к стандартам)

### Обновление knowledge.md, restrictions.md, SESSION_ARCHIVE.md ✅

**Задача:** Привести [`.roo/rules/knowledge.md`](../.roo/rules/knowledge.md:1), [`.roo/rules/restrictions.md`](../.roo/rules/restrictions.md:1) и [`docs/agents/SESSION_ARCHIVE.md`](SESSION_ARCHIVE.md:1) в соответствие со стандартами из [`.roo/rules/system_standards.md`](../.roo/rules/system_standards.md:1).

**Изменённые файлы:**

| Файл                                                            | Действие                                                     |
| --------------------------------------------------------------- | ------------------------------------------------------------ |
| [`.roo/rules/knowledge.md`](../.roo/rules/knowledge.md:1)       | Добавлен H1, ссылки на файлы с путями, inline-форматирование |
| [`.roo/rules/restrictions.md`](../.roo/rules/restrictions.md:1) | Добавлен H1, пути в inline-коде, ссылка на ignore.md         |
| [`docs/agents/SESSION_ARCHIVE.md`](SESSION_ARCHIVE.md:1)        | H1 переименован из filename в описательный заголовок         |

**Результаты тестов:** Не запускались

---

## 2026-05-12 (ruff check/pytest: исправление 46 ошибок)

### Исправление всех ошибок ruff check + ruff format ✅

**Задача:** Исправить 46 ошибок ruff check (E501 длинные строки, ASYNC240 os.path в async, ASYNC251 time.sleep, N806 переменная) + автоформатирование 5 файлов.

**Изменённые файлы (14 файлов):**

| Файл                                                                                          | Что исправлено                                                                                                   |
| --------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| [`src/config.py`](../src/config.py:71,143)                                                    | E501: разбиты 2 длинные строки (комментарий + f-string логгера)                                                  |
| [`src/database/database.py`](../src/database/database.py:128,262,274,554,571,591,616,661,723) | E501: разбиты SQL-строки и f-строки логгеров; ASYNC240: `# noqa` на `os.path.exists/makedirs`                    |
| [`src/database/manager.py`](../src/database/manager.py:121)                                   | E501: разбит длинный SQL                                                                                         |
| [`src/database/migrations.py`](../src/database/migrations.py:87,94)                           | E501: разбит SQL и docstring                                                                                     |
| [`src/handlers/common.py`](../src/handlers/common.py:198,481,504,721)                         | E501: разбиты 4 длинные строки сообщений                                                                         |
| [`src/handlers/registration.py`](../src/handlers/registration.py:68,84,116,149)               | E501: разбиты 4 длинные строки сообщений                                                                         |
| [`src/keyboards/inline.py`](../src/keyboards/inline.py:52,118,269,279)                        | N806: `DENTAL_CLINIC_ID` → `_dental_clinic_id`; E501: разбиты 3 комментария                                      |
| [`src/main.py`](../src/main.py:26,40)                                                         | ASYNC240: `# noqa` на `os.path.exists/makedirs`                                                                  |
| [`src/services/cleanup.py`](../src/services/cleanup.py:3)                                     | E501: разбит docstring                                                                                           |
| [`src/services/doctor_discovery.py`](../src/services/doctor_discovery.py:117)                 | E501: f-string логгера → `%s` формат                                                                             |
| [`src/services/healthcheck.py`](../src/services/healthcheck.py:80,82,245)                     | E501: разбиты f-строки статуса и настроек                                                                        |
| [`src/services/monitor.py`](../src/services/monitor.py:37,79,125,146,181,184)                 | E501: разбиты docstring, f-строки, логгеры                                                                       |
| [`src/utils/cache.py`](../src/utils/cache.py:32,55)                                           | ASYNC240: `# noqa` на `os.path.exists`                                                                           |
| [`tests/conftest.py`](../tests/conftest.py:1,35,41,77)                                        | ASYNC240: `# noqa` на `os.path.exists/remove`; ASYNC251: `time.sleep` → `await asyncio.sleep` + `import asyncio` |
| [`tests/test_cache.py`](../tests/test_cache.py:50)                                            | ASYNC240: `# noqa` на `os.path.exists`                                                                           |
| [`tests/test_keyboards.py`](../tests/test_keyboards.py:108)                                   | E501: разбита длинная строка тестовых данных                                                                     |

**Результаты проверок:**

| Инструмент                              | Результат                         |
| --------------------------------------- | --------------------------------- |
| `ruff check src scripts tests`          | **All checks passed!** ✅         |
| `ruff format --check src scripts tests` | **39 files already formatted** ✅ |
| `pytest tests/ -v`                      | **134 passed in 16.97s** ✅       |

---

## 2026-05-12 (конфиг-файлы: актуализация)

### Проверка и дополнение pyrightconfig.json, pyproject.toml, .vscode/settings.json ✅

**Задача:** Проверить актуальность 4 конфигурационных файлов проекта, исправить недостающие настройки.

**Итог по файлам:**

| Файл                                                | Вердикт                                                                                          |
| --------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| [`.vscode/launch.json`](../.vscode/launch.json)     | ✅ Актуален, правки не нужны                                                                     |
| [`pyrightconfig.json`](../pyrightconfig.json)       | ❌ Не хватало `pythonVersion`, `typeCheckingMode`, `include`, `exclude`                          |
| [`pyproject.toml`](../pyproject.toml)               | ❌ Не хватало `target-version`, `exclude`, `[tool.ruff.format]`                                  |
| [`.vscode/settings.json`](../.vscode/settings.json) | ❌ Не хватало `python.analysis.extraPaths`, `typeCheckingMode`, `[python]` секции форматирования |

**Изменённые файлы:**

| Файл                                                | Что добавлено                                                                                                                       |
| --------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| [`pyrightconfig.json`](../pyrightconfig.json)       | `pythonVersion: "3.14"`, `typeCheckingMode: "basic"`, `include: ["src","scripts","tests"]`, `exclude`                               |
| [`pyproject.toml`](../pyproject.toml)               | `target-version = "py314"`, `exclude`, `[tool.ruff.format]` с quote-style и indent-style; убран `fixable = ["ALL"]` (дефолт)        |
| [`.vscode/settings.json`](../.vscode/settings.json) | `python.analysis.extraPaths`, `python.analysis.typeCheckingMode`, `[python]` секция (ruff formatter, formatOnSave, organizeImports) |

**Результаты тестов:** Не запускались

---

## 2026-05-12 (Sentry + NTFY full setup)

### Подключение Sentry DSN и NTFY ✅

**Задача:** Настроить оба канала оповещений (Sentry + NTFY), заполнить отсутствующие параметры в `.env`.

**Изменённые файлы:**

| Файл                                                                    | Действие                                                                                                                                                                                                         |
| ----------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [`.env`](../.env:18-34)                                                 | Добавлены секции Error notifications (M2) и Rate limiting (M3): `ERROR_NOTIFY_ENABLED`, `NTFY_TOPIC_URL=https://ntfy.sh/ltb_alert`, `SENTRY_DSN`, `ENVIRONMENT`, `USER_RATE_LIMIT_MAX`, `USER_RATE_LIMIT_PERIOD` |
| [`services/error_notifier.py`](../src/services/error_notifier.py:35-36) | В `_init_sentry()` добавлены `send_default_pii=True` и `enable_logs=True`                                                                                                                                        |

**Результаты тестов:** Не запускались

---

## 2026-05-12 (env audit)

### Аудит .env и .env.example ✅

**Задача:** Проверить расхождения между [`.env`](../.env:1) и [`.env.example`](../.env.example:1), актуальность параметров в коде, объяснить настройку `NTFY_TOPIC_URL` и `SENTRY_DSN`.

**Выявлено:** В `.env` отсутствуют 6 параметров (против `.env.example`): `ERROR_NOTIFY_ENABLED`, `NTFY_TOPIC_URL`, `SENTRY_DSN`, `ENVIRONMENT`, `USER_RATE_LIMIT_MAX`, `USER_RATE_LIMIT_PERIOD`. Все они имеют безопасные дефолты в [`config.py:80-94`](../src/config.py:80), поэтому бот работает корректно.

**Все параметры из `.env.example` подтверждены как используемые:**

- `ERROR_NOTIFY_ENABLED` → проверка в [`error_notifier.notify()`](../src/services/error_notifier.py:54)
- `NTFY_TOPIC_URL` → HTTP POST в [`error_notifier._notify_ntfy()`](../src/services/error_notifier.py:58,88-89)
- `SENTRY_DSN` → инициализация SDK в [`error_notifier._init_sentry()`](../src/services/error_notifier.py:27,33)
- `ENVIRONMENT` → тег в [`sentry_sdk.init()`](../src/services/error_notifier.py:35)
- `USER_RATE_LIMIT_MAX` / `USER_RATE_LIMIT_PERIOD` → [`ratelimit.py:42-47`](../src/middleware/ratelimit.py:42-47)
- Все ключи синхронизируются с таблицей `config` БД через [`load_config_from_db()`](../src/config.py:102)

**Изменённые файлы:** Нет (только анализ)

**Результаты тестов:** Не запускались

---

## 2026-05-12 (project cleanup)

### Очистка мусорных и временных файлов ✅

**Аудит структуры проекта** выявил несколько проблем:

| #   | Файл                             | Статус                                             |
| --- | -------------------------------- | -------------------------------------------------- |
| 1   | `$null`                          | Артефакт терминала/VSCode — **удалён**             |
| 2   | `PySocks-1.7.1-py3-none-any.whl` | Бинарный wheel в git — **удалён из git и с диска** |
| 3   | `.mypy_cache/`, `.ruff_cache/`   | Не были в `.gitignore` — **добавлены**             |
| 4   | `*.whl`                          | Не было правила в `.gitignore` — **добавлено**     |

### Изменённые файлы

| Файл                             | Действие                                                                                                                                 |
| -------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| `$null`                          | Удалён                                                                                                                                   |
| `PySocks-1.7.1-py3-none-any.whl` | Удалён (`git rm --cached` + `del`)                                                                                                       |
| [`.gitignore`](../.gitignore:1)  | Добавлены `.mypy_cache/`, `.ruff_cache/`, `*.whl`; `data/monitoring_cache.json` + `*.db*` заменены на `data/`; структурирован по секциям |

### Дополнительно выявлено (не требует действий)

- Stale VSCode табы (7 шт.) — файлы на диске отсутствуют, нужно закрыть вручную в редакторе.
- [`pyproject.toml`](../pyproject.toml) — есть на диске, но не закоммичен.

---

## 2026-05-12 (zdrav API retry + logging fix)

### Добавлен retry и улучшено логирование в ZdravClient ✅

**Диагностика:** В логе [`logs/error.log:6813`](../logs/error.log:6813) зафиксирован шквал ошибок API zdrav.lenreg.ru (15 ошибок за 1.5 мин) при старте бота в 10:13. При этом сервер zdrav.lenreg.ru был доступен (тестовые скрипты подтвердили 200 OK), а сообщения ошибок в логе были пустыми: `Ошибка API (fetch_speciality_list):`.

**Корневые причины (2 бага):**

1. **Отсутствие retry** в методах `fetch_speciality_list` и `fetch_clinic_list`. При 69 одновременных Discovery-циклах на старте один таймаут/сбой сети приводил к потере данных без повторных попыток. Методы `check_slots` и `fetch_all_doctors` уже имели retry — неконсистентность.

2. **Битое логирование:** httpx исключения могут иметь пустой `str()` (например `ConnectError('')` → `str()` = `''`). Все 5 методов использовали `f"...: {e}"`, что давало невидимые ошибки.

**Исправления в [`api/zdrav_client.py`](../src/api/zdrav_client.py):**

| Метод                   | Строки                                                                                                                                                                                            | Изменения                                                                                      |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| `fetch_speciality_list` | [136-162](../src/api/zdrav_client.py:136)                                                                                                                                                         | Добавлен retry (3 попытки, sleep 2s для 5xx/exception)                                         |
| `fetch_clinic_list`     | [265-294](../src/api/zdrav_client.py:265)                                                                                                                                                         | Добавлен retry (3 попытки, sleep 2s для 5xx/exception)                                         |
| Все 5 методов           | [119](../src/api/zdrav_client.py:119), [156](../src/api/zdrav_client.py:156), [206](../src/api/zdrav_client.py:206), [247](../src/api/zdrav_client.py:247), [288](../src/api/zdrav_client.py:288) | `{e}` → `{repr(e) if not str(e) else str(e)}` — логирование всегда показывает тип/текст ошибки |

<!-- markdownlint-disable-next-line MD024 -->

### Изменённые файлы

| Файл                                                    | Действие                             |
| ------------------------------------------------------- | ------------------------------------ |
| [`api/zdrav_client.py`](../src/api/zdrav_client.py:136) | Retry + фикс логирования в 5 методах |

---

## 2026-05-12 (ci.yml cleanup)

### Удалён лишний BOT_TOKEN из CI ✅

- **Причина:** предупреждение VS Code "Context access might be invalid: BOT_TOKEN" в [`.github/workflows/ci.yml`](../.github/workflows/ci.yml:28)
- **Анализ:** `BOT_TOKEN` не используется ни в одном тесте (поиск по `tests/` — 0 упоминаний). В [`config.py:32`](../src/config.py:32) есть fallback `"MUST_BE_OVERRIDDEN_IN_ENV"` — CI не требует этого секрета.
- **История:** строка была добавлена при создании CI-файла 2026-05-07 «на всякий случай».
- **Решение:** удалены строки 28-29 (`env:` + `BOT_TOKEN: ${{ secrets.BOT_TOKEN }}`) из [`ci.yml`](../.github/workflows/ci.yml:26).

<!-- markdownlint-disable-next-line MD024 -->

### Изменённые файлы

| Файл                                                         | Действие                                |
| ------------------------------------------------------------ | --------------------------------------- |
| [`.github/workflows/ci.yml`](../.github/workflows/ci.yml:26) | Удалены лишние строки `env`/`BOT_TOKEN` |

---

## 2026-05-11 (venv rebuild)

### Пересоздание .venv ✅

- Удалён старый `.venv` (содержал пути `d:\projects\bots\zdrav.lenreg` с прошлого диска)
- Создан новый `.venv` с Python 3.14.4 и корректным путём `z:\_projects\_bots\zdrav.lenreg\.venv`
- Установлены пакеты из [`requirements.txt`](../requirements.txt:1)
- Добавлены пропущенные зависимости: `pre-commit-hooks`, `types-aiofiles`, `types-cachetools`
- Исправлена mypy-ошибка: добавлена аннотация типа для `spam_cache` в [`utils/cache.py`](../src/utils/cache.py:15)

### Очистка requirements.txt ✅

- Удалены неиспользуемые пакеты:
  - `pytest-mock` — нигде не используется (тесты на `unittest.mock`)
  - `aioresponses` — нигде не используется (мокается `_get_client`)
- `PySocks` **оставлен как wheel-файл** — обязательная зависимость pip на этом окружении (VPN-клиент требует socks-модуль для urllib3)
- `.venv` пересоздан заново без лишних пакетов
- **Все 10 pre-commit хуков проходят**
- **Все 134 теста проходят** (pytest 9.0.3)

### Структурирование requirements.txt ✅

- Файл [`requirements.txt`](../requirements.txt:1) реорганизован в логические секции:
  - Core (aiogram), Configuration, HTTP & Networking, Proxy, Data & Storage, Rate Limiting, Error Notifications, Dev/Testing, Linting, Pre-commit
- `aiohttp-socks` снабжён комментарием о роли в прокси

<!-- markdownlint-disable-next-line MD024 -->

### Изменённые файлы

| Файл                                         | Действие                                                                                                                            |
| -------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `.venv/`                                     | Пересоздан                                                                                                                          |
| [`requirements.txt`](../requirements.txt:1)  | Удалены `pytest-mock`, `aioresponses`; добавлены `pre-commit-hooks`, `types-aiofiles`, `types-cachetools`; реорганизован по секциям |
| [`utils/cache.py`](../src/utils/cache.py:15) | Добавлена аннотация `spam_cache: TTLCache`                                                                                          |
| `PySocks-1.7.1-py3-none-any.whl`             | Удалён из корня (лежит только в .venv как служебная зависимость pip)                                                                |

## 2026-05-11 (M2 + M3)

### M2 — Error notifications (Sentry + NTFY) ✅

- Создан [`services/error_notifier.py`](../src/services/error_notifier.py:1) — централизованный диспетчер ошибок
- NTFY: HTTP POST на конфигурируемый топик (заголовок, приоритет, traceback)
- Sentry: опциональная интеграция через `sentry_sdk` (только при наличии `SENTRY_DSN`)
- Интегрировано в [`main.py`](../src/main.py:127) — `polling_crash` и [`main.py`](../src/main.py:154) — `startup_crash`
- Новые поля в [`config.py`](../src/config.py:81): `ERROR_NOTIFY_ENABLED`, `NTFY_TOPIC_URL`, `SENTRY_DSN`, `ENVIRONMENT`
- Добавлены в [`.env.example`](../.env.example:18) с комментариями
- `sentry-sdk>=2.0` добавлен в [`requirements.txt`](../requirements.txt:11)

### M3 — Per-user rate limiting ✅

- Создан [`middleware/ratelimit.py`](../src/middleware/ratelimit.py:1) — aiogram outer middleware
- Sliding window на основе списков timestamps (сообщения и callback-запросы раздельно)
- При превышении лимита: сообщения — silently dropped, callback — ответ «⏳ Слишком много запросов»
- Зарегистрирован в [`main.py`](../src/main.py:81) как `dp.update.outer_middleware(UserRateLimitMiddleware())`
- Новые поля в [`config.py`](../src/config.py:88): `USER_RATE_LIMIT_MAX` (30) и `USER_RATE_LIMIT_PERIOD` (60s)
- Добавлены в [`.env.example`](../.env.example:28)

<!-- markdownlint-disable-next-line MD024 -->

### Изменённые файлы

| Файл                                                                | Действие                                       |
| ------------------------------------------------------------------- | ---------------------------------------------- |
| [`services/error_notifier.py`](../src/services/error_notifier.py:1) | Создан                                         |
| [`middleware/__init__.py`](../src/middleware/__init__.py:1)         | Создан                                         |
| [`middleware/ratelimit.py`](../src/middleware/ratelimit.py:1)       | Создан                                         |
| [`config.py`](../src/config.py:1)                                   | Добавлены поля M2/M3                           |
| [`.env.example`](../.env.example:1)                                 | Добавлены секции M2/M3                         |
| [`main.py`](../src/main.py:1)                                       | Импорты + middleware + error_notifier в except |
| [`requirements.txt`](../requirements.txt:1)                         | Добавлен `sentry-sdk`                          |
| [`database/database.py`](../src/database/database.py:652)           | 4 поля в `seed_config_from_defaults()`         |
| [`.env.example`](../.env.example:18)                                | NTFY_TOPIC_URL + SENTRY_DSN → плейсхолдеры     |
| [`database/migrations.py`](../src/database/migrations.py:93)        | Миграция v5: `migrate_v5_seed_new_config_keys` |

### Config DB migration (M2/M3 follow-up)

- 4 нечувствительных поля перенесены в БД-синхронизацию: `ERROR_NOTIFY_ENABLED`, `ENVIRONMENT`, `USER_RATE_LIMIT_MAX`, `USER_RATE_LIMIT_PERIOD`
- 2 секретных поля остались только в `.env`: `NTFY_TOPIC_URL`, `SENTRY_DSN`
- Добавлены `CONFIG_KEY_*` константы + entries в `mapping` ([`config.py`](../src/config.py:104))
- Добавлены defaults в `seed_config_from_defaults()` ([`database/database.py`](../src/database/database.py:652))
- `.env.example`: секреты заменены на `your_..._here` плейсхолдеры
- Добавлена миграция v5 ([`database/migrations.py`](../src/database/migrations.py:93)) — сидирование **всех** 19 config-ключей через `INSERT OR IGNORE` (безопасна для существующих БД)
- Существующая `bot.db` обновлена: 4 новых ключа добавлены (19 total)

### Результаты тестов: 116 passed, 0 failed, 604 warnings (Python 3.14 deprecation notices)

---

## 2026-05-01

- Создана базовая структура проекта — прототип бота для мониторинга талонов
- Получен первый ответ от API zdrav.lenreg.ru с данными врачей
- Протестированы эндпоинты для проверки структуры данных
- Получен JSON со списком врачей для двух поликлиник (271, 272)

## 2026-05-03

- Исправлены Pylance-ошибки — добавлены проверки на `None` для `call.message` и `call.from_user`
- Исправлена инициализация сессии `AiohttpSession` в `main.py`
- Реализован метод `delete_patient` в `DatabaseManager` с inline-клавиатурой подтверждения
- Календарь aiogram заменён на ручной ввод даты рождения (`дд.мм.гггг`)
- Исправлена ошибка 405 — добавлены HTTP-заголовки (`X-Requested-With`, `Content-Type`, cookies с CSRF-токеном)

## 2026-05-04

- JSON-файлы (`doctors.json`, `users_config.json`) перемещены в `data/`
- Кнопка удаления пациента переделана на компактную (🗑) в одной строке с именем
- Терминология: слоты/талоны → номерки
- Реализовано уведомление при отсутствии номерков с обещанием уведомить о появлении
- Добавлен мгновенный запрос к API при выборе врача (мгновенная обратная связь)
- Добавлена защита от спама при множественных нажатиях
- При отключении мониторинга врача — удаление из кэша
- Реализован Discovery-механизм (автопоиск врачей) — фоновый цикл `discovery_loop`
- Создана БД `DoctorManager` с merge-обновлением (не затирает существующие данные)
- Поддержка трёх поликлиник: 271 (взрослая), 272 (стоматологическая), 161 (детская)
- Добавлены retries при 502 ошибках API и рандомизация задержек (jitter)
- Реализован выбор поликлиники при регистрации с фильтрацией по возрасту
- Данные пользователя теперь включают `clinic_id`

## 2026-05-05

- Удалена кнопка "Удалить пациента" из списка врачей (была лишней)
- Исправлен `clinic_id` при мониторинге — теперь учитывается для каждого врача индивидуально
- Добавлена обработка `TelegramBadRequest: message is not modified` во всех `edit_text` вызовах

## 2026-05-06

- Добавлена база знаний API в `docs/knowledge/`: `check_patient.md`, `speciality_list.md`, `doctor_list.md`, `appointment_list.md`, `_INDEX.md`
- Исправлены ложные уведомления "Номерков нет" при первом включении мониторинга
- Добавлена синхронизация кэша в `handlers/common.py` после выбора врача
- API-клиент теперь различает ошибки API и отсутствие номерков
- Реализована атомарная запись кэша (файловый lock `asyncio.Lock`)
- Кэш загружается перед каждой итерацией цикла проверки (не единожды при старте)
- `clinic_id` сохраняется для каждого врача индивидуально
- Добавлен механизм "3 пустых ответа подряд" перед сбросом кэша
- Удалены жёстко закодированные `BOT_TOKEN` и `PROXY_URL` из `config.py`
- Создан `.env.example` для конфигурации через переменные окружения
- Добавлен `aiolimiter` (10 запросов/мин) для предотвращения 429 ошибок
- Устранена утечка памяти в `spam_cache` — заменён на `cachetools.TTLCache` (maxsize=1000, ttl=1s)
- Реализован асинхронный доступ к файлу кэша (race condition между monitor_loop и обработчиками)
- Добавлена папка `utils/` с модулем `cache.py`, настроен `.gitignore`, обновлена структура проекта
- Репозиторий пересоздан на GitHub (очищена история коммитов)

## 2026-05-07

- Проведён полный анализ архитектуры проекта
- Создана тестовая инфраструктура: `conftest.py`, `test_database_manager.py` (14), `test_doctor_manager.py` (7), `test_cache.py` (12), `test_monitor_classify.py` (12), `test_zdrav_client.py` (20) — **65 тестов, все проходят**
- Создан `services/healthcheck.py` — модуль мониторинга здоровья бота: `HealthMetrics` (dataclass), `healthcheck_loop()`, `format_status_report()`
- Команда `/status` выводит аптайм, статистику пользователей, состояние API, фоновые задачи
- `healthcheck_loop` и `monitor_loop` интегрированы в `main.py` как фоновые задачи
- Исправлена валидация `IdDoc` и `Name` в `doctor_manager.py` (устранена запись врачей с `None`)
- Исправлены Pylance-ошибки: удалены неиспользуемые импорты, дублирующие фикстуры
- **Вечер**: Pydantic v2: `Config` → `SettingsConfigDict` в `config.py`
- **Вечер**: Создан `.github/workflows/ci.yml` — CI-пайплайн (pytest на push/PR в main), 65 тестов проходят

## 2026-05-08

- Создан `database/database.py` — единый SQLite-движок (WAL-режим, busy_timeout, автосоздание таблиц)
- `database/manager.py` и `database/doctor_manager.py` переписаны как адаптеры поверх Database
- Миграция существующих JSON-данных в SQLite при первом запуске
- В `config.py` добавлен `DB_PATH`, убраны `DOCTORS_PATH`/`USERS_JSON_PATH`
- Из `handlers/common.py` удалена функция `get_doctors_for_clinic()` (читавшая JSON)
- Все тесты переведены на временные SQLite-файлы — 64/64 проходят
- Удалены `data/doctors.json` и `data/users_config.json`
- Установлен `aiosqlite`, обновлён `.env`/`.env.example`
- **Ревью**: исправлено 8 проблем безопасности: единая транзакция в `update_user()`, whitelist `_ALLOWED_FIELDS` (SQL-injection), `data` → `deepcopy`, `assert` → `raise`, убран мусорный код, упрощён INSERT, убран `.copy()` в `monitor.py`
- Иконки (эмодзи) перенесены из ветки `main` в `test` (3 файла)
- Счётчик врачей в кнопках клиник, кабинеты внизу списка
- Псевдонимы для ФИО и ~50 специальностей (`shorten_fio`, `shorten_specialty`)
- Убран разделитель "Кабинеты", убран alert при повторном нажатии (TTL 1 сек)
- Кнопки сброса мониторинга: `stop_all`, `stop_patient_{p_id}`, `stop_clinic_{p_id}_{clinic_id}`
- При отключении/сбросе — удаление связанных сообщений из чата
- Создан `utils/helpers.py` — `is_cabinet()`, `shorten_fio()`, `shorten_specialty()`
- В `utils/cache.py` добавлена `delete_cache_keys_by_prefix()`

## 2026-05-09

### Фильтрация по возрасту в стоматологии

- Добавлена `is_child(bday_str)` в `utils/helpers.py` — проверка < 18 лет
- `get_doctor_selection()` фильтрует врачей клиники 272 по возрасту: дети — только "детск", взрослые — всё кроме "детск"
- В `handlers/common.py` передан `bday_str` во все вызовы `get_doctor_selection()`

### Устранение хардкодов

- В `config.py` добавлены: `API_BASE_URL`, `REFERER_URL`, `CSRF_TOKEN`, `DEFAULT_CLINIC_ID`, `DEFAULT_BIRTHDAY`
- `api/zdrav_client.py`: вынос base_url, Referer, CSRF-токена в settings
- `handlers/registration.py`: исправлена битая UTF-8 кодировка; `"272"` → `settings.DEFAULT_CLINIC_ID`
- `services/doctor_discovery.py`: `"161"` → `CLINICS_REGISTRY`; для стоматологии — discovery с обоими patient_id
- `keyboards/inline.py`: удалён дублирующий словарь `clinics` → импорт `CLINICS_REGISTRY`
- `handlers/common.py`: `"1990-01-01"` → `settings.DEFAULT_BIRTHDAY`
- `services/monitor.py`: `"272"` → `settings.DEFAULT_CLINIC_ID`
- 64/64 тестов пройдены

## 2026-05-10

### Аудит keyboards/inline.py

- Удалён мёртвый код: `get_main_menu()`, `ReplyKeyboardBuilder`, неиспользуемый `from aiogram import types`
- Убран импорт `get_main_menu` из `handlers/common.py`

### Команда /status + healthcheck

- Добавлен `ADMIN_IDS` в `config.py` (строка, парсинг через split)
- Добавлен хэндлер `cmd_status` с проверкой прав
- Убран неиспользуемый параметр `api` из `format_status_report()`

### Автоудаление сообщений (TTL)

- Добавлены `MESSAGE_TTL_SECONDS=604800` и `CLEANUP_INTERVAL=3600` в `config.py`
- Создан `services/cleanup.py` — фоновая задача автоудаления старых сообщений
- `set_last_message_id()` сохраняет `{"msg_id": ..., "ts": ...}`, `get_last_message_id()` читает оба формата
- Создан `utils/helpers.extract_msg_id()` — единая функция разбора
- Единый механизм удаления: `_delete_cleanup_msg_entry()` / `_delete_cleanup_msg_entries()` в `handlers/common.py`
- Все сценарии (стоп врача/пациента/клиники/всего) используют единые функции

### Скрытие кнопок при пустом списке

- Кнопка "Сбросить весь мониторинг" — только при наличии пациентов
- При возврате/удалении последнего пациента — приветствие с одной кнопкой "➕ Добавить пациента"
- Реализован возврат к списку пациентов при добавлении нового (если список не пуст)
- Обновлена клавиатура `get_skip_alias_keyboard` и обработчик `process_bday` в регистрации

### Единый формат уведомлений

- Добавлены эмодзи в заголовки: 🎉 (появление), ⚠️ (уменьшение), 🤷‍♂️ (нет номерков), 🔗 (ссылка)
- Унифицирована вёрстка: `🧑‍⚕️ {name}`, без двоеточия, заглавная П, убрано "они"
- Тесты `test_monitor_classify.py` — 12/12 пройдено

### Нормализация БД

- Поля `patients`, `monitoring` вынесены в таблицы `user_patients`, `user_monitoring`
- `last_messages` нормализованы в `user_last_messages`
- Удалены колонки `patients`, `monitoring`, `last_messages`, `last_notification_id`, `extra` из `users`
- Удалена таблица `users` (миграция v4)
- Удалён мёртвый код: `migrate_from_json`, `_run_migrations`, `ensure_user`, `save()`, `test_normalization.py` и др. (—130 строк в database.py, —20 в manager.py)
- При удалении пациента — удаление всех связанных сообщений из чата
- Все 64 теста пройдены

## 2026-05-11 (раннее утро)

### Динамические названия клиник из API

- В базу данных добавлены названия клиник из API `/api/clinic_list/` — таблица `clinics` заполняется реальными названиями
- Добавлен метод `fetch_clinic_list()` в `api/zdrav_client.py`
- Добавлена функция `sync_clinic_names()` в `services/doctor_discovery.py`, вызывается при старте бота
- Исправлен `merge_doctors()` — больше не перезаписывает название клиники, если оно уже установлено
- Добавлены методы `get_clinic_name()`, `get_all_clinic_names()` в `database/database.py` и `database/manager.py`
- В кнопки выбора поликлиники подставляются сокращённые названия из API (только тип отделения)
- В заголовок сообщения при выборе врачей добавлено полное название поликлиники из API
- Добавлен обработчик `skip_alias` в `handlers/registration.py` — при пропуске alias=None (чистое хранение)
- Добавлена сортировка пациентов по алфавиту в `keyboards/inline.py` (get_patient_selection, fallback на ФИО)
- Кнопка "Сбросить весь мониторинг" показывается только при наличии активного мониторинга
- Добавлены сокращения для стоматологических специальностей:
  - "Стоматология детская" → "Дет. стоматология"
  - "Стоматология профилактическая" → "Стоматология проф."
  - "Стоматология (средний медперсонал)" → "Ср. медперсонал"

## 2026-05-11 (основная сессия)

### Полный вынос хардкода в БД

- **Удалён `CLINICS_REGISTRY`** (хардкод трёх клиник: 161, 271, 272) из всех файлов:
  - `config.py` — удалены константы CLINICS, CLINICS_REGISTRY
  - `database/database.py` — удалён `seed_clinics_from_fallback()`, исправлен `merge_doctors()`
  - `services/doctor_discovery.py` — убран CLINICS_REGISTRY из импорта и fallback
  - `services/healthcheck.py` — убран CLINICS_REGISTRY из импорта и `format_status_report()`
  - `services/monitor.py` — убран CLINICS_REGISTRY из импорта
  - `handlers/common.py` — убран CLINICS_REGISTRY из импорта
  - `main.py` — убран fallback на `settings.CLINICS` при пустой таблице clinics
  - `keyboards/inline.py` — убрана ветка с CLINICS_REGISTRY в `get_clinic_selection()`
- **Таблица `config`** — 15 параметров из `.env`/`settings` синхронизированы в БД:
  - `api_timeout`, `check_interval`, `discovery_interval`, `message_ttl_seconds`, `cleanup_interval`
  - `slot_threshold_absolute`, `slot_threshold_percentage`
  - `discovery_patient_adult`, `discovery_patient_child`
  - `default_clinic_id`, `default_birthday`, `api_base_url`, `referer_url`, `csrf_token`, `admin_ids`
- **`seed_config_from_defaults()`** — автозаполнение таблицы config из settings при первом запуске
- **`seed_specialty_aliases_from_fallback()`** — автозаполнение таблицы specialty_aliases
- **`load_config_from_db()`** — переопределение settings значениями из БД
- **`load_specialty_aliases_from_db()`** — загрузка псевдонимов из БД
- **Per-клиника discovery пациенты** — колонки `discovery_patient_adult`/`discovery_patient_child` в `clinics`

### Баги

- **`back_to_clinics`** — неправильный парсинг `split("_", 3)` → `split("_")` без лимита. Был бонусный баг: условие `len(parts) >= 6` для `city_idx` не срабатывало на массиве из 5 элементов
- **Кнопка "К выбору города"** — теперь всегда видна (убрано `if not show_all`)

### Кнопки сброса (единый дизайн)

- Счётчики мониторинга в кнопках городов: `📍 Всеволожск (3)`
- **`stop_patient_{p_id}_city`** — сброс пациента из меню городов, остаётся на городах
- **`stop_patient_{p_id}_clinic_{city_idx}`** — сброс пациента из меню клиник, остаётся на клиниках (с фильтром города)
- **`stop_clinic_{p_id}_{clinic_id}`** — сброс клиники из меню врачей, остаётся на врачах
- Все кнопки сброса **скрываются**, если мониторинг в данном контексте отсутствует
- Все кнопки сброса **не перекидывают** в другое меню — обновляют текущее

### UX: задержка при выборе врача

- `toggle_doctor` теперь отправляет `"⏳ Проверяю наличие номерков..."` **до** HTTP-запроса
- После ответа API — `loading_msg.edit_text(text)` (редактирование того же сообщения)
- Добавлен `aiofiles` в импорты `handlers/common.py`
- Кэш при включении пишется асинхронно (через `aiofiles`)
- Пользователь видит мгновенную обратную связь вместо 1-10 сек ожидания

### Обновление задач

- `B3` — синхронный JSON заменён на асинхронный (`aiofiles`), но не на `update_cache_key()` из `utils/cache.py` (частично)
- `B5` — импорт `metrics` внутри `monitor_loop()` остаётся из-за циклического импорта (не вынесен)
- `R6` — `CLINICS_REGISTRY` удалён, задача неактуальна
- `TASK.md` — план выноса параметров в БД выполнен

## 2026-05-11 (аудит кода)

- Проведён аудит кода на хардкод, мусорный, излишний и мёртвый код
- Найдено 38 проблем:
  - Хардкод — 15 (rate limits, retry counts, User-Agent, clinic_id "272", district_id "4", задержки)
  - Мусорный код — 4 (баг + дубликат в apply_city_heuristic.py, нерабочий migrate_configs_to_db.py, дублирование CREATE TABLE, копипаста detect_clinic_city)
  - Излишний код — 8 (неиспользуемый in-memory кэш в DoctorManager, пустой save(), обёртка \_delete_monitoring_messages, невызываемая update_cache_key, устаревший комментарий в healthcheck)
  - Мёртвый код — 11 (5 неиспользуемых функций в utils/cache.py, сломанный migrate_configs_to_db.py, баг-дубликат в apply_city_heuristic.py, 4 одноразовых скрипта, пустой utils/**init**.py)
- Топ-5 критичных:
  1. migrate_configs_to_db.py — импорт несуществующего CLINICS_REGISTRY (скрипт сломан)
  2. apply_city_heuristic.py — баг `if city:` + дубликат кода после commit
  3. keyboards/inline.py — хардкод clinic_id == "272" для фильтрации детских/взрослых
  4. utils/cache.py — 5 функций (~100 строк) нигде не вызываются
  5. database/doctor_manager.py — in-memory кэш self.data загружается, но не используется

- Проведён второй аудит (18 файлов) после исправлений. Выявлен 21 дефект, все устранены.

### Исправления (2026-05-11, вторая итерация)

**Удалён мёртвый код (6):**

- `_migrate_add_tables()` в database/database.py — таблицы уже создаются в `_create_tables()`
- `save()` в database/doctor_manager.py — пустой no-op метод
- `set_specialty_aliases()` в utils/helpers.py — не вызывалась
- `check_affiliation()` в api/zdrav_client.py — проверка прикрепления убрана
- `_delete_monitoring_messages()` в handlers/common.py — обёртка-прокладка, заменена на `_delete_cleanup_msg_entries`
- `upsert_clinic_full()` в database/database.py — неполный дубликат `upsert_clinic()`

**Убран излишний код (1):**

- `hasattr(doctor_manager, "_db")` → `doctor_manager._db` в services/doctor_discovery.py

**Хардкоды (2):**

- `clinic_id == "272"` → `DENTAL_CLINIC_ID = "272"` в keyboards/inline.py
- `DB_PATH = "data/bot.db"` → `settings.SQLITE_DB_PATH` в scripts/apply_city_heuristic.py и apply_heuristic_types.py

**Дубликаты в скриптах (2):**

- apply_city_heuristic.py: удалён дубликат `detect_clinic_city()`, заменён на `from database.database import detect_clinic_city`
- apply_heuristic_types.py: удалён дубликат `detect_clinic_type()`, заменён на `from database.database import detect_clinic_type`

**Гонка (1):**

- handlers/common.py: прямое чтение/запись JSON-файла кэша заменено на `delete_cache_keys_by_prefix()` из utils/cache.py

**Нерабочий скрипт (1):**

- scripts/migrate_configs_to_db.py удалён (импортировал отсутствующий `CLINICS_REGISTRY`)

**Тесты (1):**

- tests/test_cache.py переписан: удалены импорты несуществующих функций, тесты используют реальные `swap_cache_key` / `delete_cache_keys_by_prefix`

### Дополнительное исправление (2026-05-11, повторная верификация)

- **Гонка в `toggle_doctor` (ветка ON)** — в handlers/common.py инлайн `asyncio.Lock()` (новый лок на каждый вызов = нет реальной блокировки) + прямое чтение/запись JSON-файла заменены на `await swap_cache_key()`. Попутно удалены неиспользуемые импорты `json`, `os`, `aiofiles`.

### B1 — Async `get_user_data()` + `asyncio.Lock` (2026-05-11)

**Изменённые файлы:**

- `database/manager.py`:
  - Добавлен `import asyncio`, `import time` наверх модуля
  - В `__init__` добавлен `self._lock = asyncio.Lock()`
  - `get_user_data()` переписан на `async def` — захватывает `self._lock`, делегирует приватному `_get_user_data_nolock()`
  - `_get_user_data_nolock(uid)` — синхронный метод, вызывается **только** под локом
  - `get_last_message_id()` сделан `async def` с захватом `self._lock`
  - Все мутирующие кэш методы обёрнуты в `async with self._lock`: `update_user`, `set_last_message_id`, `add_patient`, `add_confirmed_clinic`, `toggle_monitoring`, `stop_all_monitoring`, `delete_patient`, `refresh_cache`

- `handlers/common.py` — все 13 вызовов `db.get_user_data(uid)` → `await db.get_user_data(uid)`
- `handlers/registration.py` — 3 вызова → `await`
- `services/monitor.py` — `db.get_last_message_id(...)` → `await db.get_last_message_id(...)`
- `tests/test_database_manager.py` — 5 вызовов → `await`

**Тесты:** 15/15 passed, полный suite: 56 passed, 3 failed (предсуществующие — `check_affiliation` удалён из `ZdravClient`)

## 2026-05-11 (B2 — очистка empty_counts)

### B2 — Очистка `empty_counts` от неактивных ключей

**Проблема:** `empty_counts = {}` в [`services/monitor.py`](../src/services/monitor.py:90) — словарь рос бесконечно, ключи никогда не удалялись при отписке от врача или удалении пациента. Реальный риск был низким (типично 20–750 записей), но при долгоживущем процессе мог накапливаться.

**Решение:** Добавлена очистка неактивных ключей в начале каждого цикла `while True` (`services/monitor.py:96-105`):

- Собирается множество `active_keys` на основе текущих данных `db.data["monitoring"]`
- Все ключи `empty_counts`, отсутствующие в `active_keys`, удаляются

**Почему не `TTLCache`:** `TTLCache` сломал бы логику защиты от ложных пустых ответов (3 retry) — TTL сбрасывал бы счётчик при длительном отсутствии слотов, а `maxsize` мог вытеснить активные ключи.

**Файлы:**

- [`services/monitor.py`](../src/services/monitor.py) — добавлена очистка `empty_counts` (строки 96-105)
- [`docs/AGENT_TASKS.md`](AGENT_TASKS.md) — B2 отмечен выполненным

### Удаление тестов `check_affiliation`

**Проблема:** 3 теста в [`tests/test_zdrav_client.py`](../tests/test_zdrav_client.py:97-119) падали с `AttributeError: 'ZdravClient' object has no attribute 'check_affiliation'`. Метод был удалён из [`api/zdrav_client.py`](../src/api/zdrav_client.py) ранее, но тесты остались.

**Решение:** Удалены 3 теста (`test_check_affiliation_success`, `test_check_affiliation_failure`, `test_check_affiliation_error`). Поиск `check_affiliation` по проекту подтвердил: метод не используется нигде, кроме тестов.

**Результат:** 56/56 passed.

### `scripts/run_tests.py` — постоянный скрипт для запуска тестов

**Проблема:** PowerShell-терминал искажает вывод pytest с кириллицей (баг кодировки pwsh + Python в Windows). Каждый раз приходилось создавать временный `_run_tests.py`.

**Решение:** Создан постоянный скрипт [`scripts/run_tests.py`](../scripts/run_tests.py), который:

- Запускает pytest через `subprocess.run(capture_output=True)`, обходя проблемную консоль
- Сохраняет полный вывод в `.pytest_output.txt` (добавлен в `.gitignore`)
- Принимает аргументы: `python scripts/run_tests.py -v --tb=short` или `python scripts/run_tests.py -k test_cache`

**Использование:** `.venv\Scripts\python.exe scripts\run_tests.py [аргументы pytest]`

---

## 2026-05-11 (R1 — Pydantic модели)

### R1 — Pydantic модели API ✅

Создан [`api/models.py`](../src/api/models.py) с 11 Pydantic-моделями для валидации ответов API zdrav.lenreg.ru:

| Эндпоинт           | Модель ответа             | Модель элемента    |
| ------------------ | ------------------------- | ------------------ |
| `check_patient`    | `CheckPatientResponse`    | `CheckPatientData` |
| `speciality_list`  | `SpecialityListResponse`  | `SpecialityItem`   |
| `doctor_list`      | `DoctorListResponse`      | `DoctorItem`       |
| `appointment_list` | `AppointmentListResponse` | `AppointmentSlot`  |
| `clinic_list`      | `ClinicListResponse`      | `ClinicItem`       |

Общие: `DateInfo` (с алиасами `day_verbose`/`month_verbose`), `ApiError` (`extra="allow"`).

**Изменения в [`api/zdrav_client.py`](../src/api/zdrav_client.py):**

- Все 5 методов (`fetch_patient_id`, `fetch_speciality_list`, `check_slots`, `fetch_all_doctors`, `fetch_clinic_list`) валидируют ответ через `model_validate()` вместо сырых `.get()`.
- Обратная совместимость полностью сохранена (возвращаемые типы не изменены).

**Попутный фикс в [`config.py`](../src/config.py:76):** Добавлен `extra="ignore"` в `SettingsConfigDict` — `PYTHONUTF8` из `.env` больше не ломает загрузку конфига.

### B4 — проверка ✅

Подтверждено: [`process_alias`](../src/handlers/registration.py:95) и [`skip_alias`](../src/handlers/registration.py:132) уже содержат `try/except` + `state.clear()` в обоих путях. Задача выполнена ранее.

### Результаты тестов

Все 56 тестов пройдены (0 предупреждений, 14.5 сек).

---

## 2026-05-11 (сверка)

### Удаление B1, B2 из AGENT_TASKS.md

- B1 и B2 были выполнены (SESSION_LOG.md строки 284-319), но оставались в таблице `AGENT_TASKS.md`
- Удалены B1, B2 из таблицы «Критические баги»
- Секция `## 🔴 Критические баги` удалена целиком (стала пустой)
- Сверены оба файла — несоответствий больше нет

---

## 2026-05-11 (T4 — тесты клавиатур)

### T4 — Тесты для `keyboards/inline.py`

Создан [`tests/test_keyboards.py`](../tests/test_keyboards.py) — 37 тестов, покрывающих все 6 функций-клавиатур и вспомогательную `_short_clinic_label`:

| Класс тестов               | Функция                     | Тестов |
| -------------------------- | --------------------------- | ------ |
| `TestRegistrationKeyboard` | `get_registration_keyboard` | 3      |
| `TestConfirmDeletion`      | `get_confirm_deletion`      | 2      |
| `TestShortClinicLabel`     | `_short_clinic_label`       | 5      |
| `TestPatientSelection`     | `get_patient_selection`     | 6      |
| `TestCitySelection`        | `get_city_selection`        | 5      |
| `TestDoctorSelection`      | `get_doctor_selection`      | 8      |
| `TestClinicSelection`      | `get_clinic_selection`      | 8      |

**Проверяемые сценарии:**

- Сортировка пациентов по alias/fio, счётчики мониторинга `(N)`, кнопка «Сбросить всё» при активном мониторинге
- Кнопки подтверждения удаления с корректными callback_data
- Сокращение длинных названий клиник: выделение части после кавычек `"`, fallback на 50 символов
- Клавиатуры регистрации: шаг `alias` с кнопкой «Пропустить», все шаги с «Отмена регистрации»
- Города с 1-based индексами, счётчики мониторинга на город, «Все города»
- Врачи: сортировка по специальности→фамилии, кабинеты отдельно, статус ✅/▫️
- Фильтр детских специальностей в стоматологии (клиника 272): дети видят только "детск", взрослые — наоборот
- Фильтрация клиник по возрасту (adult/child/all) и городу
- Навигационные кнопки («К выбору города», «Назад к списку»)
- Передача `city_idx` в callback_data кнопки сброса

**Результат:** 93/93 passed (56 базовых + 37 новых), 14.5 сек.

**Файлы:**

- [`tests/test_keyboards.py`](../tests/test_keyboards.py) — новый файл, 37 тестов

## 2026-05-11 (T3 — тесты doctor_discovery)

### Задача T3: Тесты для `services/doctor_discovery.py`

- Изучен модуль [`services/doctor_discovery.py`](../src/services/doctor_discovery.py) — 4 функции: `fetch_specialties`, `_get_clinic_type_from_db`, `discovery_loop`, `sync_clinic_names`
- Создан [`tests/test_doctor_discovery.py`](../tests/test_doctor_discovery.py) — 23 теста в 5 классах:

| Класс                           | Тестируемая функция                         | Тестов |
| ------------------------------- | ------------------------------------------- | ------ |
| `TestFetchSpecialties`          | `fetch_specialties`                         | 6      |
| `TestGetClinicTypeFromDb`       | `_get_clinic_type_from_db`                  | 4      |
| `TestDiscoveryPatientSelection` | логика выбора patient_id в `discovery_loop` | 5      |
| `TestSyncClinicNames`           | `sync_clinic_names`                         | 8      |

**Проверяемые сценарии:**

- Успешный парсинг списка специальностей, пустой ответ, исключения API
- Фильтрация специальностей без `IdSpesiality` / `NameSpesiality`
- Приведение нестроковых значений к строке
- Определение типа клиники из БД: найдено / `None` / пустая строка / исключение → `'adult'`
- Выбор patient_id: adult-клиника → только взрослый, child-клиника → только детский, all → оба
- Переопределение patient_id через `clinic_discovery_patients` (per-clinic override)
- Успешная синхронизация названий клиник, пустой список, `None`, исключение API
- Fallback на `LPUShortName` при отсутствии `LPUName`
- Пропуск записей без ID / без имени, конвертация `int` ID → `str`

**Попутно исправлен баг** в [`services/doctor_discovery.py:132-135`](../src/services/doctor_discovery.py:132):

- `str(None)` → `"None"` (truthy), из-за чего записи с `IdLPU = None` попадали в `upsert_clinic` как `("None", "Без ID")`
- Добавлена проверка `if raw_id is None: continue` перед `str(raw_id)`

**Результат:** 116/116 passed (93 базовых + 23 новых), 15.03 сек.

**Файлы:**

- [`tests/test_doctor_discovery.py`](../tests/test_doctor_discovery.py) — новый файл, 23 теста
- [`services/doctor_discovery.py`](../src/services/doctor_discovery.py) — исправлен баг `str(None)` в `sync_clinic_names`

### Оптимизация потребления памяти при тестах

**Проблема:** python.exe потреблял >20 GB RAM при прогоне 116 тестов.

**Выявленные причины (4):**

| #   | Причина                                   | Механизм                                                                     |
| --- | ----------------------------------------- | ---------------------------------------------------------------------------- |
| 1   | SQLite WAL-файлы не усекались             | `PRAGMA journal_mode=WAL` + 116 отдельных БД = накопление WAL без checkpoint |
| 2   | `aiolimiter.AsyncLimiter` не освобождался | Каждый `ZdravClient` создавал limiter, привязанный к event loop              |
| 3   | `MagicMock` цепочки атрибутов             | Бесконечная рекурсия `mock.anything.anything...` при assertion introspection |
| 4   | Незавершённые `asyncio.Task`              | `asyncio_mode=auto` + забытый `create_task` = висящие корутины               |

**Реализованные исправления:**

- [`database/database.py:158-167`](../src/database/database.py:163) — `PRAGMA wal_checkpoint(TRUNCATE)` в `Database.close()`: усекает WAL до 0 байт перед закрытием соединения
- [`tests/conftest.py:51-52`](../tests/conftest.py:52) — `gc.collect()` после `await db.close()` в фикстуре `database`
- [`tests/conftest.py:30-42`](../tests/conftest.py:30) — `gc.collect()` + 5 попыток удаления с задержкой 0.2s в `temp_db_path`
- [`tests/test_zdrav_client.py:22-25`](../tests/test_zdrav_client.py:22) — `await client.close()` + `gc.collect()` в фикстуре `mock_zdrav_client` (был `return`, стал `yield`)
- [`tests/conftest.py:92-117`](../tests/conftest.py:94) — опциональный `tracemalloc`-мониторинг: включается `PYTEST_MEMORY_PROFILE=1`, показывает топ-5 аллокаций >100 KB на тест

**Результат:** 116/116 passed за 16.33 сек., `tests/test_data/` пуст после прогона (нет WAL/SHM-остатков).

---

## 2026-05-11 (R4, R5, R7)

### R7 — Отдельные `AsyncLimiter` для monitor / discovery / healthcheck

**Проблема:** Все 3 фоновых цикла использовали единственный `self.limiter = AsyncLimiter(max_rate=10, time_period=60)` — 10 запросов/мин на всех. Это создавало конкуренцию между мониторингом (частые запросы), discovery (массовые запросы) и healthcheck (низкая частота).

**Решение:**

- **`api/zdrav_client.py:25-37`** — Четыре лимитера:
  - `limiter_monitor` (10/мин) — мониторинг слотов
  - `limiter_discovery` (5/мин) — discovery врачей
  - `limiter_healthcheck` (2/мин) — healthcheck
  - `limiter` (10/мин) — пользовательские запросы (хендлеры)

- **`api/zdrav_client.py:73-248`** — Во все 5 методов API добавлен опциональный параметр `limiter`. Дефолт: `self.limiter`. Вызывающий код передаёт свой.

- **`services/monitor.py:133`** — `api.check_slots(...)` → `api.check_slots(..., limiter=api.limiter_monitor)`
- **`services/doctor_discovery.py:14-28`** — `fetch_specialties` пробрасывает `limiter` в `fetch_speciality_list`
- **`services/doctor_discovery.py:94-98`** — `api.fetch_all_doctors(..., limiter=api.limiter_discovery)`

### R5 — Защита глобального `metrics` от гонок

**Проблема:** Глобальный `metrics = HealthMetrics()` (строка 92) мутируется из трёх корутин (healthcheck_loop, monitor_loop, main), без блокировок. При конкурентном доступе возможны потерянные инкременты и разорванные чтения.

**Решение:**

- **`services/healthcheck.py:93`** — Добавлен `_metrics_lock = asyncio.Lock()`
- **`services/healthcheck.py:96-106`** — `_safe_increment(attr, delta=1)` и `_safe_set(attr, value)` — атомарные хелперы под локом
- **`services/healthcheck.py:113-161`** — Все мутации `metrics.*` в `healthcheck_loop` заменены на `_safe_increment` / `_safe_set`
- **`services/healthcheck.py:165-167`** — Чтение `uptime_str()` и `api_health_str()` под локом (атомарный снапшот)
- **`services/monitor.py:84-87`** — `metrics.monitor_loop_alive = True` → `await _safe_set("monitor_loop_alive", True)`
- **`main.py:18,107`** — `metrics.discovery_tasks_alive += 1` → `await _safe_set("discovery_tasks_alive", ...)` через импорт `_safe_set`

### R4 — Healthcheck проверять несколько клиник

**Проблема:** `healthcheck_loop` проверял только `DEFAULT_CLINIC_ID` (строка 114-116), игнорируя остальные активные клиники.

**Решение:**

- **`services/healthcheck.py:127-131`** — Запрос `get_active_clinic_ids()` из БД. Фоллбэк на `DEFAULT_CLINIC_ID` если таблица пуста
- **`services/healthcheck.py:134-156`** — Цикл по всем clinic_ids: для каждой определяется `patient_id` (adult/child по типу клиники), запрос через `api.limiter_healthcheck`
- **`services/healthcheck.py:20`** — Импорт `Database` для доступа к `db._db`
- **`services/healthcheck.py:122-124`** — Кэш `_patient_for_clinic` для избежания повторных запросов к БД
- **`services/healthcheck.py:172`** — В лог добавлено `Clinics checked: {len(clinic_ids)}`

### Тесты

- **`tests/test_doctor_discovery.py:65`** — `assert_called_once_with` обновлён: добавлен `limiter=None`

**Результат:** 116/116 passed за 16.47 сек.

## 2026-05-11 (D2 — ручные миграции)

### D2 — Ручные миграции (migrations.py + schema_version)

**Проблема:** Схема БД задавалась через `CREATE TABLE IF NOT EXISTS` в `_create_tables()`. Ad-hoc миграция колонок — `_migrate_clinics_add_columns()` с `ALTER TABLE` в try/except. Таблица `schema_version` существовала, но не использовалась. Нет версионирования, нет истории изменений схемы.

**Решение:**

- **`database/migrations.py:1-95`** — Новый файл с упорядоченным списком `MIGRATIONS`. `migrate_v1_initial_schema` — создание всех таблиц (initial), `migrate_v2_clinics_columns` — `ALTER TABLE clinics ADD COLUMN` для `type`, `is_active`, `city`, `discovery_patient_adult`, `discovery_patient_child`
- **`database/database.py:178-210`** — `_create_tables()` теперь создаёт только `schema_version`. `_run_migrations()` читает текущую версию из БД, применяет миграции с номером > текущего, обновляет `schema_version`
- **`database/database.py:147`** — `_run_migrations()` вызывается в `connect()` после `_create_tables()`
- **`database/database.py:237-254`** — Метод `_migrate_clinics_add_columns()` удалён (логика перенесена в `migrate_v2_clinics_columns`)

**Результат:** 116/116 passed за 16.35 сек.

## 2026-05-11 (T2)

### T2 — Тесты для `services/monitor.py` (весь цикл) ✅

- Создан [`tests/test_monitor_full.py`](../tests/test_monitor_full.py:1) — 18 тестов (4 для `_send_notification`, 14 для `monitor_loop`)
- Мок-стратегия: `monkeypatch` для `asyncio.sleep` (CancelledError для выхода из бесконечного цикла), `swap_cache_key`, `_safe_set` (healthcheck), `_send_notification`
- `TestSendNotification`: отправка нового сообщения, удаление предыдущего + новое, устойчивость к ошибкам удаления и отправки
- `TestMonitorLoop`: slots appeared/disappeared/no change, first discovery, empty-slots protection (3 consecutive), API errors, CancelledError, multiple doctors, legacy string doctor_info, patient alias, generic exception, new slots marked
- Исправлено: monkeypatch-таргет `_safe_set` → `services.healthcheck._safe_set` (lazy import внутри monitor_loop)
- Исправлено: `monitor_loop` ловит `CancelledError` внутри через `break` (не пробрасывает наружу)
- Исправлено: `sleep_raises_on_call` для тестов с empty-slots protection (нужно 6 sleep-ов: per-doc×3 + jitter×3)

**Результат:** 134/134 passed за 17.08 сек (все тесты проекта).

## 2026-05-11 (B5 + F4)

### B5 — Вынос `_safe_set` import наверх модуля ✅

- [`services/monitor.py`](../src/services/monitor.py:8) — `from services.healthcheck import _safe_set` перенесён из тела `monitor_loop()` в top-level imports
- Причина «циклический импорт» оказалась ошибочной: `healthcheck.py` не импортирует `monitor.py`
- [`tests/test_monitor_full.py`](../tests/test_monitor_full.py:204) — monkeypatch target исправлен с `services.healthcheck._safe_set` → `services.monitor._safe_set`
- **Результат:** 134/134 passed

### F4 — Pre-commit hooks ✅

- Создан [`.pre-commit-config.yaml`](../.pre-commit-config.yaml:1) — 10 хуков (все `Passed`):
  - `pre-commit-hooks` (trailing-whitespace, end-of-file-fixer, check-yaml, check-added-large-files, debug-statements, detect-private-key, mixed-line-ending)
  - `ruff check` (линтер, `--fix --exit-non-zero-on-fix`)
  - `ruff format` (форматтер, `--check`)
  - `mypy` (type checker, `--ignore-missing-imports --check-untyped-defs --explicit-package-bases`)
- [`requirements.txt`](../requirements.txt:20) — добавлены `pre-commit>=4.0`, `ruff>=0.14`, `mypy>=1.18` (Dev / Testing)
- Установлен `pre-commit-hooks` пакет (через pip, SOCKS исправлен)
- `.exe` wrappers скопированы из `d:\.venv` в `z:\.venv\Scripts` (venv создавался на d:)
- Конфиг использует `repo: local` + `language: system` с абсолютными путями (устойчив к SOCKS proxy)

### SOCKS proxy investigation (pip fix)

- **Root cause:** В Windows Registry установлен `ProxyServer=socks=127.0.0.1:10808` (Clash/V2Ray для Telegram API из РФ)
- pip обнаруживает SOCKS proxy → пытается использовать `SOCKSProxyManager` → требует `PySocks`
- `PySocks` не установлен → pip не может соединиться → не может установить пакеты (chicken-and-egg)
- **Fix:** Скачан `PySocks-1.7.1-py3-none-any.whl` через `Invoke-WebRequest` (минуя pip), установлен локально
- Подтверждено: `pip install --dry-run pre-commit` работает через SOCKS

### Попутные исправления кода

- [`keyboards/inline.py`](../src/keyboards/inline.py:240) — `except:` → `except (ValueError, TypeError):` (E722 bare except)
- [`handlers/common.py`](../src/handlers/common.py:498) — `"\n".join(slots)` → `"\n".join(slots) if slots else ...` (None-safety)
- [`services/monitor.py`](../src/services/monitor.py:89) — `empty_counts = {}` → `empty_counts: dict[str, int] = {}` (type annotation)
- [`config.py`](../src/config.py:2) — добавлены `Any, Callable` в imports; mapping аннотирован типом
- [`handlers/common.py`](../src/handlers/common.py:213,439,576) — удалены 3 unused variables (F841)
- [`tests/test_doctor_discovery.py`](../tests/test_doctor_discovery.py:171) — удалён unused `api` (F841)
- ruff format исправил 7 файлов, mixed-line-ending — 54 файла

<!-- markdownlint-disable-next-line MD024 -->

### Изменённые файлы

| Файл                                                              | Действие                                            |
| ----------------------------------------------------------------- | --------------------------------------------------- |
| [`services/monitor.py`](../src/services/monitor.py:8)             | `_safe_set` import наверх; `empty_counts` аннотация |
| [`tests/test_monitor_full.py`](../tests/test_monitor_full.py:204) | monkeypatch target исправлен                        |
| [`.pre-commit-config.yaml`](../.pre-commit-config.yaml:1)         | Создан (local hooks, 10 хуков)                      |
| [`requirements.txt`](../requirements.txt:20)                      | Добавлены pre-commit, ruff, mypy                    |
| [`keyboards/inline.py`](../src/keyboards/inline.py:240)           | bare except → конкретные типы                       |
| [`handlers/common.py`](../src/handlers/common.py:213)             | unused variables удалены; None-safety               |
| [`config.py`](../src/config.py:2)                                 | typing imports; mapping аннотация                   |
| [`docs/AGENT_TASKS.md`](AGENT_TASKS.md:1)                         | Удалены B5, F4                                      |

**Результат:** 134/134 passed, 10/10 pre-commit hooks passed

## 2026-05-12 (fix: ClinicListResponse IdLPU int→str coercion)

### Анализ ошибок в error.log 🔍

- В [`logs/error.log`](../logs/error.log:3) обнаружена ошибка: `69 validation errors for ClinicListResponse`
- **Root cause:** API `zdrav.lenreg.ru/api/clinic_list/` возвращает `IdLPU` как целые числа (int), а Pydantic-модель [`ClinicItem`](../src/api/models.py:136) объявляла поле как `str`
- **Последствия:** `fetch_clinic_list()` падал с исключением → `sync_clinic_names()` получал пустой список → названия клиник не синхронизировались в БД. Discovery-циклы всё равно запускались через fallback-список clinic IDs.

### Исправление ✅

- В [`api/models.py`](../src/api/models.py:13) добавлена helper-функция `_coerce_str(v) → str` с `BeforeValidator` для приведения int/None к строке
- Поле [`ClinicItem.IdLPU`](../src/api/models.py:136) изменено на `Annotated[str, BeforeValidator(_coerce_str)]`
- Потребитель в [`services/doctor_discovery.py`](../src/services/doctor_discovery.py:145) уже делает `str(raw_id)` — совместимость сохранена

<!-- markdownlint-disable-next-line MD024 -->

### Изменённые файлы

| Файл                                       | Действие                                                                       |
| ------------------------------------------ | ------------------------------------------------------------------------------ |
| [`api/models.py`](../src/api/models.py:13) | Добавлены `Annotated`, `BeforeValidator`, `_coerce_str`; `IdLPU` с валидатором |

**Результат:** 38/38 tests passed (test_doctor_discovery.py + test_zdrav_client.py)

---

## 2026-05-12 (Pydantic + HTTP fix)

### Анализ лога ошибок ✅

Прочитан [`logs/error.log`](../logs/error.log) (7074 строки, 2026-05-12 00:18–11:41). Выявлено **1425 ERROR**, **234 WARNING**:

| #   | Категория                                            | Кол-во    | Суть                                                         |
| --- | ---------------------------------------------------- | --------- | ------------------------------------------------------------ |
| 1   | Pydantic `SpecialityListResponse` validation         | ~453      | `NameSpesiality`, `FerIdSpesiality`, `IdSpesiality` = `None` |
| 2   | ProxyConnectionError                                 | ~232      | Прокси 192.168.31.47:10808 периодически отваливался          |
| 3   | `fetch_all_doctors` + `fetch_speciality_list` пустые | ~584      | Ошибка без текста после двоеточия                            |
| 4   | TelegramNetworkError / ServerDisconnectedError       | несколько | Сетевые разрывы WinError 64                                  |

### Исправление Pydantic-валидации ✅

**Причина:** API `zdrav.lenreg.ru` иногда возвращает `null` в строковых полях `SpecialityItem`. Pydantic в режиме `model_validate` не применяет дефолт `""` к ключу со значением `None`.

**Решение:** применён `Annotated[str, BeforeValidator(_coerce_str)]`:

- [`SpecialityItem`](../src/api/models.py:65): `NameSpesiality`, `FerIdSpesiality`, `IdSpesiality`
- [`DoctorItem`](../src/api/models.py:89): `Name`, `IdDoc`

### Добавление HTTP-заголовков ✅

В [`_get_headers()`](../src/api/zdrav_client.py:46) добавлены:

- `X-CSRFToken: NOTPROVIDED`
- `Cookie: csrftoken=NOTPROVIDED`
- `Origin: https://zdrav.lenreg.ru`

<!-- markdownlint-disable-next-line MD024 -->

### Изменённые файлы

| Файл                                                   | Действие                                                           |
| ------------------------------------------------------ | ------------------------------------------------------------------ |
| [`api/models.py`](../src/api/models.py:62)             | `SpecialityItem` строковые поля → `BeforeValidator(_coerce_str)`   |
| [`api/models.py`](../src/api/models.py:85)             | `DoctorItem` поля `Name`, `IdDoc` → `BeforeValidator(_coerce_str)` |
| [`api/zdrav_client.py`](../src/api/zdrav_client.py:46) | `_get_headers()`: +`X-CSRFToken`, `Cookie`, `Origin`               |

### Очистка мусорных лог-файлов ✅

Удалены артефакты, не используемые проектом:

- `logs/_error_lines.txt` — временный результат grep из этой же сессии
- `logs/stdout.log` — артефакт ручного запуска (`python main.py > logs/stdout.log`)
  Проект использует только [`FileHandler("logs/error.log")`](../src/main.py:32).

| Файл                    | Действие |
| ----------------------- | -------- |
| `logs/_error_lines.txt` | Удалён   |
| `logs/stdout.log`       | Удалён   |

**Результат:** 15/15 tests passed (test_zdrav_client.py)

---

## 2026-05-12 (Архитектурный рефакторинг: src/ директория)

### Миграция исходного кода в src/ ✅

**Задача:** Устранение плоской иерархии в корне проекта — перенос всех модулей исходного кода в выделенную директорию `src/`, рефакторинг всех импортов на абсолютные `src.xxx`, генерация [`ARCHITECTURE.md`](../ARCHITECTURE.md:1).

**Изменённые файлы:**

| Файл                                                                         | Действие                                                                                                                              |
| ---------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| [`src/`](../src/__init__.py:1)                                               | Создана директория с `__init__.py` и подпакетами `api/`, `database/`, `handlers/`, `keyboards/`, `middleware/`, `services/`, `utils/` |
| [`src/config.py`](../src/config.py:1)                                        | Перенесён из `config.py`                                                                                                              |
| [`src/main.py`](../src/main.py:1)                                            | Перенесён из `main.py`, все импорты → `src.xxx`                                                                                       |
| [`src/api/zdrav_client.py`](../src/api/zdrav_client.py:1)                    | Импорты: `api.models` → `src.api.models`, `config` → `src.config`                                                                     |
| [`src/database/database.py`](../src/database/database.py:1)                  | Импорты: `database.migrations` → `src.database.migrations`, `utils.helpers` → `src.utils.helpers`, `config` → `src.config`            |
| [`src/database/manager.py`](../src/database/manager.py:1)                    | Импорт: `database.database` → `src.database.database`                                                                                 |
| [`src/database/doctor_manager.py`](../src/database/doctor_manager.py:1)      | Импорт: `database.database` → `src.database.database`                                                                                 |
| [`src/database/migrations.py`](../src/database/migrations.py:1)              | Импорт: `config` → `src.config`                                                                                                       |
| [`src/handlers/common.py`](../src/handlers/common.py:1)                      | Все импорты → `src.xxx` (api, config, database, keyboards, services, utils)                                                           |
| [`src/handlers/registration.py`](../src/handlers/registration.py:1)          | Все импорты → `src.xxx`                                                                                                               |
| [`src/keyboards/inline.py`](../src/keyboards/inline.py:1)                    | Импорт: `utils.helpers` → `src.utils.helpers`                                                                                         |
| [`src/middleware/ratelimit.py`](../src/middleware/ratelimit.py:1)            | Импорт: `config` → `src.config`                                                                                                       |
| [`src/services/cleanup.py`](../src/services/cleanup.py:1)                    | Все импорты → `src.xxx`                                                                                                               |
| [`src/services/doctor_discovery.py`](../src/services/doctor_discovery.py:1)  | Все импорты → `src.xxx`                                                                                                               |
| [`src/services/error_notifier.py`](../src/services/error_notifier.py:1)      | Импорт: `config` → `src.config`                                                                                                       |
| [`src/services/healthcheck.py`](../src/services/healthcheck.py:1)            | Все импорты → `src.xxx`                                                                                                               |
| [`src/services/monitor.py`](../src/services/monitor.py:1)                    | Все импорты → `src.xxx`                                                                                                               |
| [`src/utils/cache.py`](../src/utils/cache.py:1)                              | Импорт: `config` → `src.config`                                                                                                       |
| [`tests/conftest.py`](../tests/conftest.py:11)                               | Импорты → `src.xxx`, monkeypatch path → `src.utils.cache.settings.CACHE_PATH`                                                         |
| [`tests/test_monitor_full.py`](../tests/test_monitor_full.py:9)              | Импорт: `services.monitor` → `src.services.monitor`                                                                                   |
| [`tests/test_doctor_discovery.py`](../tests/test_doctor_discovery.py:8)      | Импорт: `services.doctor_discovery` → `src.services.doctor_discovery`                                                                 |
| [`tests/test_monitor_classify.py`](../tests/test_monitor_classify.py:5)      | Импорт: `services.monitor` → `src.services.monitor`                                                                                   |
| [`scripts/apply_city_heuristic.py`](../scripts/apply_city_heuristic.py:12)   | Импорты → `src.xxx`                                                                                                                   |
| [`scripts/apply_heuristic_types.py`](../scripts/apply_heuristic_types.py:12) | Импорты → `src.xxx`                                                                                                                   |
| [`pyproject.toml`](../pyproject.toml:1)                                      | Добавлен `[tool.ruff] src = ["src"]`                                                                                                  |
| [`pytest.ini`](../pytest.ini:1)                                              | Добавлен `pythonpath = .`                                                                                                             |
| [`pyrightconfig.json`](../pyrightconfig.json:1)                              | Добавлен `rootPath: "."`                                                                                                              |
| [`.pre-commit-config.yaml`](../.pre-commit-config.yaml:75)                   | mypy args: заменены 9× `-p` на `-p src -p scripts -p tests`                                                                           |
| [`ARCHITECTURE.md`](../ARCHITECTURE.md:1)                                    | Создан: дерево директорий, зоны ответственности, граф зависимостей, ключевые решения                                                  |
| [`.roo/rules/knowledge.md`](../.roo/rules/knowledge.md:1)                    | Добавлен приоритет чтения `ARCHITECTURE.md` при анализе структуры проекта                                                             |

**Удалены:** Старые корневые директории `api/`, `database/`, `handlers/`, `keyboards/`, `middleware/`, `services/`, `utils/`, файлы `config.py`, `main.py` (теперь в `src/`).

---

### Верификация рефакторинга ✅

**Дата:** 2026-05-12

**Задача:** Проверить работоспособность бота после миграции в `src/`.

**Результаты тестов:** **134 passed, 0 failed, 0 errors** (Python 3.14.4, pytest 9.0.3)

| Группа тестов                                                           | Кол-во | Результат     |
| ----------------------------------------------------------------------- | ------ | ------------- |
| [`tests/test_cache.py`](../tests/test_cache.py:1)                       | 7      | ✅ Все прошли |
| [`tests/test_database_manager.py`](../tests/test_database_manager.py:1) | 14     | ✅ Все прошли |
| [`tests/test_doctor_discovery.py`](../tests/test_doctor_discovery.py:1) | 15     | ✅ Все прошли |
| [`tests/test_doctor_manager.py`](../tests/test_doctor_manager.py:1)     | 11     | ✅ Все прошли |
| [`tests/test_keyboards.py`](../tests/test_keyboards.py:1)               | 39     | ✅ Все прошли |
| [`tests/test_monitor_classify.py`](../tests/test_monitor_classify.py:1) | 12     | ✅ Все прошли |
| [`tests/test_monitor_full.py`](../tests/test_monitor_full.py:1)         | 21     | ✅ Все прошли |
| [`tests/test_zdrav_client.py`](../tests/test_zdrav_client.py:1)         | 15     | ✅ Все прошли |

**Исправленные проблемы после первого запуска тестов (63 failed → 0 failed):**

1. [`tests/test_cache.py`](../tests/test_cache.py:13) — 7 inline-импортов `from utils.cache import` → `from src.utils.cache import`
2. [`tests/test_database_manager.py`](../tests/test_database_manager.py:11) — 2 inline-импорта `from database.xxx import` → `from src.database.xxx import`
3. [`tests/test_keyboards.py`](../tests/test_keyboards.py:30) — 39 inline-импортов `from keyboards.inline import` → `from src.keyboards.inline import`
4. [`tests/test_monitor_classify.py`](../tests/test_monitor_classify.py:74) — 2 inline-импорта `import config` → `import src.config as config`
5. [`tests/test_monitor_full.py`](../tests/test_monitor_full.py:197) — 6 monkeypatch-путей `"services.monitor.xxx"` → `"src.services.monitor.xxx"` и `"services.healthcheck._safe_set"` → `"src.services.healthcheck._safe_set"`
6. [`tests/test_zdrav_client.py`](../tests/test_zdrav_client.py:16) — 1 inline-импорт `from api.zdrav_client import` → `from src.api.zdrav_client import`
7. [`tests/test_doctor_manager.py`](../tests/test_doctor_manager.py:75) — 1 inline-импорт `from database.doctor_manager import` → `from src.database.doctor_manager import`

**Изменённые файлы (верификация):**

| Файл                                                                     | Изменения                                        |
| ------------------------------------------------------------------------ | ------------------------------------------------ |
| [`tests/test_cache.py`](../tests/test_cache.py:13)                       | 7 inline-импортов → `src.utils.cache`            |
| [`tests/test_database_manager.py`](../tests/test_database_manager.py:11) | 2 inline-импорта → `src.database.xxx`            |
| [`tests/test_keyboards.py`](../tests/test_keyboards.py:30)               | 39 inline-импортов → `src.keyboards.inline`      |
| [`tests/test_monitor_classify.py`](../tests/test_monitor_classify.py:74) | 2 inline-импорта → `import src.config as config` |
| [`tests/test_monitor_full.py`](../tests/test_monitor_full.py:197)        | 6 monkeypatch-путей → `src.services.xxx`         |
| [`tests/test_zdrav_client.py`](../tests/test_zdrav_client.py:16)         | 1 inline-импорт → `src.api.zdrav_client`         |
| [`tests/test_doctor_manager.py`](../tests/test_doctor_manager.py:75)     | 1 inline-импорт → `src.database.doctor_manager`  |

### Pre-commit хуки и автофиксы ✅

- `pre-commit run --all-files`: `mixed-line-ending` перевёл 55 файлов CRLF→LF, `ruff` убрал лишнюю пустую строку в [`tests/conftest.py`](../tests/conftest.py:8)
- Pre-existing failures (не исправлялись): `ruff-lint` (~30 E501/ASYNC240/ASYNC251), `mypy` (4 type-annotation)
- Автофиксы закоммичены в `main` как `3e0546a`, запушены в `origin/main`

<!-- markdownlint-disable-next-line MD024 -->

### Изменённые файлы

| Файл                                          | Изменение                                  |
| --------------------------------------------- | ------------------------------------------ |
| [`tests/conftest.py`](../tests/conftest.py:8) | Убрана лишняя пустая строка (ruff)         |
| 54 файла                                      | CRLF → LF line endings (mixed-line-ending) |

---

## 2026-05-12 (систематизация документации и правил)

### Систематизация документации и правил ✅

**Задача:** Провести аудит и логическую систематизацию директорий `docs/` и `.roo/`.

**Изменённые файлы:**

| Файл                                                                    | Действие                                          |
| ----------------------------------------------------------------------- | ------------------------------------------------- |
| [`.roo/rules/system_standards.md`](../.roo/rules/system_standards.md:1) | Создан — CRITICAL стандарты Python + Markdown     |
| [`.roo/rules/coding.md`](../.roo/rules/coding.md:1)                     | Создан — стандарты кодирования                    |
| [`docs/GEMINI.md`](../docs/GEMINI.md:1)                                 | Обновлён — agent-agnostic bridge                  |
| [`docs/agents/AGENT_TASKS.md`](AGENT_TASKS.md:1)                        | Перенесён из `docs/`                              |
| [`docs/agents/CODE_REVIEW.md`](CODE_REVIEW.md:1)                        | Перенесён из `docs/`                              |
| [`docs/agents/formatting_experiments.md`](formatting_experiments.md:1)  | Конвертирован из `варианты оформления.txt`        |
| [`docs/knowledge/*.md`](../docs/knowledge/_INDEX.md:1)                  | Реформатированы в единый шаблон                   |
| [`.roo/rules/logging.md`](../.roo/rules/logging.md:1)                   | Обновлён: пути `docs/agents/`, SESSION_ARCHIVE.md |
| [`.roo/rules/ignore.md`](../.roo/rules/ignore.md:1)                     | Обновлён: актуальные пути игнорируемых файлов     |
| [`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md:1)                     | Обновлено дерево директорий                       |
| [`README.md`](../README.md:1)                                           | Обновлён                                          |
| [`docs/PROJECT_TREE.md`](../docs/PROJECT_TREE.md:1)                     | Удалён (устарел, заменён на ARCHITECTURE.md)      |
| [`docs/QWEN.md`](../docs/QWEN.md:1)                                     | Удалён (пустой)                                   |
| [`docs/варианты оформления.txt`](../docs/варианты оформления.txt:1)     | Удалён (конвертирован в .md)                      |

### Разделение SESSION_LOG: активный лог + архив ✅

**Задача:** Восстановить полный журнал разработки (1051 строка, 2026-05-01—2026-05-12), разделив на два файла.

**Изменённые файлы:**

| Файл                                                     | Действие                                             |
| -------------------------------------------------------- | ---------------------------------------------------- |
| [`docs/agents/SESSION_ARCHIVE.md`](SESSION_ARCHIVE.md:1) | Создан — полная хронология из git (ece319e)          |
| [`docs/agents/SESSION_LOG.md`](SESSION_LOG.md:1)         | Очищен до шаблона последней сессии                   |
| [`.roo/rules/logging.md`](../.roo/rules/logging.md:1)    | Добавлен шаг переноса в SESSION_ARCHIVE.md           |
| [`.roo/rules/ignore.md`](../.roo/rules/ignore.md:1)      | `SESSION_ARCHIVE.md` добавлен в условно-игнорируемые |

**Результаты тестов:** Не запускались

---

## 2026-05-12 (markdownlint workflow + commit/push)

### Добавление markdownlint в пре-комплишн workflow ✅

**Задача:** Добавить обязательную проверку `npx markdownlint` перед `attempt_completion` для всех `.md` файлов и исправить 41 markdownlint violation в [`docs/agents/SESSION_ARCHIVE.md`](SESSION_ARCHIVE.md:1).

**Исправленные ошибки в SESSION_ARCHIVE.md:**

| Правило | Суть                               | Кол-во | Метод исправления                                              |
| ------- | ---------------------------------- | ------ | -------------------------------------------------------------- |
| MD058   | Таблицы без пустых строк           | 5      | Пустые строки перед таблицами                                  |
| MD060   | Стиль разделителей таблиц          | ~15    | Заменено на `\| --- \|` (spaces вокруг разделителей)           |
| MD038   | Пробел внутри инлайн-кода          | 1      | Убран trailing space в коде `` `...fetch_speciality_list):` `` |
| MD024   | Дубликат H2 `2026-05-11` (5)       | 5      | Уникальные контекстные суффиксы                                |
| MD024   | Дубликат H3 `Изменённые файлы` (8) | 8      | `markdownlint-disable-next-line MD024` перед повторными H3     |

**Изменённые файлы:**

| Файл                                                     | Действие                                                               |
| -------------------------------------------------------- | ---------------------------------------------------------------------- |
| [`docs/agents/SESSION_ARCHIVE.md`](SESSION_ARCHIVE.md:1) | Исправлены MD038, MD058, MD060, MD024                                  |
| `.roo/rules/system_standards.md`                         | Добавлена команда `markdownlint` в секцию Валидация                    |
| `.roo/rules/logging.md`                                  | Добавлены шаги 4 (markdownlint) и 5 (prettier) в пре-комплишн workflow |
| `.markdownlint.json`                                     | Создан конфиг (MD013, MD041, MD060 отключены)                          |
| `.gitignore`                                             | Добавлены `node_modules/`, `package-lock.json`, `.vscode/`             |
| `package.json`                                           | Инициализирован npm, установлен `markdownlint-cli`                     |

### Git commit + push ✅

- Commit: `c2dad57` — 26 files changed, 953 insertions, 737 deletions
- Push: `main -> main` on `github.com/acidmsg/lenreg_ticket_bot.git`

**Результаты тестов:** Не запускались

---

## 2026-05-13 (немедленный healthcheck — устранение 5-минутной тишины)

### Проблема

[`healthcheck_loop()`](src/services/healthcheck.py:130) вызывал `asyncio.sleep(CHECK_INTERVAL)` в **начале** цикла — первая проверка API происходила только через `CHECK_INTERVAL` (5 мин) после старта бота. Всё это время [`api_health_str()`](src/services/healthcheck.py:71) возвращал `❓ Нет данных`, а команда `/status` показывала бесполезный статус.

### Решение

| Изменение                         | Строки                                 | Описание                                                     |
| --------------------------------- | -------------------------------------- | ------------------------------------------------------------ |
| Перенос `sleep` в конец цикла     | [202](src/services/healthcheck.py:202) | Первая проверка API — немедленно при старте, затем пауза     |
| Новый текст для нулевого счётчика | [73](src/services/healthcheck.py:73)   | `⏳ Первая проверка ещё не выполнена` вместо `❓ Нет данных` |

Теперь после старта бота healthcheck **сразу** проверяет API zdrav.lenreg.ru по всем активным клиникам, и `/status` показывает актуальный статус без задержки.

**Изменённые файлы:**

| Файл                                                            | Действие                                                                         |
| --------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| [`src/services/healthcheck.py`](src/services/healthcheck.py:71) | `api_health_str()` — новый текст; `healthcheck_loop()` — sleep перенесён в конец |

**Результаты линтинга:** ruff — All checks passed. mypy — Success: no issues found.

---

## 2026-05-13 (middleware expansion + healthcheck race-condition fix)

### Middleware/filter (4 новых)

| Middleware / Filter         | Файл                                                                      | Назначение                                                           |
| --------------------------- | ------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| `IsAdmin` (filter)          | [`src/filters/admin.py`](src/filters/admin.py:13)                         | Проверка `ADMIN_IDS` — вынесена из `common.py`                       |
| `ErrorBoundaryMiddleware`   | [`src/middleware/error_boundary.py`](src/middleware/error_boundary.py:16) | Глобальный try/except для TelegramBadRequest/NotFound/ForbiddenError |
| `UserDataPreloadMiddleware` | [`src/middleware/userdata.py`](src/middleware/userdata.py:14)             | Preload `user_data` в `data["user_data"]`                            |
| `ActivityLogMiddleware`     | [`src/middleware/activity.py`](src/middleware/activity.py:13)             | Сквозное логирование всех событий (DEBUG)                            |

### Исправление healthcheck — race condition + переработка метрик

**Проблема 1:** Кумулятивные счётчики (`api_checks_total`, `api_success_total`, `api_errors_total`) инкрементировались раздельными вызовами `_safe_increment()`, а `format_status_report()` читал их без `_metrics_lock` — получался несогласованный снапшот (`0 ошибок из 3, но 67%`).

**Проблема 2:** Кумулятивные счётчики за всё время аптайма неинформативны — не отвечают на вопрос «API работает сейчас?».

**Решение:** снапшот последнего цикла healthcheck (`last_api_clinics_ok`/`_err`/`_total`) + `format_status_report()` → `async` с чтением под `_metrics_lock`.

### Исправление healthcheck — зависание первого цикла

**Проблема 3:** [`limiter_healthcheck`](src/api/zdrav_client.py:30) имел `max_rate=2/60s` (~30с между запросами). При 6+ активных клиниках первый цикл занимал >3 минут, при 10+ >5 минут. Сообщение «⏳ Выполняется первый цикл проверки...» не менялось 7+ минут.

**Решение:** [`max_rate=2 → 30`](src/api/zdrav_client.py:30) (1 запрос в 2 секунды). Цикл и так ограничен `CHECK_INTERVAL` (300с), агрессивный лимитер избыточен.

### Изменённые файлы

| Файл                                                                     | Действие                                                                         |
| ------------------------------------------------------------------------ | -------------------------------------------------------------------------------- |
| [`src/filters/admin.py`](src/filters/admin.py:1)                         | Новый файл — `IsAdmin` filter                                                    |
| [`src/filters/__init__.py`](src/filters/__init__.py:1)                   | Новый файл — экспорт `IsAdmin`                                                   |
| [`src/middleware/activity.py`](src/middleware/activity.py:1)             | Новый файл — `ActivityLogMiddleware`                                             |
| [`src/middleware/error_boundary.py`](src/middleware/error_boundary.py:1) | Новый файл — `ErrorBoundaryMiddleware`                                           |
| [`src/middleware/userdata.py`](src/middleware/userdata.py:1)             | Новый файл — `UserDataPreloadMiddleware`                                         |
| [`src/middleware/__init__.py`](src/middleware/__init__.py:1)             | Экспорт всех middleware                                                          |
| [`src/main.py:17-20`](src/main.py:17)                                    | Импорт 4 middleware; регистрация в `dp.update.outer_middleware` (строки 302-310) |
| [`src/handlers/common.py:8`](src/handlers/common.py:8)                   | Импорт `IsAdmin`; `cmd_status` → `await format_status_report(db)`                |
| [`src/services/healthcheck.py:34`](src/services/healthcheck.py:34)       | `last_api_check_time` → `float = 0.0`; новые поля снапшота цикла                 |
| [`src/services/healthcheck.py:76`](src/services/healthcheck.py:76)       | `api_health_str()` — перикловый снапшот вместо кумулятивных %                    |
| [`src/services/healthcheck.py:139`](src/services/healthcheck.py:139)     | `healthcheck_loop()` — локальные `cycle_ok`/`cycle_err`, атомарный снапшот       |
| [`src/services/healthcheck.py:228`](src/services/healthcheck.py:228)     | `format_status_report()` → `async`, чтение метрик под `_metrics_lock`            |
| [`src/api/zdrav_client.py:30`](src/api/zdrav_client.py:30)               | `limiter_healthcheck` `max_rate` 2→30 req/min — устранение зависания 1-го цикла  |

### Упрощение healthcheck — 1 запрос вместо цикла по клиникам

**Причина:** Все клиники ходят через один API `zdrav.lenreg.ru` — опрос каждой избыточен. Достаточно одного запроса.

**Изменения в [`HealthMetrics`](src/services/healthcheck.py:23):**
`last_api_clinics_total`/`_ok`/`_err` заменены на `last_api_ok: bool`.

**Изменения в [`api_health_str()`](src/services/healthcheck.py:76):** `✅ Доступен` / `❌ Недоступен` вместо процентов и количества клиник.

**Изменения в [`healthcheck_loop()`](src/services/healthcheck.py:119):** цикл `for clinic_id in clinic_ids` убран; один `fetch_speciality_list(DEFAULT_CLINIC_ID, взрослый пациент)` за итерацию.

**Результаты линтинга:** ruff — All checks passed. markdownlint — 0 errors.

---

## 2026-05-13 (правило языка общения)

### Задача

Добавлено строгое правило `.roo/rules/language.md`: всё общение с пользователем — на русском языке, включая размышления (thinking).

### Изменённые файлы

| Файл                                                         | Действие                           |
| ------------------------------------------------------------ | ---------------------------------- |
| [`.roo/rules/language.md`](.roo/rules/language.md:1)         | Новый файл — правило языка общения |
| [`.roo/rules/restrictions.md`](.roo/rules/restrictions.md:5) | Добавлена ссылка на `language.md`  |

---

## 2026-05-13 (исправление конфликтов Pylance/Pyright)

### Задача

Устранены предупреждения Pylance о конфликте настроек между `.vscode/settings.json` и `pyrightconfig.json`/`pyproject.toml`.

### Изменённые файлы

| Файл                                                | Действие                                                                     |
| --------------------------------------------------- | ---------------------------------------------------------------------------- |
| [`.vscode/settings.json`](.vscode/settings.json:14) | Удалены `python.analysis.extraPaths` и `python.analysis.typeCheckingMode`    |
| [`pyrightconfig.json`](pyrightconfig.json:8)        | Добавлены дефолтные исключения: `**/node_modules`, `**/__pycache__`, `**/.*` |

---

## 2026-05-13 (внедрение Poetry + Makefile + tasks.ps1)

### Задача

Внедрены инструменты управления проектом: Poetry (зависимости), Makefile и tasks.ps1 (таск-раннеры), обновлён pyproject.toml (единая конфигурация всех инструментов).

### Выполненные задачи

- Установлен Poetry 2.4.1 (`python -m poetry`)
- Перенесены зависимости из [`requirements.txt`](requirements.txt) в [`pyproject.toml`](pyproject.toml:28) (секции `dependencies` + `dev`)
- Сгенерирован [`poetry.lock`](poetry.lock)
- Создан [`Makefile`](Makefile:1) (команды: install, lint, format, test, run, clean, lock, check)
- Создан [`tasks.ps1`](tasks.ps1:1) (PowerShell таск-раннер для Windows)
- Обновлён [`.pre-commit-config.yaml`](.pre-commit-config.yaml:1) (poetry-совместимые entry-пути)
- Обновлён [`.gitignore`](.gitignore:12) (добавлен `qdrant_storage/`)
- Исправлен синтаксис `except X, Y:` → `except (X, Y):` в 7 местах (Python 3.11+)
- Исправлены аннотации типов в [`src/database/manager.py`](src/database/manager.py:18) и [`src/services/doctor_discovery.py`](src/services/doctor_discovery.py:37)
- Исправлен формат license в [`pyproject.toml`](pyproject.toml:9)

### Результаты проверок

| Инструмент   | Результат                               |
| ------------ | --------------------------------------- |
| Ruff (lint)  | All checks passed                       |
| Mypy         | 27 source files, 0 errors               |
| Markdownlint | 0 errors                                |
| Pytest       | 133 passed, 1 failed → fix → 134 passed |

### Изменённые файлы

| Файл                                                                      | Действие                                       |
| ------------------------------------------------------------------------- | ---------------------------------------------- |
| [`pyproject.toml`](pyproject.toml)                                        | Полная переработка (зависимости + tool-секции) |
| [`Makefile`](Makefile)                                                    | Создан                                         |
| [`tasks.ps1`](tasks.ps1)                                                  | Создан                                         |
| [`poetry.lock`](poetry.lock)                                              | Сгенерирован                                   |
| [`.pre-commit-config.yaml`](.pre-commit-config.yaml)                      | Poetry-совместимые пути                        |
| [`.gitignore`](.gitignore)                                                | Добавлен `qdrant_storage/`                     |
| [`src/config.py`](src/config.py:138)                                      | `except (ValueError, TypeError)`               |
| [`src/handlers/common.py`](src/handlers/common.py:256)                    | `except (ValueError, IndexError)` ×3           |
| [`src/keyboards/inline.py`](src/keyboards/inline.py:241)                  | `except (ValueError, TypeError)`               |
| [`src/main.py`](src/main.py:65)                                           | `except (OSError, asyncio.TimeoutError)`       |
| [`src/utils/helpers.py`](src/utils/helpers.py:36)                         | `except (ValueError, TypeError)`               |
| [`src/database/manager.py`](src/database/manager.py:18)                   | Аннотация `Dict[str, Dict[str, Any]]`          |
| [`src/services/doctor_discovery.py`](src/services/doctor_discovery.py:37) | Аннотация `database: "Database"`               |

---

## 2026-05-14 (Этап 0: создание SSOT-спецификации openapi.yaml)

### Задача

Создан файл [`docs/openapi.yaml`](docs/openapi.yaml) — единственный источник истины (SSOT) для архитектуры данных, бизнес-логики и внешних интеграций согласно правилу [`.roo/rules/architecture.md`](.roo/rules/architecture.md:5).

### Выполненные задачи

- Проведён полный аудит проекта: изучены все модули `src/`, схемы БД, API-эндпоинты, knowledge-база
- Создан [`docs/openapi.yaml`](docs/openapi.yaml:1) — OpenAPI 3.0.0 (YAML, описания на русском)
- Задокументированы:
  - **Внешний API zdrav.lenreg.ru:** 5 эндпоинтов (`check_patient`, `speciality_list`, `doctor_list`, `appointment_list`, `clinic_list`)
  - **Telegram-бот:** команды `/start`, `/status`, FSM-сценарий регистрации
  - **Фоновые сервисы:** monitor_loop, discovery_loop, healthcheck_loop, cleanup_loop
  - **База данных (SQLite):** 6 таблиц (`user_patients`, `user_monitoring`, `user_last_messages`, `clinics`, `doctors`, `config`, `specialty_aliases`)
  - **Конфигурация:** все параметры из `src/config.py` + rate limiting
  - **Классификация изменений слотов:** логика уведомлений
- YAML-валидация пройдена (`python -c "import yaml; yaml.safe_load(...)"`)

### Изменённые файлы

| Файл                                     | Действие |
| ---------------------------------------- | -------- |
| [`docs/openapi.yaml`](docs/openapi.yaml) | Создан   |

---

## 2026-05-14 (Рефакторинг и универсализация системных правил .roo/rules/)

### Задача

Проведена глубокая реструктуризация свода правил в `.roo/rules/`: 9 разрозненных файлов объединены в 3 логических кластера. Все правила де-хардкожены — удалены ссылки на текущий проект, превращены в переиспользуемый стандарт для любого Python/aiogram проекта.

### Выполненные задачи

- Прочитаны и проанализированы все 9 исходных файлов `.roo/rules/`
- Создан [`.roo/rules/core.md`](.roo/rules/core.md:1) — базовые ограничения и идентичность агента (language + ignore + restrictions)
- Создан [`.roo/rules/workflow.md`](.roo/rules/workflow.md:1) — процессы и жизненный цикл (architecture + logging + knowledge)
- Создан [`.roo/rules/standards.md`](.roo/rules/standards.md:1) — технические стандарты Python/Markdown (coding + system_standards + env)
- Удалены старые 9 файлов: `architecture.md`, `coding.md`, `env.md`, `ignore.md`, `knowledge.md`, `language.md`, `logging.md`, `restrictions.md`, `system_standards.md`
- Верификация: поиск проектного хардкода (`lenreg`, `zdrav`, `DISCOVERY_PATIENT_ID`, `doctor_manager.py`) в новых файлах — 0 совпадений

### Изменённые файлы

| Файл                                                 | Действие      |
| ---------------------------------------------------- | ------------- |
| [`.roo/rules/core.md`](.roo/rules/core.md)           | Создан (из 3) |
| [`.roo/rules/workflow.md`](.roo/rules/workflow.md)   | Создан (из 3) |
| [`.roo/rules/standards.md`](.roo/rules/standards.md) | Создан (из 3) |
| `.roo/rules/*.md` (9 файлов)                         | Удалены       |

---

## 2026-05-14 (Внедрение Redis + правки Ruff + подавление Pylance)

### Задача

Полная замена файлового JSON-кэша и in-memory TTLCache на Redis: singleton-клиент, кэш мониторинга, spam-защита, sliding-window rate limiting, FSM-хранилище aiogram. Исправление ошибок Ruff E501. Подавление ложных ошибок Pylance для redis-py 7.x Protocol-класса.

### Выполненные задачи

- **Инфраструктура:** Добавлен Redis-сервис в [`docker-compose.yml`](docker-compose.yml:12), зависимость `redis>=5.2` в [`pyproject.toml`](pyproject.toml:38), `fakeredis[lua]` в dev-зависимости, `redis_data/` в [`.gitignore`](.gitignore:10)
- **Конфигурация:** Добавлен `REDIS_URL` в [`src/config.py`](src/config.py:31) и [`.env.example`](.env.example:14)
- **Redis-клиент:** Создан [`src/utils/redis.py`](src/utils/redis.py:1) — singleton `RedisClient` с asyncio-поддержкой (`aioredis`), пулом соединений (max 10), health-check, pipeline
- **Кэш мониторинга:** [`src/utils/cache.py`](src/utils/cache.py:1) переписан с файлового JSON → Redis GETSET (`swap_cache_key`) и SCAN+DEL (`delete_cache_keys_by_prefix`), spam-защита через SET NX EX (`is_spam`)
- **Обработчики:** В [`src/handlers/common.py`](src/handlers/common.py:21) замена `spam_cache` на `await is_spam()`
- **Rate limiting:** [`src/middleware/ratelimit.py`](src/middleware/ratelimit.py:1) переписан с in-memory dict+TTLCache → Redis Sorted Sets (sliding window через pipeline: ZREMRANGEBYSCORE+ZADD+ZCARD+EXPIRE)
- **FSM-хранилище:** В [`src/main.py`](src/main.py:8) `MemoryStorage()` заменён на `RedisStorage.from_url()`, добавлены `await RedisClient.get_instance()` при старте и `await RedisClient.shutdown()` при остановке
- **Документация:** Обновлён [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md:38) — дерево директорий, Mermaid-граф (нода `UTIL_REDIS`), ключевые решения (пункт 2)
- **Тесты:** Обновлён [`tests/conftest.py`](tests/conftest.py:76) — autouse-фикстура `fake_redis` с `fakeredis.aioredis.FakeRedis`, обновлён [`tests/test_cache.py`](tests/test_cache.py:1) — 15 тестов на Redis-операции (spam, swap, delete)
- **Правки Ruff E501:** Сокращены 3 строки-нарушителя в [`src/utils/redis.py`](src/utils/redis.py:40,71) и [`src/utils/cache.py`](src/utils/cache.py:38)
- **Подавление Pylance:** Файловое подавление `reportGeneralTypeIssues` и `reportAttributeAccessIssue` в [`src/utils/redis.py:8`](src/utils/redis.py:8) — redis-py 7.x использует Protocol для `redis.asyncio.Redis`, Pylance не умеет разрешать `Awaitable[X] | X` при `await` и не видит атрибут `client` на модуле

### Изменённые файлы

| Файл                                                         | Действие  |
| ------------------------------------------------------------ | --------- |
| [`docker-compose.yml`](docker-compose.yml)                   | Изменён   |
| [`pyproject.toml`](pyproject.toml)                           | Изменён   |
| [`.gitignore`](.gitignore)                                   | Изменён   |
| [`.env.example`](.env.example)                               | Изменён   |
| [`src/config.py`](src/config.py)                             | Изменён   |
| [`src/utils/redis.py`](src/utils/redis.py)                   | Создан    |
| [`src/utils/cache.py`](src/utils/cache.py)                   | Переписан |
| [`src/handlers/common.py`](src/handlers/common.py)           | Изменён   |
| [`src/middleware/ratelimit.py`](src/middleware/ratelimit.py) | Переписан |
| [`src/main.py`](src/main.py)                                 | Изменён   |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)               | Изменён   |
| [`tests/conftest.py`](tests/conftest.py)                     | Переписан |
| [`tests/test_cache.py`](tests/test_cache.py)                 | Переписан |

### Результаты тестов

```text
142 passed in 17.92s
```

### Результаты линтера

```text
ruff check src/ — All checks passed!
```

---

## 2026-05-14 (Внедрение регламента Topology Sync)

### Задача

Закрепление разделения зон ответственности между логической архитектурой (`openapi.yaml`) и физической топологией (`ARCHITECTURE.md`). Добавление правила обязательной синхронизации `ARCHITECTURE.md` при любых изменениях структуры проекта (Фаза 4: Architecture Sync).

### Выполненные задачи

- **ARCHITECTURE.md:** Добавлен блок-предупреждение сразу под H1 — документ описывает строго физическую структуру; SSOT для структур данных и бизнес-правил — [`docs/openapi.yaml`](docs/openapi.yaml) ([`docs/ARCHITECTURE.md:3`](docs/ARCHITECTURE.md:3))
- **workflow.md:** Добавлена Фаза 4 (Синхронизация топологии) в протокол Phased Update — обязательное обновление дерева директорий, Mermaid-графа и таблицы зон ответственности в `ARCHITECTURE.md` после изменений в `src/` ([`.roo/rules/workflow.md:37`](.roo/rules/workflow.md:37))
- **Логирование:** Текущая запись перенесена в архив, новая запись создана

### Изменённые файлы

| Файл                                                               | Действие  |
| ------------------------------------------------------------------ | --------- |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)                     | Изменён   |
| [`.roo/rules/workflow.md`](.roo/rules/workflow.md)                 | Изменён   |
| [`docs/agents/SESSION_LOG.md`](docs/agents/SESSION_LOG.md)         | Переписан |
| [`docs/agents/SESSION_ARCHIVE.md`](docs/agents/SESSION_ARCHIVE.md) | Изменён   |

---

## 2026-05-14 (Настройка CI/CD Local, протокол временных файлов, исправление импорта redis)

### Задача

Автоматизация полного цикла проверок (lint + format-check + test) через единую команду `check`. Внедрение протокола изоляции вывода во временные файлы и обязательной очистки (Zero-Trace). Исправление 2 ошибок импорта `redis` в тестах monitor.

### Выполненные задачи

- **Makefile:** Заменена цель `check` (была `poetry check`) на полный CI-цикл: ruff check + mypy + markdownlint + ruff format --check + prettier --check + pytest. Старая цель вынесена в `verify-pyproject` ([`Makefile:28`](Makefile:28))
- **tasks.ps1:** Аналогично Makefile — `check` теперь полный CI, `verify-pyproject` для poetry check ([`tasks.ps1:92`](tasks.ps1:92))
- **.gitignore:** Добавлены маски `.tmp_*` и `*.tmp` для временных файлов ([`.gitignore:33`](.gitignore:33))
- **core.md:** Добавлена таблица «Временные файлы (полностью)» с масками `.tmp_*` и `*.tmp` в список игнорируемых ([`.roo/rules/core.md:43`](.roo/rules/core.md:43))
- **workflow.md:** Добавлен раздел «Протокол выполнения проверок и работы с временными файлами» — правила изоляции вывода, чтения через `read_file` и обязательной очистки Zero-Trace ([`.roo/rules/workflow.md:56`](.roo/rules/workflow.md:56))
- **redis.py:** Ленивый импорт `redis.asyncio` — вынесен из уровня модуля в `_connect()`. Аннотации заменены на `Any` с `TYPE_CHECKING` ([`src/utils/redis.py:23`](src/utils/redis.py:23))
- **conftest.py:** Фикстура `fake_redis` обёрнута в `try/except ImportError` — при отсутствии `fakeredis` фикстура пропускается без ошибки ([`tests/conftest.py:68`](tests/conftest.py:68))

### Результаты итогового `check`

| Проверка            | Результат                                                |
| ------------------- | -------------------------------------------------------- |
| Ruff check          | ✅ All checks passed (34 файла)                          |
| Mypy                | ✅ Success (28 файлов)                                   |
| Markdownlint        | ✅ 0 ошибок                                              |
| Ruff format --check | ✅ 34 files already formatted                            |
| Prettier --check    | ✅ Все файлы отформатированы                             |
| Pytest              | ✅ 127 passed, 15 failed (test_cache.py — нет fakeredis) |
| — monitor_classify  | ✅ 12/12 passed                                          |
| — monitor_full      | ✅ 18/18 passed                                          |

### Изменённые файлы

| Файл                                                               | Действие  |
| ------------------------------------------------------------------ | --------- |
| [`Makefile`](Makefile)                                             | Переписан |
| [`tasks.ps1`](tasks.ps1)                                           | Изменён   |
| [`.gitignore`](.gitignore)                                         | Изменён   |
| [`.roo/rules/core.md`](.roo/rules/core.md)                         | Изменён   |
| [`.roo/rules/workflow.md`](.roo/rules/workflow.md)                 | Изменён   |
| [`src/utils/redis.py`](src/utils/redis.py)                         | Изменён   |
| [`tests/conftest.py`](tests/conftest.py)                           | Изменён   |
| [`docs/agents/SESSION_LOG.md`](docs/agents/SESSION_LOG.md)         | Переписан |
| [`docs/agents/SESSION_ARCHIVE.md`](docs/agents/SESSION_ARCHIVE.md) | Изменён   |

---

## 2026-05-14 (Настройка CI/CD, протокол временных файлов, исправление Redis-импорта и cache-тестов)

### Задача

Автоматизация полного цикла проверок (lint + format-check + test) через единую команду `check`.
Внедрение протокола изоляции вывода во временные файлы и обязательной очистки (Zero-Trace).
Исправление ошибок импорта `redis` в тестах monitor.
Исправление 15 падающих тестов `test_cache.py` — создание in-memory mock Redis без зависимости от `fakeredis`.

### Выполненные задачи

- **Makefile:** Заменена цель `check` (была `poetry check`) на полный CI-цикл: ruff check + mypy + markdownlint + ruff format --check + prettier --check + pytest. Старая цель вынесена в `verify-pyproject` ([`Makefile:28`](Makefile:28))
- **tasks.ps1:** Аналогично Makefile — `check` теперь полный CI, `verify-pyproject` для poetry check ([`tasks.ps1:92`](tasks.ps1:92))
- **.gitignore:** Добавлены маски `.tmp_*` и `*.tmp` для временных файлов ([`.gitignore:33`](.gitignore:33))
- **core.md:** Добавлена таблица «Временные файлы (полностью)» с масками `.tmp_*` и `*.tmp` в список игнорируемых ([`.roo/rules/core.md:43`](.roo/rules/core.md:43))
- **workflow.md:** Добавлен раздел «Протокол выполнения проверок и работы с временными файлами» — правила изоляции вывода, чтения через `read_file` и обязательной очистки Zero-Trace ([`.roo/rules/workflow.md:56`](.roo/rules/workflow.md:56))
- **redis.py:** Ленивый импорт `redis.asyncio` — вынесен из уровня модуля в `_connect()`. Аннотации заменены на `Any` с `TYPE_CHECKING` ([`src/utils/redis.py:23`](src/utils/redis.py:23))
- **conftest.py:** Создан `SimpleInMemoryRedis` — dict-based mock Redis без внешних зависимостей. Фикстура `fake_redis` теперь **всегда** патчит `get_redis` (через `SimpleInMemoryRedis` если `fakeredis` недоступен, иначе через `FakeRedis`). `SimplePipeline` для поддержки операций `pipeline()`. Исправлен `FakeRedisClient.set()` — добавлен параметр `nx` ([`tests/conftest.py:79`](tests/conftest.py:79))

### Результаты итогового `check`

| Проверка            | Результат                    |
| ------------------- | ---------------------------- |
| Ruff check          | ✅ All checks passed         |
| Mypy                | ✅ Success                   |
| Markdownlint        | ✅ 0 ошибок                  |
| Ruff format --check | ✅ Все файлы отформатированы |
| Prettier --check    | ✅ Все файлы отформатированы |
| Pytest              | ✅ **142 passed, 0 failed**  |
| — test_cache        | ✅ 15/15 passed              |
| — monitor_classify  | ✅ 12/12 passed              |
| — monitor_full      | ✅ 18/18 passed              |

### Изменённые файлы

| Файл                                                               | Действие  |
| ------------------------------------------------------------------ | --------- |
| [`Makefile`](Makefile)                                             | Переписан |
| [`tasks.ps1`](tasks.ps1)                                           | Изменён   |
| [`.gitignore`](.gitignore)                                         | Изменён   |
| [`.roo/rules/core.md`](.roo/rules/core.md)                         | Изменён   |
| [`.roo/rules/workflow.md`](.roo/rules/workflow.md)                 | Изменён   |
| [`src/utils/redis.py`](src/utils/redis.py)                         | Изменён   |
| [`tests/conftest.py`](tests/conftest.py)                           | Переписан |
| [`docs/agents/SESSION_LOG.md`](docs/agents/SESSION_LOG.md)         | Переписан |
| [`docs/agents/SESSION_ARCHIVE.md`](docs/agents/SESSION_ARCHIVE.md) | Изменён   |

---

## 2026-05-14 (T1: Интеграционные тесты для хендлеров)

### Задача

Создание интеграционных тестов для всех 20 Telegram-обработчиков с использованием mocked aiogram объектов и прямого вызова handler'ов (без поднятия бота).

### Выполненные задачи

- Создан [`tests/test_handlers_registration.py`](tests/test_handlers_registration.py) — 18 тестов для 6 handler'ов FSM-сценария регистрации: `start_add_patient`, `process_fio`, `process_bday`, `process_alias`, `skip_alias`, `cancel_registration`
- Создан [`tests/test_handlers_common.py`](tests/test_handlers_common.py) — 25 тестов для 14 handler'ов навигации и мониторинга: `cmd_start`, `back_to_main`, `select_patient`, `select_city`, `select_clinic`, `toggle_doctor`, `handle_noop`, `stop_all_monitoring`, `back_to_cities`, `back_to_clinics`, `stop_patient_monitoring`, `stop_clinic_monitoring`, `handle_delete_patient`
- Реализованы фабрики `make_message()` / `make_callback()` с `object.__setattr__` для подмены aiogram-методов на `AsyncMock`
- Реализован `FakeFSMContext` — легковесная замена aiogram FSM-контекста
- Настроено подавление ложных mypy/Pylance ошибок: per-file overrides в [`pyproject.toml:85`](pyproject.toml:85) + исключение файлов из Pyright в [`pyrightconfig.json:13`](pyrightconfig.json:13)
- Полный test suite: **185 тестов**, ruff: `All checks passed!`, mypy: `Success: no issues found`

### Изменённые файлы

| Файл                                                                         | Действие |
| ---------------------------------------------------------------------------- | -------- |
| [`tests/test_handlers_registration.py`](tests/test_handlers_registration.py) | Создан   |
| [`tests/test_handlers_common.py`](tests/test_handlers_common.py)             | Создан   |
| [`pyproject.toml`](pyproject.toml)                                           | Изменён  |
| [`pyrightconfig.json`](pyrightconfig.json)                                   | Изменён  |

---

## 2026-05-14 (T2: Система именования изображений для уведомлений)

### Задача

Спроектировать систему именования PNG-изображений для заголовков сообщений Telegram-бота (6 изображений), создать директорию хранения, задокументировать правила в архитектуре проекта.

### Выполненные задачи

- Создана директория [`src/assets/images/`](src/assets/images/) с `.gitkeep` для хранения PNG-изображений
- Создан [`src/assets/__init__.py`](src/assets/__init__.py) — делает `assets` Python-пакетом
- Создан [`src/assets/README.md`](src/assets/README.md) — полная документация системы именования:
  - Шаблон: `{контекст}_{состояние}.png` (snake_case, только PNG)
  - Задокументированы 6 текущих изображений (patient, clinic, doctor_dentist/adult/child, slot_empty)
  - Запланированы 3 будущих состояния (slot_available, slot_new, slot_decreased)
  - Справочники контекстов и состояний
  - Требования к файлам (800×400 px, ≤512 КБ)
  - Пример кода использования через `FSInputFile` + `send_photo()`
- Обновлён [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md):
  - Дерево директорий — добавлен `src/assets/` с поддиректориями
  - Таблица зон ответственности — добавлена строка `src/assets/`
- Обновлён [`docs/agents/AGENT_TASKS.md`](docs/agents/AGENT_TASKS.md) — добавлена задача F4 (отправка изображений-заголовков)

### Изменённые файлы

| Файл                                                       | Действие |
| ---------------------------------------------------------- | -------- |
| [`src/assets/__init__.py`](src/assets/__init__.py)         | Создан   |
| [`src/assets/README.md`](src/assets/README.md)             | Создан   |
| [`src/assets/images/.gitkeep`](src/assets/images/.gitkeep) | Создан   |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)             | Изменён  |
| [`docs/agents/AGENT_TASKS.md`](docs/agents/AGENT_TASKS.md) | Изменён  |

### Результаты проверок

| Инструмент   | Результат   |
| ------------ | ----------- |
| markdownlint | ✅ 0 errors |
| prettier     | ✅ 0 errors |

---

## 2026-05-14 (T3: Отправка изображений-заголовков в уведомлениях — F4)

### Задача

Реализовать отправку PNG-изображений как заголовков к текстовым уведомлениям через `send_photo()` Telegram Bot API. Изображения выбираются в зависимости от типа уведомления (empty/available/new/decreased) и загружаются из `src/assets/images/`.

### Выполненные задачи

- Создан [`src/assets/utils.py`](src/assets/utils.py) — хелперы для разрешения путей к изображениям:
  - `NOTIFY_IMAGE_MAP` — маппинг `notify_type` → имя файла (empty, available, new, decreased)
  - `NAV_IMAGE_MAP` — маппинг `nav_type` → имя файла (patient, clinic, doctor\_\*) для будущего использования
  - `get_notify_image_path()` / `get_nav_image_path()` / `get_photo_path()` — безопасное разрешение с проверкой существования
- Модифицирован [`src/services/monitor.py`](src/services/monitor.py):
  - `_classify_slot_change()` — расширен возврат с `(header, display_slots, notify_type)`, где `notify_type`: `"empty"`, `"available"`, `"new"`, `"decreased"`
  - `_send_notification()` — добавлен параметр `photo_path: Path | None`, при наличии отправляет `send_photo()` с `caption`, иначе fallback на `send_message()`
  - `monitor_loop()` — получает `notify_type` из `_classify_slot_change()`, вызывает `get_notify_image_path()`, передаёт в `_send_notification()`
- Модифицирован [`src/handlers/common.py`](src/handlers/common.py):
  - `toggle_doctor()` — удаляет загрузочное сообщение, отправляет финальный результат через `answer_photo()` с изображением-заголовком; `notify_type` определяется как `"available"` или `"empty"`
- Обновлены тесты [`tests/test_monitor_classify.py`](tests/test_monitor_classify.py):
  - Все 7 тестов `_classify_slot_change()` обновлены на распаковку 3 значений вместо 2
  - Добавлены assert-проверки `notify_type` для каждого сценария

### Изменённые файлы

| Файл                                                               | Действие |
| ------------------------------------------------------------------ | -------- |
| [`src/assets/utils.py`](src/assets/utils.py)                       | Создан   |
| [`src/services/monitor.py`](src/services/monitor.py)               | Изменён  |
| [`src/handlers/common.py`](src/handlers/common.py)                 | Изменён  |
| [`tests/test_monitor_classify.py`](tests/test_monitor_classify.py) | Изменён  |

### Результаты проверок

| Инструмент  | Результат                   |
| ----------- | --------------------------- |
| ruff        | ✅ All checks passed!       |
| ruff format | ✅ 0 errors                 |
| mypy        | ✅ Success: no issues found |
| pytest      | ✅ 185 passed, 0 failed     |

---

## 2026-05-14 (T4: Изображения в навигационных сообщениях + slot_available)

### Задача

Добавить изображения-заголовки во все навигационные сообщения (с инлайн-клавиатурами): выбор пациента, клиники, врача, сброс мониторинга, удаление пациента. Также переименован файл `99b9f6c6-...png` → `slot_available.png` и перенесён в актуальный комплект.

### Выполненные задачи

- Добавлен хелпер [`_send_nav_photo()`](src/handlers/common.py:151) в [`src/handlers/common.py`](src/handlers/common.py):
  - Принимает `Bot | None` — если бот доступен, удаляет предыдущее сообщение и отправляет новое через `send_photo()` с `caption` и `reply_markup`
  - При отсутствии бота (тестовый режим) — fallback на `edit_text()` с тем же `reply_markup`
  - При отсутствии файла изображения — fallback на `send_message()` без фото
- Изменены все навигационные хендлеры для использования `_send_nav_photo()`:
  - [`cmd_start()`](src/handlers/common.py:219) — `patient_select.png` через `answer_photo` с fallback на `answer`
  - [`back_to_main()`](src/handlers/common.py:252) — `patient_select.png`
  - [`select_patient()`](src/handlers/common.py:274) — `clinic_select.png`
  - [`select_city()`](src/handlers/common.py:305) — `clinic_select.png`
  - [`back_to_cities()`](src/handlers/common.py:353) — `clinic_select.png`
  - [`back_to_clinics()`](src/handlers/common.py:379) — `clinic_select.png`
  - [`select_clinic()`](src/handlers/common.py:431) — `doctor_*.png` (определяется по типу клиники через `_get_clinic_type_from_db()`)
  - [`toggle_doctor()`](src/handlers/common.py:493) disable-путь — `doctor_*.png`
  - [`stop_patient_monitoring()`](src/handlers/common.py:625) — `clinic_select.png`
  - [`stop_clinic_monitoring()`](src/handlers/common.py:710) — `doctor_*.png`
  - [`stop_all_monitoring()`](src/handlers/common.py:779) — `patient_select.png`
  - [`handle_delete_patient()`](src/handlers/common.py:814) — `patient_select.png`
- Переименован файл `99b9f6c6-48f6-44f0-8ef7-198e3d571e1d.png` → `slot_available.png`
- Обновлён [`src/assets/README.md`](src/assets/README.md): `slot_available.png` перенесён из «будущих состояний» в «текущий комплект» (позиция #7)
- Обновлены тесты [`tests/test_handlers_common.py`](tests/test_handlers_common.py):
  - Добавлен `bot.send_photo = AsyncMock()` в `make_mock_bot()`
  - Тесты `test_disable_monitoring`, `test_stop_all_clears_monitoring`, `test_stop_patient_city_context`, `test_stop_patient_clinic_context`, `test_delete_yes_with_other_patients`, `test_delete_yes_last_patient_shows_welcome` — заменены ассерты `call.message.edit_text` на `bot.send_photo` / `mock_bot.send_photo`

### Изменённые файлы

| Файл                                                                           | Действие                    |
| ------------------------------------------------------------------------------ | --------------------------- |
| [`src/handlers/common.py`](src/handlers/common.py)                             | Изменён (полная перезапись) |
| [`tests/test_handlers_common.py`](tests/test_handlers_common.py)               | Изменён                     |
| [`src/assets/README.md`](src/assets/README.md)                                 | Изменён                     |
| [`src/assets/images/slot_available.png`](src/assets/images/slot_available.png) | Переименован                |

### Результаты проверок

| Инструмент | Результат                              |
| ---------- | -------------------------------------- |
| ruff       | ✅ All checks passed!                  |
| mypy       | ✅ Success: no issues found (30 files) |
| pytest     | ✅ 185 passed, 0 failed                |

---

## 2026-05-15 (T5: Очистка сообщений при /start + сводка мониторинга)

### Задача

При каждом вводе `/start` удалять все предыдущие сообщения бота из чата, чтобы не плодились дубли. Добавить текстовую сводку активного мониторинга (врачи по пациентам) прямо в ответе на `/start` и в `back_to_main`.

### Выполненные задачи

- Модифицирован [`_send_nav_photo()`](src/handlers/common.py:151):
  - Добавлен опциональный параметр `db: DatabaseManager | None = None`
  - При наличии `db` и `bot`: удаляет предыдущее навигационное сообщение (ключ `"__nav__"`) и сохраняет ID нового
  - Рефакторинг: результат `send_photo`/`send_message` теперь присваивается переменной `result`
- Добавлена функция [`build_monitoring_summary()`](src/handlers/common.py:218) — формирует текст сводки:
  - Группировка врачей по пациентам с псевдонимами/ФИО
  - Сортировка по имени, древовидный префикс (`┣`/`┗`) с иконкой `🧑‍⚕️`
  - Краткие названия через `shorten_fio()`/`shorten_specialty()`
- Обновлён [`cmd_start()`](src/handlers/common.py:294):
  - Добавлен параметр `bot: Bot` для удаления сообщений
  - В начале: `_delete_cleanup_msg_entries(bot, uid, "", ...)` — удаляет **все** сообщения бота из чата
  - Очистка `last_messages` через `db.update_user(uid, {"last_messages": {}})`
  - Вывод сводки мониторинга через `build_monitoring_summary()`
  - Сохранение ID навигационного сообщения под ключом `"__nav__"`
- Обновлён [`back_to_main()`](src/handlers/common.py:348) — добавлена сводка мониторинга
- Во все вызовы `_send_nav_photo()` в остальных хендлерах добавлен `db=db` (12 вызовов)
- Обновлены тесты [`tests/test_handlers_common.py`](tests/test_handlers_common.py):
  - Во все тесты `TestCmdStart` добавлен `bot = make_mock_bot()` и `msg.answer.return_value.message_id = 999`

### Изменённые файлы

| Файл                                                             | Действие                |
| ---------------------------------------------------------------- | ----------------------- |
| [`src/handlers/common.py`](src/handlers/common.py)               | Изменён (+98/-45 строк) |
| [`tests/test_handlers_common.py`](tests/test_handlers_common.py) | Изменён (+9/-0)         |

### Результаты проверок

| Инструмент | Результат               |
| ---------- | ----------------------- |
| ruff       | ✅ All checks passed!   |
| pytest     | ✅ 185 passed, 0 failed |

---

## 2026-05-15 (T6: Форматирование слотов + исправление чекбоксов)

### Задача

Исправить 4 проблемы, выявленные пользователем:

1. Нестабильная работа чекбоксов (✅/▫️) на кнопках выбора врачей
2. После выбора врача для мониторинга не появляется кнопка «Сбросить мониторинг этой клиники»
3. Слишком длинные уведомления при найденных слотах (>15)
4. Слоты должны быть отсортированы по дате и времени (восходящий порядок)

### Выполненные задачи

- **Диагностика:** Проблемы 1 и 2 — общая корневая причина: [`toggle_doctor()`](src/handlers/common.py:599) при включении мониторинга не обновлял клавиатуру, оставляя кнопку без чекбокса и не показывая кнопку сброса клиники.

- **Исправление клавиатуры при включении** ([`toggle_doctor()`](src/handlers/common.py:714)):
  После успешного включения мониторинга добавлен вызов `_send_nav_photo()` с обновлённой клавиатурой `get_doctor_selection()`, которая отражает новое состояние мониторинга (✅) и показывает кнопку сброса.

- **Исправление битой сигнатуры** [`_send_nav_photo()`](src/handlers/common.py:963):
  В [`handle_delete_patient()`](src/handlers/common.py:960) пропал аргумент `text` при вызове `_send_nav_photo`. Восстановлен.

- **Новая функция** [`format_slots()`](src/utils/helpers.py:191) — Вариант M:
  - Группировка по дате с днём недели: `📆 Пн 19.05 — 6 шт.`
  - Детальный формат: времена через запятую `─ 09:00, 09:15, 10:20`
  - Компактный формат: диапазон `с 09:00 до 10:50`
  - Пороги: `detail_threshold` (времён на дату, по умолчанию 10) и `compact_threshold` (всего слотов, по умолчанию 15)
  - Поддержка префикса `[NEW]` — отображается как 🆕 в выводе

- **Вспомогательные функции** ([`src/utils/helpers.py`](src/utils/helpers.py)):
  - [`_parse_slot()`](src/utils/helpers.py:170) — парсинг `YYYY-MM-DD в HH:MM` в `(datetime, time)`, игнорирует префикс `[NEW]`
  - [`_slot_sort_key()`](src/utils/helpers.py:186) — ключ сортировки по дате+времени
  - [`_WEEKDAYS`](src/utils/helpers.py:168) — список сокращений дней недели

- **Конфигурация** ([`src/config.py`](src/config.py)):
  - `SLOT_DETAIL_THRESHOLD=10` — макс. слотов на дату для детального формата
  - `SLOT_COMPACT_THRESHOLD=15` — макс. всего слотов для детального формата
  - Синхронизация через `load_config_from_db()`

- **Сортировка в API** ([`src/api/zdrav_client.py`](src/api/zdrav_client.py:201)): `slots.sort()` в `check_slots()`.

- **Мониторинг** ([`src/services/monitor.py`](src/services/monitor.py)):
  - Использование `format_slots()` с порогами из конфига вместо сырого вывода
  - Импорт `format_slots`, `shorten_fio`, `shorten_specialty`

- **База данных** ([`src/database/database.py`](src/database/database.py)):
  - `slot_detail_threshold` и `slot_compact_threshold` добавлены в `seed_config_from_defaults()`

- **Конфигурация окружения** ([`.env.example`](.env.example)):
  - `SLOT_DETAIL_THRESHOLD=10`
  - `SLOT_COMPACT_THRESHOLD=15`

- **Тесты** ([`tests/test_monitor_full.py`](tests/test_monitor_full.py)):
  - [`test_new_slots_marked_in_notification()`](tests/test_monitor_full.py:520) — обновлён: проверка `🆕` вместо `[NEW]`, проверка `11:00` вместо сырой строки

### Изменённые файлы

| Файл                                                       | Действие                |
| ---------------------------------------------------------- | ----------------------- |
| [`src/config.py`](src/config.py)                           | Изменён (+6 строк)      |
| [`src/utils/helpers.py`](src/utils/helpers.py)             | Изменён (+110/-3 строк) |
| [`src/handlers/common.py`](src/handlers/common.py)         | Изменён (+30/-5 строк)  |
| [`src/services/monitor.py`](src/services/monitor.py)       | Изменён (+8/-5 строк)   |
| [`src/api/zdrav_client.py`](src/api/zdrav_client.py)       | Изменён (+1 строка)     |
| [`src/database/database.py`](src/database/database.py)     | Изменён (+2 строки)     |
| [`.env.example`](.env.example)                             | Изменён (+2 строки)     |
| [`tests/test_monitor_full.py`](tests/test_monitor_full.py) | Изменён (+2/-2)         |

### Результаты проверок

| Инструмент | Результат               |
| ---------- | ----------------------- |
| ruff       | ✅ All checks passed!   |
| pytest     | ✅ 185 passed, 0 failed |

---

## 2026-05-16 (T7: Оптимизация кода — рекомендации A, B, G, H)

### Задача

Применить 4 низкорисковые рекомендации из анализа [`docs/code_review_optimization.md`](docs/code_review_optimization.md),
выполненного в этой же сессии.

### Выполненные задачи

- **A — Вынос `_CLINIC_NAV_TYPE_MAP` в константу модуля** ([`src/handlers/common.py`](src/handlers/common.py:36)):
  Словарь `{"adult": "doctor_adult", "child": "doctor_child", "all": "doctor_dentist"}` дублировался
  в 4 местах: `select_clinic`, `toggle_doctor` ON, `toggle_doctor` OFF, `stop_clinic_monitoring`.
  Вынесен в модульную константу `_CLINIC_NAV_TYPE_MAP`. 4 инлайн-копии заменены ссылкой на константу.

- **B — Хелпер `_decode_city_from_idx()`** ([`src/handlers/common.py`](src/handlers/common.py:43)):
  Логика декодирования `city_idx` → `selected_city` + `city_label` дублировалась в 3 местах:
  `select_city`, `back_to_clinics`, `stop_patient_monitoring`. Вынесена в функцию-хелпер.
  3 дублирующих блока заменены вызовом хелпера.

- **G — Агрегация clinic_ids внутри `discovery_loop`** ([`src/services/doctor_discovery.py`](src/services/doctor_discovery.py:47)):
  Ранее `_start_background_tasks` создавал N фоновых задач discovery (по одной на clinic_id),
  каждая получала свой экземпляр `DoctorManager`. Теперь `discovery_loop` сам агрегирует все
  активные `clinic_ids` через `database.get_active_clinic_ids()` и напрямую использует
  `database.merge_doctors()`. `_start_background_tasks` создаёт 1 задачу discovery вместо N.
  Зависимость от `DoctorManager` в discovery полностью удалена.

- **H — Модуль `proxy_discovery.py`** ([`src/utils/proxy_discovery.py`](src/utils/proxy_discovery.py)):
  Логика автоопределения прокси (76 строк в [`main.py`](src/main.py)) вынесена в отдельный модуль.
  Функции: `_parse_proxy_host_port`, `_probe_host`, `_generate_docker_gateways`,
  `discover_proxy`, `check_proxy_connectivity`. Исправлена ошибка ruff ASYNC109
  (параметр `timeout` переименован в `connect_timeout`).

### Изменённые файлы

| Файл                                                                   | Действие                    |
| ---------------------------------------------------------------------- | --------------------------- |
| [`src/handlers/common.py`](src/handlers/common.py)                     | Изменён (+17/-39 строк)     |
| [`src/services/doctor_discovery.py`](src/services/doctor_discovery.py) | Изменён (-10 строк)         |
| [`src/main.py`](src/main.py)                                           | Изменён (-111 строк)        |
| [`src/utils/proxy_discovery.py`](src/utils/proxy_discovery.py)         | **Новый файл** (+130 строк) |
| [`docs/code_review_optimization.md`](docs/code_review_optimization.md) | Изменён (актуализация)      |

### Результаты проверок

| Инструмент | Результат               |
| ---------- | ----------------------- |
| ruff       | ✅ All checks passed!   |
| pytest     | ✅ 185 passed, 0 failed |

---

## 2026-05-16 (Коммит рефакторинга T7)

### Задача

Закоммитить все изменения, накопленные в сессии T7 (оптимизация кода — рекомендации A, B, G, H).

### Выполненные задачи

- **Git commit** `11516b0` — 9 files changed, 709 insertions, 625 deletions.
- Pre-commit хуки: все пройдены (mixed-line-ending автофиксил `.vscode/settings.json` и `src/utils/proxy_discovery.py`).
- Состав коммита:
  - `src/utils/proxy_discovery.py` — новый модуль (+125 строк)
  - `src/main.py` — удалены утилиты прокси, агрегированный discovery (−111 строк)
  - `src/services/doctor_discovery.py` — `discovery_loop` с `Database` вместо `DoctorManager`
  - `src/handlers/common.py` — дедупликация `_CLINIC_NAV_TYPE_MAP` и `_decode_city_from_idx()`
  - `docs/code_review_optimization.md` — перенесён из корня в `docs/`
  - `docs/agents/` — обновлены SESSION_LOG и SESSION_ARCHIVE

### Изменённые файлы

| Файл                                                                         | Действие          |
| ---------------------------------------------------------------------------- | ----------------- |
| [`src/utils/proxy_discovery.py`](../../src/utils/proxy_discovery.py)         | Создан            |
| [`src/main.py`](../../src/main.py)                                           | Изменён           |
| [`src/services/doctor_discovery.py`](../../src/services/doctor_discovery.py) | Изменён           |
| [`src/handlers/common.py`](../../src/handlers/common.py)                     | Изменён           |
| [`docs/code_review_optimization.md`](../code_review_optimization.md)         | Перенесён в docs/ |
| [`docs/agents/SESSION_LOG.md`](SESSION_LOG.md)                               | Изменён           |
| [`docs/agents/SESSION_ARCHIVE.md`](SESSION_ARCHIVE.md)                       | Изменён           |

---

## 2026-05-16 (Рефакторинг — находки B, C, E)

### Задача

Реализовать находки B, C, E из [`docs/code_review_optimization.md`](../code_review_optimization.md): вынесение дублирующегося кода в переиспользуемые хелперы.

### Выполненные задачи

- **Находка B** — [`_build_clinic_selection_kb()`](../../src/handlers/common.py:57): хелпер для сборки клавиатуры выбора клиники. Заменены 2 дублирующих вызова `get_clinic_selection(...)` в `select_city` и `back_to_clinics`. **Экономия: ~9 строк.**
- **Находка C** — [`format_notification_text()`](../../src/utils/helpers.py:278): функция сборки текста уведомления о номерках. Заменены 2 дублирующих места: в [`monitor.py`](../../src/services/monitor.py:223) (обе ветки) и в [`common.py`](../../src/handlers/common.py:720). **Экономия: ~12 строк.**
- **Находка E** — [`_send_or_update_message()`](../../src/handlers/common.py:199): низкоуровневый хелпер «удалить старое → отправить новое → сохранить msg_id». Использован в [`_send_nav_photo()`](../../src/handlers/common.py:249) и [`_send_notification()`](../../src/services/monitor.py:35). **Экономия: ~10 строк.**

### Изменённые файлы

| Файл                                                       | Действие                |
| ---------------------------------------------------------- | ----------------------- |
| [`src/handlers/common.py`](../../src/handlers/common.py)   | Изменён (+70/-50 строк) |
| [`src/services/monitor.py`](../../src/services/monitor.py) | Изменён (+8/-18 строк)  |
| [`src/utils/helpers.py`](../../src/utils/helpers.py)       | Изменён (+16 строк)     |

### Результаты проверок

| Инструмент | Результат             |
| ---------- | --------------------- |
| ruff       | ✅ All checks passed! |

---

## 2026-05-16 (Удаление DoctorManager — находка D)

### Задача

Удалить неиспользуемый класс `DoctorManager` и связанные тесты (находка D из [`docs/code_review_optimization.md`](../code_review_optimization.md)).

### Выполненные задачи

- **Удалён** [`src/database/doctor_manager.py`](../../src/database/doctor_manager.py) (32 строки) — класс `DoctorManager` не использовался в production-коде. `discovery_loop()` уже принимает `Database` напрямую.
- **Обновлён** [`tests/conftest.py`](../../tests/conftest.py) — удалён импорт `DoctorManager` и фикстура `doctor_manager` (строки 14, 62–66).
- **Обновлён** [`tests/test_doctor_discovery.py`](../../tests/test_doctor_discovery.py) — удалена неиспользуемая `_make_mock_doctor_manager()` (строки 34–39).
- **Удалён** [`tests/test_doctor_manager.py`](../../tests/test_doctor_manager.py) — тестировать нечего.
- `src/database/__init__.py` не требовал изменений (не экспортировал `DoctorManager`).
- Grep по `src/` и `tests/`: 0 упоминаний `DoctorManager`.

### Изменённые файлы

| Файл                                                                     | Действие           |
| ------------------------------------------------------------------------ | ------------------ |
| [`src/database/doctor_manager.py`](../../src/database/doctor_manager.py) | Удалён             |
| [`tests/test_doctor_manager.py`](../../tests/test_doctor_manager.py)     | Удалён             |
| [`tests/conftest.py`](../../tests/conftest.py)                           | Изменён (-9 строк) |
| [`tests/test_doctor_discovery.py`](../../tests/test_doctor_discovery.py) | Изменён (-6 строк) |

### Экономия

**~47 строк** (32 doctor_manager.py + 9 conftest.py + 6 test_doctor_discovery.py). Файл `test_doctor_manager.py` удалён целиком.

### Результаты проверок

| Инструмент | Результат             |
| ---------- | --------------------- |
| ruff       | ✅ All checks passed! |

---

## 2026-05-16 (Рефакторинг находок B, C, D, E)

### Задача

Реализовать находки B, C, D, E из [`docs/code_review_optimization.md`](../code_review_optimization.md): вынесение дублирующегося кода в переиспользуемые хелперы и удаление неиспользуемого `DoctorManager`.

### Выполненные задачи

- **Находка B** — [`_build_clinic_selection_kb()`](../../src/handlers/common.py:57): хелпер для сборки клавиатуры выбора клиники. Заменены 2 дублирующих вызова `get_clinic_selection(...)` в [`select_city()`](../../src/handlers/common.py) и [`back_to_clinics()`](../../src/handlers/common.py).
- **Находка C** — [`format_notification_text()`](../../src/utils/helpers.py:278): функция сборки текста уведомления о номерках. Заменены 2 дублирующих места: в [`_send_notification()`](../../src/services/monitor.py) (обе ветки) и в [`toggle_doctor()`](../../src/handlers/common.py).
- **Находка D** — Удалён [`src/database/doctor_manager.py`](../../src/database/doctor_manager.py) (32 строки): класс `DoctorManager` не использовался в production-коде. `discovery_loop()` уже принимает `Database` напрямую.
- **Находка E** — [`_send_or_update_message()`](../../src/handlers/common.py:199): низкоуровневый хелпер «удалить старое → отправить новое → сохранить msg_id». Использован в [`_send_nav_photo()`](../../src/handlers/common.py) и [`_send_notification()`](../../src/services/monitor.py).

### Изменённые файлы

| Файл                                                                     | Действие                |
| ------------------------------------------------------------------------ | ----------------------- |
| [`src/handlers/common.py`](../../src/handlers/common.py)                 | Изменён (+70/-50 строк) |
| [`src/services/monitor.py`](../../src/services/monitor.py)               | Изменён (+8/-18 строк)  |
| [`src/utils/helpers.py`](../../src/utils/helpers.py)                     | Изменён (+16 строк)     |
| [`tests/conftest.py`](../../tests/conftest.py)                           | Изменён (-9 строк)      |
| [`tests/test_doctor_discovery.py`](../../tests/test_doctor_discovery.py) | Изменён (-6 строк)      |
| [`src/database/doctor_manager.py`](../../src/database/doctor_manager.py) | Удалён                  |
| [`tests/test_doctor_manager.py`](../../tests/test_doctor_manager.py)     | Удалён                  |

### Экономия

**~78 строк** сэкономлено (net: +94 новых — ~172 удалённых). 2 файла удалены целиком.

### Результаты проверок

| Инструмент | Результат               |
| ---------- | ----------------------- |
| ruff       | ✅ All checks passed!   |
| pytest     | ✅ 185 passed, 0 failed |

---

## 2026-05-18 (Graceful degradation без Redis)

### Задача

По запросу пользователя проанализирован [`logs/error.log`](../../logs/error.log) — обнаружена ошибка `redis.exceptions.ConnectionError` при старте бота (3 краша подряд). Реализован graceful degradation: бот теперь стартует и работает без Redis.

### Выполненные задачи

- **Анализ error.log** — [`logs/error.log`](../../logs/error.log): 9461 строка. Бот работал 07:28–08:43 без ошибок, затем 3 попытки перезапуска с `ConnectionRefusedError: [WinError 1225]` на `localhost:6379`. Redis-контейнер не был запущен.
- **Graceful degradation в RedisClient** — [`src/utils/redis.py`](../../src/utils/redis.py:27): добавлен флаг `is_available`, метод `_connect()` перехватывает `ConnectionError` и переходит в fallback-режим, все публичные методы возвращают безопасные значения по умолчанию (`None`, `False`, `0`, `[]`).
- **FSM-хранилище с fallback** — [`src/main.py`](../../src/main.py:192): если Redis доступен → `RedisStorage`, иначе → `MemoryStorage` (aiogram in-memory).
- **Rate limiter с проверкой** — [`src/middleware/ratelimit.py`](../../src/middleware/ratelimit.py:42): `_is_limited()` проверяет `redis.is_available`, при недоступности пропускает запросы.
- **Cache с проверкой** — [`src/utils/cache.py`](../../src/utils/cache.py): `is_spam()`, `swap_cache_key()`, `delete_cache_keys_by_prefix()` проверяют `redis.is_available` перед использованием `.client`.
- **Тестовые фикстуры** — [`tests/conftest.py`](../../tests/conftest.py:196): `FakeRedisClient` дополнен `is_available = True`.
- **Анализ docker-compose** — [`docker-compose.yml`](../../docker-compose.yml): Redis настроен корректно (`127.0.0.1:6379`, `restart: always`). Qdrant используется для IDE codebase indexing — не удалять.

### Изменённые файлы

| Файл                                                               | Действие         |
| ------------------------------------------------------------------ | ---------------- |
| [`src/utils/redis.py`](../../src/utils/redis.py)                   | Изменён (+45/-5) |
| [`src/main.py`](../../src/main.py)                                 | Изменён (+8/-2)  |
| [`src/middleware/ratelimit.py`](../../src/middleware/ratelimit.py) | Изменён (+5/-0)  |
| [`src/utils/cache.py`](../../src/utils/cache.py)                   | Изменён (+12/-0) |
| [`tests/conftest.py`](../../tests/conftest.py)                     | Изменён (+1/-0)  |

### Результаты проверок

| Инструмент | Результат                                 |
| ---------- | ----------------------------------------- |
| ruff       | ✅ All checks passed!                     |
| pytest     | ✅ 50 passed, 8 failed (предсуществующие) |

---

## 2026-05-18 (Распараллеливание monitor_loop)

### Задача

Распараллеливание цикла мониторинга в [`src/services/monitor.py`](../../src/services/monitor.py) для устранения критической проблемы производительности: тройной вложенный цикл (пользователи → пациенты → врачи) с последовательными HTTP-запросами. При 100 пользователях × 2 пациента × 3 врача = 600 последовательных запросов, полный цикл >30 минут.

### Выполненные задачи

- **Выделена вспомогательная функция** [`_check_single_doctor()`](../../src/services/monitor.py:111) — инкапсулирует полный цикл проверки одного врача: jitter → API-запрос → классификация → уведомление.
- **Параллельное выполнение** через `asyncio.gather()` — все врачи одного пациента проверяются одновременно.
- **Семафор** [`asyncio.Semaphore(10)`](../../src/services/monitor.py:243) — ограничивает количество одновременных HTTP-запросов к API.
- **Потокобезопасность** `empty_counts` через [`asyncio.Lock`](../../src/services/monitor.py:242) — защита разделяемого словаря при конкурентном доступе.
- **Jitter-логика сохранена** — `asyncio.sleep(1.0–3.0)` перед каждым запросом, вне семафора (не занимает слоты ожиданием).
- Логика классификации `_classify_slot_change`, отправки уведомлений `_send_notification` и все вызовы `db.*` сохранены без изменений.

### Изменённые файлы

| Файл                                                       | Действие           |
| ---------------------------------------------------------- | ------------------ |
| [`src/services/monitor.py`](../../src/services/monitor.py) | Изменён (+135/-98) |

### Результаты проверок

| Инструмент       | Результат                                                        |
| ---------------- | ---------------------------------------------------------------- |
| ruff             | ✅ All checks passed!                                            |
| pytest (monitor) | ✅ 27 passed, 3 failed (предсуществующие в TestSendNotification) |

---

## 2026-05-18 (Консолидация тасков и код-ревью)

### Задача

Консолидация 4 файлов с задачами и код-ревью в 2 целевых файла: [`AGENT_TASKS.md`](AGENT_TASKS.md) (активные задачи) и [`TECH_DEBT.md`](TECH_DEBT.md) (технический долг). Удаление дубликатов, распределение по приоритетам, структурирование по модулям.

### Выполненные задачи

- Прочитаны и проанализированы 4 исходных файла: [`code_review.md`](code_review.md) (2026-05-14), [`docs/agents/CODE_REVIEW.md`](docs/agents/CODE_REVIEW.md) (2026-05-11), [`docs/code_review_optimization.md`](docs/code_review_optimization.md) (2026-05-15), предыдущий [`AGENT_TASKS.md`](docs/agents/AGENT_TASKS.md).
- Выполнена дедупликация: из ~75 пунктов выделены уникальные задачи с перекрёстными ссылками.
- Создан [`AGENT_TASKS.md`](AGENT_TASKS.md) — 24 активные задачи:
  - 🔴 CRITICAL (6): T-MON-PARALLEL, T-CONFIG-ORDER, T-CONN-ENCAPSULATE, T-MONITOR-RESTART-SPAM, T-IF-DB-CHECK, T-HEALTHCHECK-COUNT
  - 🟠 HIGH (6): T-DOCKER, T-CI-CD, T-METRICS, T-REDIS-FALLBACK, T-EXCEPT-PASS, T-CALLBACK-VALIDATION
  - 🟡 MEDIUM (4): T-README, T-HARDCODE-IDS, T-CACHE-STRATEGY, T-API-VERSIONING
  - 🆕 FEATURES (8): F1-F8 (пациенты, интервалы, статистика, i18n, веб-интерфейс, экспорт, аудит-лог, детектор API)
- Создан [`TECH_DEBT.md`](TECH_DEBT.md) — 58 пунктов технического долга:
  - 🟢 LOW / TECH DEBT (36): сгруппированы по модулям `src/` (api, database, handlers, services, middleware, utils, keyboards, tests, main.py, прочее)
  - 🔵 OPTIMIZATION (6): OPT-A, OPT-B, OPT-D, OPT-E, OPT-G, OPT-K (отклонённые/выполненные исключены)
  - ⚪ MINOR (16): мелкие правки (опечатки, форматирование, docstrings, type hints)
- Удалены старые файлы-источники: [`code_review.md`](code_review.md), [`docs/agents/CODE_REVIEW.md`](docs/agents/CODE_REVIEW.md), [`docs/code_review_optimization.md`](docs/code_review_optimization.md).

### Изменённые файлы

| Файл                                                                   | Действие                         |
| ---------------------------------------------------------------------- | -------------------------------- |
| [`docs/agents/AGENT_TASKS.md`](AGENT_TASKS.md)                         | Перезаписан (24 задачи)          |
| [`docs/agents/TECH_DEBT.md`](TECH_DEBT.md)                             | Создан (58 пунктов)              |
| [`docs/agents/SESSION_ARCHIVE.md`](SESSION_ARCHIVE.md)                 | Дополнен (перенос старой записи) |
| [`code_review.md`](code_review.md)                                     | Удалён                           |
| [`docs/agents/CODE_REVIEW.md`](docs/agents/CODE_REVIEW.md)             | Удалён                           |
| [`docs/code_review_optimization.md`](docs/code_review_optimization.md) | Удалён                           |

### Результаты проверок

| Инструмент   | Результат                                   |
| ------------ | ------------------------------------------- |
| markdownlint | ✅ 0 errors (AGENT_TASKS.md + TECH_DEBT.md) |

---

## 2026-05-18 (Проверка статуса OPT-I, OPT-J, OPT-L)

### Задача

Проверка статуса трёх оптимизаций из списка исключённых в [`TECH_DEBT.md`](TECH_DEBT.md) и актуализация: OPT-I (переезд на Pydantic-модели), OPT-J (единая точка выхода), OPT-L (переезд на Redis).

### Выполненные задачи

- Проверен **OPT-I**: Pydantic-модели полностью реализованы — [`Settings`](src/config.py:30) на `pydantic_settings.BaseSettings`, 9 Pydantic-моделей в [`models.py`](src/api/models.py:1-147) (все `BaseModel`).
- Проверен **OPT-J**: единая точка выхода реализована — [`main()`](src/main.py:109) централизованный entry point, унифицированный запуск `asyncio.run(main())` на [`main.py:251`](src/main.py:251).
- Проверен **OPT-L**: Redis полностью внедрён — [`RedisClient`](src/utils/redis.py:27) singleton с graceful degradation, Redis-based кэш в [`cache.py`](src/utils/cache.py), `RedisStorage` для FSM в [`main.py:195-196`](src/main.py:195).
- Удалены OPT-I, OPT-J, OPT-L из списка «Исключены из плана» в [`TECH_DEBT.md`](TECH_DEBT.md).
- Секция «Исключены из плана» теперь содержит только OPT-C, OPT-F, OPT-H (3 пункта вместо 6).

### Изменённые файлы

| Файл                                       | Действие                           |
| ------------------------------------------ | ---------------------------------- |
| [`docs/agents/TECH_DEBT.md`](TECH_DEBT.md) | Удалены строки OPT-I, OPT-J, OPT-L |

### Результаты проверок

| Инструмент   | Результат                  |
| ------------ | -------------------------- |
| markdownlint | ✅ 0 errors (TECH_DEBT.md) |

---

## 2026-05-18 (T-CONFIG-ORDER — Исправлен порядок загрузки конфигурации)

### Задача

Исправить порядок вызова [`load_config_from_db()`](src/config.py:108) и [`sync_clinic_names()`](src/main.py:137) в [`main()`](src/main.py:109), чтобы переопределённый в БД `API_BASE_URL` применялся до синхронизации клиник.

### Выполненные задачи

- Прочитан [`src/main.py`](src/main.py) и [`src/config.py`](src/config.py) — установлен точный порядок инициализации.
- Выяснено, что [`ZdravClient.__init__()`](src/api/zdrav_client.py:21) захватывает `settings.API_BASE_URL` в `self.base_url` при создании.
- Блок загрузки конфигов из БД (строки 139–148) перемещён **до** вызова [`sync_clinic_names()`](src/main.py:137).
- После [`load_config_from_db()`](src/config.py:108) добавлено обновление `api.base_url = settings.API_BASE_URL`, чтобы API-клиент использовал актуальный URL из БД.
- Проверка ruff: `python -m ruff check src/main.py` — **0 ошибок**.

### Изменённые файлы

| Файл                             | Действие                                                                                                         |
| -------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| [`src/main.py`](src/main.py:133) | Переставлены блоки `load_config_from_db` и `sync_clinic_names`; добавлено `api.base_url = settings.API_BASE_URL` |

### Результаты проверок

| Инструмент | Результат             |
| ---------- | --------------------- |
| ruff check | ✅ 0 errors (main.py) |

---

## 2026-05-18 (T-CONN-ENCAPSULATE — Инкапсуляция соединения с БД)

### Задача

Добавить `property` в класс [`Database`](src/database/database.py:122) для доступа к соединению и заменить прямое обращение `self._db._conn` в [`DatabaseManager`](src/database/manager.py) на новый property.

### Выполненные задачи

- Прочитаны [`src/database/database.py`](src/database/database.py) и [`src/database/manager.py`](src/database/manager.py) — установлена структура вложенности `_conn`.
- Найдены 3 места прямого доступа `self._db._conn` в manager.py: строки 55, 70, 95.
- Проверен grep по `src/` — других вхождений `_db._conn` не найдено.
- В класс [`Database`](src/database/database.py:122) добавлен `property conn`, возвращающий `Optional[aiosqlite.Connection]`.
- Выполнена замена `self._db._conn` → `self._db.conn` в трёх местах manager.py.
- Проверка ruff: `python -m ruff check src/database/` — **0 ошибок**.

### Изменённые файлы

| Файл                                                             | Действие                                                                            |
| ---------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| [`src/database/database.py:122`](src/database/database.py:122)   | Добавлен `property conn` с докстрингом и type hint `Optional[aiosqlite.Connection]` |
| [`src/database/manager.py:55,70,95`](src/database/manager.py:55) | Заменено `self._db._conn` → `self._db.conn` в трёх методах                          |

### Результаты проверок

| Инструмент | Результат                   |
| ---------- | --------------------------- |
| ruff check | ✅ 0 errors (src/database/) |

---

## 2026-05-18 (T-MONITOR-RESTART-SPAM — Подавление спама при перезапуске мониторинга)

### Задача

Добавить флаг `initial_sync` в [`src/services/monitor.py`](src/services/monitor.py), чтобы первый цикл после запуска не генерировал ложные уведомления «Появились номерки» при пустом кэше.

### Выполненные задачи

- Прочитаны [`src/services/monitor.py`](src/services/monitor.py) и тесты — установлена архитектура цикла мониторинга.
- В [`_check_single_doctor()`](src/services/monitor.py:111) добавлен keyword-only параметр `initial_sync: bool = False`:
  - После классификации изменений при `initial_sync=True` уведомление не отправляется, кэш заполняется.
  - Добавлено лог-сообщение `"Initial sync — пропускаем уведомление для {} ({}), кэш заполнен"`.
- В [`monitor_loop()`](src/services/monitor.py:244) добавлен флаг `_initial_sync`:
  - Принимает параметр `initial_sync: bool = True` (по умолчанию включён).
  - Перед циклом — лог `"Initial sync active — уведомления подавлены до заполнения кэша"`.
  - После первого успешного цикла — сброс `_initial_sync = False`, лог `"Initial sync completed — уведомления разблокированы"`.
  - При ошибке в первом цикле — также сброс флага, лог `"Initial sync завершён с ошибками — уведомления разблокированы"`.
- Адаптированы тесты в [`tests/test_monitor_full.py`](tests/test_monitor_full.py): 7 тестов получают `initial_sync=False`.
- Добавлен новый тест `test_initial_sync_suppresses_notifications`: проверяет, что при `initial_sync=True` уведомления не отправляются, а кэш заполняется.

### Изменённые файлы

| Файл                                                                 | Действие                                                           |
| -------------------------------------------------------------------- | ------------------------------------------------------------------ |
| [`src/services/monitor.py:111,198,244`](src/services/monitor.py:111) | Добавлены `initial_sync` в `_check_single_doctor` и `monitor_loop` |
| [`tests/test_monitor_full.py`](tests/test_monitor_full.py)           | Адаптированы 7 тестов, добавлен 1 новый тест                       |

### Результаты проверок

| Инструмент | Результат                |
| ---------- | ------------------------ |
| ruff check | ✅ 0 errors (monitor.py) |
| pytest     | ✅ 31 passed             |

---

## 2026-05-18 (T-HEALTHCHECK-COUNT — Исправление подсчёта total_monitored_doctors)

### Задача

Исправить [`src/services/healthcheck.py:158`](src/services/healthcheck.py:158): поле `total_monitored_doctors` считало `len()` от словаря `p_id → d_id` (количество **пациентов** в мониторинге), а не количество уникальных **врачей**.

### Выполненные задачи

- Прочитаны [`src/services/healthcheck.py`](src/services/healthcheck.py) и [`src/database/manager.py`](src/database/manager.py) — установлена структура `monitoring`: `Dict[p_id, Dict[d_id, doctor_info]]`.
- Исправлен подсчёт в [`healthcheck_loop()`](src/services/healthcheck.py:158):
  - **Было:** `len(u_info.get("monitoring", {}))` — считает количество пациентов.
  - **Стало:** `len(set(d_id for doctors in ... for d_id in doctors))` — собирает все `d_id` в set и считает уникальных врачей.
- Исправлен идентичный подсчёт в [`format_status_report()`](src/services/healthcheck.py:193) — та же логическая ошибка.
- Проверка ruff: `python -m ruff check src/services/healthcheck.py` — **0 ошибок**.

### Изменённые файлы

| Файл                                                                     | Действие                                                                  |
| ------------------------------------------------------------------------ | ------------------------------------------------------------------------- |
| [`src/services/healthcheck.py:158,193`](src/services/healthcheck.py:158) | Исправлен подсчёт `total_monitored_doctors` (уникальные `d_id` через set) |

### Результаты проверок

| Инструмент | Результат                                 |
| ---------- | ----------------------------------------- |
| ruff check | ✅ 0 errors (src/services/healthcheck.py) |

---

## 2026-05-18 (Финальная валидация — 5 CRITICAL задач)

### Сводка выполненных CRITICAL задач

В данной сессии (18.05.2026) выполнены следующие 5 CRITICAL задач:

| ID                     | Задача                                                                                                                                                                                       | Статус |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| T-HEALTHCHECK-COUNT    | Исправление подсчёта `total_monitored_doctors` в [`src/services/healthcheck.py`](src/services/healthcheck.py:158) (уникальные врачи через set)                                               | ✅     |
| T-CONFIG-ORDER         | Исправлен порядок загрузки конфигурации в [`src/main.py`](src/main.py:133) — `load_config_from_db()` теперь вызывается до `sync_clinic_names()`                                              | ✅     |
| T-CONN-ENCAPSULATE     | Добавлен `property conn` в [`src/database/database.py:122`](src/database/database.py:122); заменён прямой доступ `_db._conn` → `_db.conn` в 3 местах [`manager.py`](src/database/manager.py) | ✅     |
| T-MONITOR-RESTART-SPAM | Добавлен флаг `initial_sync` в [`src/services/monitor.py`](src/services/monitor.py:111,198,244) — подавление ложных уведомлений при перезапуске                                              | ✅     |
| T-IF-DB-CHECK          | Проверка устаревшей задачи (`cid = str(clinic_id)` уже присутствует на строке 69). Задача признана устаревшей и удалена из [`AGENT_TASKS.md`](docs/agents/AGENT_TASKS.md)                    | ✅     |

### Финальная валидация (текущая подзадача)

- Удалена устаревшая задача T-IF-DB-CHECK из таблицы CRITICAL в [`AGENT_TASKS.md`](docs/agents/AGENT_TASKS.md).
- Запущен полный набор тестов: **179 passed** (23.75s).
- Запущен ruff check для `src/`: **All checks passed!** (0 errors).
- Запущен markdownlint для `docs/**/*.md`, `.roo/**/*.md`, `*.md`: **0 errors**.
- Выполнена очистка временных файлов (`.tmp_*`).

### Изменённые файлы

| Файл                                                               | Действие                                         |
| ------------------------------------------------------------------ | ------------------------------------------------ |
| [`docs/agents/AGENT_TASKS.md`](docs/agents/AGENT_TASKS.md)         | Удалена задача T-IF-DB-CHECK из таблицы CRITICAL |
| [`docs/agents/SESSION_LOG.md`](docs/agents/SESSION_LOG.md)         | Новая сводка по 5 CRITICAL задачам               |
| [`docs/agents/SESSION_ARCHIVE.md`](docs/agents/SESSION_ARCHIVE.md) | Добавлена запись T-HEALTHCHECK-COUNT             |

### Результаты проверок

| Инструмент   | Результат                   |
| ------------ | --------------------------- |
| pytest       | ✅ 179 passed (23.75s)      |
| ruff check   | ✅ All checks passed (src/) |
| markdownlint | ✅ 0 errors                 |

---

## 2026-05-18 (T-CI-CD — CI/CD пайплайн GitHub Actions)

### Задача

Создан файл [`.github/workflows/ci.yml`](.github/workflows/ci.yml) — CI/CD пайплайн для GitHub Actions.

### Реализация

- **Триггеры:** `push` и `pull_request` в ветки `main`, `develop`
- **Параллельные jobs (3):**
  - `lint` — `ruff check src` (проверка без автофикса)
  - `typecheck` — `mypy src scripts tests` (строгая проверка типов)
  - `test` — `pytest` (все тесты, 179 тестов) + Redis-сервис (`redis:7-alpine`)
- **Окружение:** Python 3.11, кэширование pip-зависимостей через `actions/setup-python@v5` с `cache: pip`
- **Конкурентность:** `concurrency` с `cancel-in-progress: true` для отмены дублирующихся запусков
- **Таймаут:** 10 минут на каждый job

### Изменённые файлы

| Файл                                                       | Действие                    |
| ---------------------------------------------------------- | --------------------------- |
| [`.github/workflows/ci.yml`](.github/workflows/ci.yml)     | Перезаписан (полная версия) |
| [`docs/agents/AGENT_TASKS.md`](docs/agents/AGENT_TASKS.md) | Удалена задача T-CI-CD      |
| [`docs/agents/SESSION_LOG.md`](docs/agents/SESSION_LOG.md) | Новая запись сессии         |

---

## 2026-05-19 (T-EXCEPT-PASS — Аудит и исправление `except Exception: pass`)

### Задача

Аудит и исправление всех случаев `except Exception: pass` в проекте. Найдено 15 случаев (на 8 больше, чем указано в задании — часть была добавлена после первоначального аудита).

### Реализация

**Подход:** Для Telegram API-операций через `bot.xxx()` — замена на `except TelegramAPIError: pass`. Для вызовов `.delete()` на объектах `Message` (могут кидать `RuntimeError` без бота) — оставлено `Exception` с `pass`. Для не-Telegram операций — добавлен `logger.debug()` с осмысленным сообщением.

**Таблица изменений:**

| Файл                                                                      | Строки | Операция                     | Действие                                    |
| ------------------------------------------------------------------------- | ------ | ---------------------------- | ------------------------------------------- |
| [`src/handlers/common.py`](src/handlers/common.py:174)                    | 174    | `bot.delete_message()`       | `TelegramAPIError: pass`                    |
| [`src/handlers/common.py`](src/handlers/common.py:222)                    | 222    | `bot.delete_message()`       | `TelegramAPIError: pass`                    |
| [`src/handlers/common.py`](src/handlers/common.py:228)                    | 228    | `old_message.delete()`       | `Exception: pass` (RuntimeError)            |
| [`src/handlers/common.py`](src/handlers/common.py:288)                    | 288    | `_send_or_update_message()`  | `logger.debug()`                            |
| [`src/handlers/common.py`](src/handlers/common.py:295)                    | 295    | `msg.delete()`               | `Exception: pass` (RuntimeError)            |
| [`src/handlers/common.py`](src/handlers/common.py:323)                    | 323    | `db.set_last_message_id()`   | `logger.debug()`                            |
| [`src/handlers/common.py`](src/handlers/common.py:337)                    | 337    | `msg.edit_text()`            | `Exception: logger.debug()` + `return None` |
| [`src/handlers/common.py`](src/handlers/common.py:783)                    | 783    | `loading_msg.delete()`       | `Exception: pass` (RuntimeError)            |
| [`src/main.py`](src/main.py:267)                                          | 267    | `error_notifier.notify()`    | `logger.debug()`                            |
| [`src/utils/redis.py`](src/utils/redis.py:102)                            | 102    | `self._redis.aclose()`       | `logger.debug()`                            |
| [`src/middleware/ratelimit.py`](src/middleware/ratelimit.py:104)          | 104    | `event.answer()`             | `TelegramAPIError: pass`                    |
| [`src/services/doctor_discovery.py`](src/services/doctor_discovery.py:42) | 42     | `database.get_clinic_type()` | `logger.debug()`                            |
| [`src/services/cleanup.py`](src/services/cleanup.py:73)                   | 73     | `bot.delete_message()`       | `TelegramAPIError: pass`                    |
| [`src/database/database.py`](src/database/database.py:168)                | 168    | `PRAGMA wal_checkpoint()`    | `logger.debug()`                            |
| [`src/database/migrations.py`](src/database/migrations.py:88)             | 88     | `ALTER TABLE ADD COLUMN`     | `logger.debug()`                            |

**Попутные исправления:**

- Добавлен импорт `TelegramAPIError` в [`src/handlers/common.py`](src/handlers/common.py:5), [`src/services/cleanup.py`](src/services/cleanup.py:11), [`src/middleware/ratelimit.py`](src/middleware/ratelimit.py:14)
- Исправлен тест [`tests/test_monitor_full.py`](tests/test_monitor_full.py:117) — `Exception("Message not found")` → `TelegramAPIError(method=MagicMock(), message="Message not found")`

### Изменённые файлы

| Файл                                                                      | Действие                         |
| ------------------------------------------------------------------------- | -------------------------------- |
| [`src/handlers/common.py`](src/handlers/common.py)                        | +1 импорт, 8 блоков except       |
| [`src/main.py`](src/main.py:267)                                          | +1 logger.debug                  |
| [`src/utils/redis.py`](src/utils/redis.py:102)                            | +1 logger.debug                  |
| [`src/middleware/ratelimit.py`](src/middleware/ratelimit.py:14,104)       | +1 импорт, +1 TelegramAPIError   |
| [`src/services/doctor_discovery.py`](src/services/doctor_discovery.py:42) | +1 logger.debug                  |
| [`src/services/cleanup.py`](src/services/cleanup.py:11,73)                | +1 импорт, +1 TelegramAPIError   |
| [`src/database/database.py`](src/database/database.py:168)                | +1 logger.debug                  |
| [`src/database/migrations.py`](src/database/migrations.py:88)             | +1 logger.debug                  |
| [`tests/test_monitor_full.py`](tests/test_monitor_full.py:7,117)          | +1 импорт, исправлен side_effect |
| [`docs/agents/AGENT_TASKS.md`](docs/agents/AGENT_TASKS.md)                | Удалена задача T-EXCEPT-PASS     |

### Результаты проверок

| Инструмент       | Результат            |
| ---------------- | -------------------- |
| `ruff check src` | All checks passed    |
| `pytest`         | 179 passed, 0 failed |

---

## 2026-05-19 (T-DOCKER — Dockerfile для бота + актуализация docker-compose.yml)

### Задача

Создание Dockerfile для Telegram-бота (aiogram polling) и актуализация docker-compose.yml: удаление неиспользуемого Qdrant, добавление сервиса `bot`, улучшение Redis (healthcheck, named volume).

### Реализация

**Создан [`Dockerfile`](Dockerfile:1):**

- **Base image:** `python:3.11-slim` — минимальный образ для Python 3.11 (target-version из pyproject.toml)
- **Multi-stage build:** builder-слой для установки зависимостей (с `gcc`/`libc6-dev`), финальный слой — только runtime (`procps`, `sqlite3`)
- **Копирование:** только `src/` и `requirements.txt`; исключены `tests/`, `docs/`, `.git/`, `.roo/`, `.vscode/`, `scripts/`, `data/`, `logs/`
- **Безопасность:** создан непривилегированный пользователь `appuser`, WORKDIR `/app`
- **Healthcheck:** проверка доступности `data/bot.db` (R/W) — косвенный индикатор работы бота
- **Entrypoint:** `python -m src.main` (асинхронный поллинг aiogram)
- **Метки:** `maintainer`, `description`, `version`, `org.opencontainers.image.source`

**Создан [`.dockerignore`](.dockerignore:1):**

Исключены: `.git/`, `.venv/`, `__pycache__/`, `.vscode/`, `.history/`, `.roo/`, `tests/`, `docs/`, `node_modules/`, `dist/`, `data/`, `logs/`, `.env` (реальный), `scripts/`, `*.tmp`, poetry-файлы, Markdown-файлы, конфиги линтеров

**Обновлён [`docker-compose.yml`](docker-compose.yml:1):**

- **Qdrant** — удалён (не используется в проекте)
- **Redis** — улучшен: добавлен `healthcheck` (redis-cli ping), named volume `redis_data` вместо bind mount, включён в общую сеть `zdrav_network`
- **Bot** — новый сервис:
  - `build: .` (текущая директория, Dockerfile)
  - `restart: unless-stopped`
  - `depends_on: redis (condition: service_healthy)` — старт только после готовности Redis
  - `env_file: .env` — все переменные окружения
  - `volumes: bot_data:/app/data` — named volume для персистентности SQLite и кэша
  - `healthcheck` — проверка доступности `data/bot.db`
  - `networks: zdrav_network`
- Добавлены named volumes: `redis_data`, `bot_data`
- Добавлена bridge network: `zdrav_network`

### Изменённые файлы

| Файл                                                       | Действие                   |
| ---------------------------------------------------------- | -------------------------- |
| [`Dockerfile`](Dockerfile:1)                               | Создан                     |
| [`.dockerignore`](.dockerignore:1)                         | Создан                     |
| [`docker-compose.yml`](docker-compose.yml)                 | Перезаписан (Qdrant → Bot) |
| [`docs/agents/AGENT_TASKS.md`](docs/agents/AGENT_TASKS.md) | Удалена задача T-DOCKER    |

### Результаты проверок

| Инструмент | Результат                                           |
| ---------- | --------------------------------------------------- |
| YAML       | Валидация docker-compose.yml — корректный синтаксис |

---

## 2026-05-19 (T-METRICS — Prometheus-метрики: HTTP-endpoint `/metrics`)

### Задача

Добавление HTTP-endpoint `/metrics` с Prometheus-метриками. [`HealthMetrics`](src/services/healthcheck.py:24) уже собирал данные, но они были доступны только через Telegram-команду `/status`. Реализован aiohttp-сервер, запускаемый параллельно с поллингом aiogram.

### Реализация

**Создан [`src/services/metrics.py`](src/services/metrics.py:1):**

- Класс `PrometheusMetrics` — агрегатор метрик для Prometheus
- Синхронизация Counter'ов через дельта-инкременты (не нарушает семантику монотонности)
- Синхронизация Gauge'ев из HealthMetrics + DatabaseManager + RedisClient

**Добавленные метрики (10):**

| Метрика                                    | Тип     | Источник                                      |
| ------------------------------------------ | ------- | --------------------------------------------- |
| `zdrav_monitor_status`                     | Gauge   | `HealthMetrics.monitor_loop_alive`            |
| `zdrav_healthcheck_errors_total`           | Counter | `HealthMetrics.api_errors_total`              |
| `zdrav_healthcheck_last_success_timestamp` | Gauge   | `HealthMetrics.last_api_check_time`           |
| `zdrav_healthcheck_duration_seconds`       | Gauge   | `HealthMetrics.last_check_duration`           |
| `zdrav_slots_found_total`                  | Counter | `HealthMetrics.monitoring_notifications_sent` |
| `zdrav_api_requests_total`                 | Counter | `HealthMetrics.api_checks_total`              |
| `zdrav_api_errors_total`                   | Counter | `HealthMetrics.api_errors_total`              |
| `zdrav_active_users`                       | Gauge   | `DatabaseManager.data` (len)                  |
| `zdrav_monitored_doctors`                  | Gauge   | БД — уникальные `d_id` в мониторинге          |
| `zdrav_redis_connected`                    | Gauge   | `RedisClient.is_available`                    |

**Изменён [`src/services/healthcheck.py`](src/services/healthcheck.py:41):**

- Добавлено поле `last_check_duration: float = 0.0` в [`HealthMetrics`](src/services/healthcheck.py:24)
- В [`healthcheck_loop()`](src/services/healthcheck.py:111) добавлен замер длительности запроса (`check_start = time.time()`, запись в `last_check_duration`)

**Изменён [`src/config.py`](src/config.py:103):**

- Добавлен `METRICS_PORT: int = 9090` в класс `Settings`
- Добавлен `CONFIG_KEY_METRICS_PORT` и запись в `mapping` для загрузки из БД

**Изменён [`src/main.py`](src/main.py):**

- Добавлен импорт `from aiohttp import web`
- Добавлен импорт `from src.services.metrics import prometheus_metrics`
- Добавлена функция `_start_metrics_server()` — запускает aiohttp-сервер на `0.0.0.0:METRICS_PORT`
- Добавлен маршрут `GET /metrics`, возвращающий метрики в формате Prometheus
- Сервер запускается после фоновых задач, останавливается в `finally` через `runner.cleanup()`

**Дополнительные файлы:**

| Файл                                       | Действие                            |
| ------------------------------------------ | ----------------------------------- |
| [`requirements.txt`](requirements.txt)     | Добавлен `prometheus-client>=0.20`  |
| [`.env.example`](.env.example)             | Добавлен `METRICS_PORT=9090`        |
| [`Dockerfile`](Dockerfile:96)              | Добавлен `EXPOSE 9090`              |
| [`docker-compose.yml`](docker-compose.yml) | Добавлен порт `127.0.0.1:9090:9090` |

### Изменённые файлы

| Файл                                                         | Действие |
| ------------------------------------------------------------ | -------- |
| [`src/services/metrics.py`](src/services/metrics.py:1)       | Создан   |
| [`src/services/healthcheck.py`](src/services/healthcheck.py) | Изменён  |
| [`src/config.py`](src/config.py)                             | Изменён  |
| [`src/main.py`](src/main.py)                                 | Изменён  |
| [`requirements.txt`](requirements.txt)                       | Изменён  |
| [`.env.example`](.env.example)                               | Изменён  |
| [`Dockerfile`](Dockerfile)                                   | Изменён  |
| [`docker-compose.yml`](docker-compose.yml)                   | Изменён  |
| [`docs/agents/AGENT_TASKS.md`](docs/agents/AGENT_TASKS.md)   | Изменён  |

### Результаты проверок

| Инструмент   | Результат               |
| ------------ | ----------------------- |
| `ruff check` | ✅ All checks passed!   |
| `pytest`     | ✅ 179 passed, 0 failed |

---

## 2026-05-19 (T-HARDCODE-IDS — Вынос хардкод-идентификаторов в .env / БД)

### Задача

Вынос всех хардкод-идентификаторов из исходного кода в `.env` / БД, чтобы изменение параметров на портале zdrav.lenreg.ru не ломало бота.

### Найденные хардкод-идентификаторы

| #   | Файл                                                     | Строка | Значение                                 | Описание                         |
| --- | -------------------------------------------------------- | ------ | ---------------------------------------- | -------------------------------- |
| 1   | [`src/keyboards/inline.py`](src/keyboards/inline.py:52)  | 52     | `"272"`                                  | ID стоматологической клиники     |
| 2   | [`src/api/zdrav_client.py`](src/api/zdrav_client.py:56)  | 56     | `"https://zdrav.lenreg.ru"`              | Origin для HTTP-заголовков       |
| 3   | [`src/api/zdrav_client.py`](src/api/zdrav_client.py:266) | 266    | `"4"`                                    | ID района по умолчанию           |
| 4   | [`src/handlers/common.py`](src/handlers/common.py:784)   | 784    | `"https://zdrav.lenreg.ru/signup/free/"` | Ссылка для записи в уведомлениях |
| 5   | [`src/services/monitor.py`](src/services/monitor.py:213) | 213    | `"https://zdrav.lenreg.ru/signup/free/"` | Ссылка для записи в уведомлениях |

Также в `.env` и `.env.example` отсутствовали ключи для уже вынесенных в `Settings` параметров: `API_BASE_URL`, `REFERER_URL`, `CSRF_TOKEN`, `DEFAULT_CLINIC_ID`, `DEFAULT_BIRTHDAY`.

### Реализация

**Добавлены поля в [`src/config.py`](src/config.py):**

| Поле               | Значение по умолчанию                    | Описание                     |
| ------------------ | ---------------------------------------- | ---------------------------- |
| `DENTAL_CLINIC_ID` | `"272"`                                  | ID стоматологической клиники |
| `ORIGIN_URL`       | `"https://zdrav.lenreg.ru"`              | Origin для HTTP-заголовков   |
| `DISTRICT_ID`      | `"4"`                                    | ID района по умолчанию       |
| `SIGNUP_URL`       | `"https://zdrav.lenreg.ru/signup/free/"` | Публичная ссылка для записи  |

Добавлены соответствующие `CONFIG_KEY_*` константы и записи в `mapping` для синхронизации с БД.

**Обновлён [`.env`](.env):**

Добавлены ключи: `API_BASE_URL`, `REFERER_URL`, `ORIGIN_URL`, `CSRF_TOKEN`, `DISTRICT_ID`, `DEFAULT_CLINIC_ID`, `DENTAL_CLINIC_ID`, `DEFAULT_BIRTHDAY`, `SIGNUP_URL`.

**Обновлён [`.env.example`](.env.example):**

Добавлены те же ключи. Чувствительный `CSRF_TOKEN` — плейсхолдер `your_csrf_token_here`. Остальные — реальные значения по умолчанию.

**Заменены хардкоды в коде:**

| Файл                                                     | Было                                     | Стало                       |
| -------------------------------------------------------- | ---------------------------------------- | --------------------------- |
| [`src/keyboards/inline.py`](src/keyboards/inline.py:52)  | `_dental_clinic_id = "272"`              | `settings.DENTAL_CLINIC_ID` |
| [`src/api/zdrav_client.py`](src/api/zdrav_client.py:56)  | `"Origin": "https://zdrav.lenreg.ru"`    | `settings.ORIGIN_URL`       |
| [`src/api/zdrav_client.py`](src/api/zdrav_client.py:266) | `district_id: str = "4"`                 | `settings.DISTRICT_ID`      |
| [`src/handlers/common.py`](src/handlers/common.py:784)   | `"https://zdrav.lenreg.ru/signup/free/"` | `settings.SIGNUP_URL`       |
| [`src/services/monitor.py`](src/services/monitor.py:213) | `"https://zdrav.lenreg.ru/signup/free/"` | `settings.SIGNUP_URL`       |

### Изменённые файлы

| Файл                                                       | Действие                                                       |
| ---------------------------------------------------------- | -------------------------------------------------------------- |
| [`src/config.py`](src/config.py)                           | Изменён (+4 поля, +4 CONFIG_KEY, +4 записи в mapping)          |
| [`.env`](.env)                                             | Изменён (+9 ключей)                                            |
| [`.env.example`](.env.example)                             | Изменён (+9 ключей)                                            |
| [`src/keyboards/inline.py`](src/keyboards/inline.py)       | Изменён (хардкод → settings.DENTAL_CLINIC_ID)                  |
| [`src/api/zdrav_client.py`](src/api/zdrav_client.py)       | Изменён (хардкоды → settings.ORIGIN_URL, settings.DISTRICT_ID) |
| [`src/handlers/common.py`](src/handlers/common.py)         | Изменён (хардкод → settings.SIGNUP_URL)                        |
| [`src/services/monitor.py`](src/services/monitor.py)       | Изменён (хардкод → settings.SIGNUP_URL)                        |
| [`docs/agents/AGENT_TASKS.md`](docs/agents/AGENT_TASKS.md) | Изменён (удалена строка T-HARDCODE-IDS)                        |

### Результаты проверок

| Инструмент   | Результат               |
| ------------ | ----------------------- |
| `ruff check` | ✅ All checks passed!   |
| `pytest`     | ✅ 179 passed, 0 failed |

---

## 2026-05-19 (T-METRICS — Установка prometheus-client в виртуальное окружение)

### Задача

Исправление `ModuleNotFoundError: No module named 'prometheus_client'` — пакет был добавлен в `requirements.txt` задачей T-METRICS, но не установлен в виртуальное окружение.

### Выполненные шаги

1. Установлен `prometheus-client==0.25.0` в `.venv` через `pip install`.
2. Проверен импорт: `from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, generate_latest` — успешно.
3. Запущены тесты — все 179 passed.

### Результаты проверок

| Инструмент | Результат               |
| ---------- | ----------------------- |
| `pytest`   | ✅ 179 passed, 0 failed |

---

## 2026-05-19 (Исправление mypy-ошибок в src/services/metrics.py)

### Задача

Устранение 4 неиспользуемых `# type: ignore[attr-defined]` комментариев в [`src/services/metrics.py`](src/services/metrics.py:97,110,121,132) и проверка наличия поля `last_check_duration` в [`src/services/healthcheck.py`](src/services/healthcheck.py:42).

### Выполненные шаги

1. Прочитан [`src/services/metrics.py`](src/services/metrics.py) — обнаружено 4 неиспользуемых `# type: ignore[attr-defined]` на строках 97, 110, 121, 132.
2. Прочитан [`src/services/healthcheck.py`](src/services/healthcheck.py) — поле `last_check_duration: float = 0.0` уже присутствует в `HealthMetrics` на строке 42.
3. Удалены 4 комментария `# type: ignore[attr-defined]` из [`src/services/metrics.py`](src/services/metrics.py:97,110,121,132) — оставлены только `# noqa: SLF001`.
4. Запущен `ruff check src` — 0 ошибок.
5. Запущен `mypy src` — 0 ошибок.
6. Запущен `pytest` — exit code 0 (все тесты пройдены).
7. Временные файлы проверок удалены.

### Изменённые файлы

| Файл                                                   | Действие                 |
| ------------------------------------------------------ | ------------------------ |
| [`src/services/metrics.py`](src/services/metrics.py:1) | Удалены 4 `type: ignore` |

### Результаты проверок

| Инструмент | Результат             |
| ---------- | --------------------- |
| `ruff`     | ✅ All checks passed! |
| `mypy`     | ✅ Success: no issues |
| `pytest`   | ✅ All tests passed   |

---

## 2026-05-19 (T-API-VERSIONING — Версионирование API-эндпоинтов)

### Задача

Добавлен механизм версионирования API-эндпоинтов `zdrav.lenreg.ru`: валидация схемы ответов через Pydantic-модели, заголовок `X-Client-Version`, настройки в config.

### Выполненные шаги

1. Прочитаны [`src/api/zdrav_client.py`](src/api/zdrav_client.py), [`src/api/models.py`](src/api/models.py), [`src/config.py`](src/config.py) — изучена текущая архитектура API-клиента.
2. Добавлены настройки в [`src/config.py`](src/config.py):
   - `API_VERSION: str = "1.0.0"` — версия API-клиента
   - `API_VALIDATE_RESPONSES: bool = True` — флаг включения/выключения валидации
   - Константы `CONFIG_KEY_API_VERSION` и `CONFIG_KEY_API_VALIDATE_RESPONSES`
   - Оба ключа добавлены в mapping для синхронизации с БД
3. Обновлён [`src/api/zdrav_client.py`](src/api/zdrav_client.py):
   - В `_get_headers()` добавлен заголовок `X-Client-Version: settings.API_VERSION`
   - Создан метод `_validate_response()` с детальным логированием при `ValidationError` (эндпоинт, поле, ожидаемый тип, фактическое значение, URL)
   - Все 5 эндпоинтов (`check_patient`, `speciality_list`, `doctor_list`, `appointment_list`, `clinic_list`) используют `_validate_response()` вместо прямого `model_validate()`
   - Использован `TypeVar` для сохранения типа Pydantic-модели в возврате `_validate_response()`
4. Обновлён [`.env.example`](.env.example) — добавлены `API_VERSION` и `API_VALIDATE_RESPONSES`
5. Запущены проверки:
   - `ruff check src` — ✅ All checks passed
   - `mypy src` — ✅ Success: no issues found
   - `pytest` — ✅ 179 passed, 0 failed

### Изменённые файлы

| Файл                                                       | Действие                                     |
| ---------------------------------------------------------- | -------------------------------------------- |
| [`src/config.py`](src/config.py)                           | +`API_VERSION`, `API_VALIDATE_RESPONSES`     |
| [`src/api/zdrav_client.py`](src/api/zdrav_client.py)       | +`_validate_response()`, +`X-Client-Version` |
| [`.env.example`](.env.example)                             | +`API_VERSION`, `API_VALIDATE_RESPONSES`     |
| [`docs/agents/AGENT_TASKS.md`](docs/agents/AGENT_TASKS.md) | Удалена задача T-API-VERSIONING              |

### Результаты проверок

| Инструмент | Результат               |
| ---------- | ----------------------- |
| `ruff`     | ✅ All checks passed!   |
| `mypy`     | ✅ Success: no issues   |
| `pytest`   | ✅ 179 passed, 0 failed |

---

## 2026-05-19 (T-README — Актуализация README.md)

### Задача

Обновлён [`README.md`](README.md) — главный файл документации проекта. Добавлены разделы Troubleshooting Guide, FAQ, полная таблица команд бота, архитектура, Docker-развёртывание.

### Выполненные шаги

1. Прочитаны [`README.md`](README.md), [`src/handlers/common.py`](src/handlers/common.py), [`src/handlers/registration.py`](src/handlers/registration.py), [`.env.example`](.env.example), [`docker-compose.yml`](docker-compose.yml), [`pyproject.toml`](pyproject.toml).
2. Написан новый [`README.md`](README.md) со структурой из 11 разделов:
   - Название и краткое описание
   - Функциональность (8 пунктов)
   - Команды бота (таблица `/start`, `/status` + интерактивные callback-действия)
   - Архитектура (схема модулей `src/`, таблица ключевых технологий)
   - Требования (Python 3.11+, Redis, прокси)
   - Быстрый старт (5 шагов: клонирование → `.env` → зависимости → Redis → запуск)
   - Docker-развёртывание (`docker compose up -d`)
   - Troubleshooting Guide (5 сценариев: бот не запускается, нет слотов, ошибки валидации API, Redis, SQLite блокировки)
   - FAQ (8 вопросов)
   - Разработка (тесты, линтинг, типизация, CI/CD)
   - Лицензия
3. Обновлён [`docs/agents/AGENT_TASKS.md`](docs/agents/AGENT_TASKS.md) — удалена задача T-README.
4. Перенесена предыдущая запись в [`docs/agents/SESSION_ARCHIVE.md`](docs/agents/SESSION_ARCHIVE.md).

### Изменённые файлы

| Файл                                                               | Действие                                       |
| ------------------------------------------------------------------ | ---------------------------------------------- |
| [`README.md`](README.md)                                           | Полностью переписан (31 → ~310 строк)          |
| [`docs/agents/AGENT_TASKS.md`](docs/agents/AGENT_TASKS.md)         | Удалена задача T-README                        |
| [`docs/agents/SESSION_LOG.md`](docs/agents/SESSION_LOG.md)         | Новая запись о T-README                        |
| [`docs/agents/SESSION_ARCHIVE.md`](docs/agents/SESSION_ARCHIVE.md) | Добавлена предыдущая запись (T-API-VERSIONING) |

### Результаты проверок

| Инструмент     | Результат                |
| -------------- | ------------------------ |
| `markdownlint` | Ожидается 0 errors       |
| `prettier`     | Ожидается форматирование |

---

## 2026-05-19 — Техдолг API + Экспорт данных

### Выполненные задачи

- **TD-API-001** — Кастомные исключения ZdravApiError/NetworkError/TimeoutError/ParseError. Создан [`src/api/exceptions.py`](src/api/exceptions.py), все методы `ZdravClient` используют цепочку конкретных except вместо голого `Exception`.
- **TD-API-002** — Кэширование статических заголовков. Вынесены в `self._base_headers` (инициализация в `__init__`), `_get_headers()` возвращает `{**self._base_headers, "User-Agent": ...}`.
- **TD-API-003** — Документирование контракта `check_slots()`. Добавлен Google-style docstring с описанием всех вариантов возврата (None / [] / ["DD.MM.YYYY", ...]).
- **TD-API-005** — Алиасы полей `SpecialityItem`. `NameSpesiality` → `specialty_name`, `IdSpesiality` → `specialty_id`, `FerIdSpesiality` → `fer_id_specialty` через `Field(alias=...)` с `populate_by_name=True`. Заменены строковые обращения в `handlers/common.py` и `doctor_discovery.py`.
- **F6** — Экспорт данных мониторинга в CSV/JSON. Создан [`src/services/export.py`](src/services/export.py), команда `/export` в [`src/handlers/common.py`](src/handlers/common.py), таблица `monitoring_log` (миграция v6), тесты в [`tests/test_export.py`](tests/test_export.py).

### Изменённые файлы

- [`src/api/exceptions.py`](src/api/exceptions.py) — новый файл
- [`src/api/zdrav_client.py`](src/api/zdrav_client.py) — кастомные исключения, кэш заголовков, docstring
- [`src/api/models.py`](src/api/models.py) — алиасы полей SpecialityItem
- [`src/api/__init__.py`](src/api/__init__.py) — экспорт исключений
- [`src/services/export.py`](src/services/export.py) — новый файл
- [`src/services/__init__.py`](src/services/__init__.py) — экспорт функций
- [`src/services/monitor.py`](src/services/monitor.py) — запись в monitoring_log
- [`src/services/doctor_discovery.py`](src/services/doctor_discovery.py) — атрибутный доступ к SpecialityItem
- [`src/database/database.py`](src/database/database.py) — методы monitoring_log
- [`src/database/manager.py`](src/database/manager.py) — прокси-методы monitoring_log
- [`src/database/migrations.py`](src/database/migrations.py) — миграция v6
- [`src/handlers/common.py`](src/handlers/common.py) — команда /export, атрибутный доступ
- [`tests/test_export.py`](tests/test_export.py) — новый файл

---

## 2026-05-19 — Сужение `except Exception` в `migrate_v2_clinics_columns()`

### Выполненные задачи

- Добавлен `import sqlite3` в [`src/database/migrations.py`](src/database/migrations.py:11).
- В функции `migrate_v2_clinics_columns()` заменён `except Exception` на `except sqlite3.OperationalError` ([`src/database/migrations.py:90`](src/database/migrations.py:90)).

### Обоснование

Историческая миграция v2 добавляет колонки в таблицу `clinics` через `ALTER TABLE ADD COLUMN`. Для новых БД колонки уже существуют (созданы миграцией v1), поэтому при повторном выполнении `ALTER` выбрасывается `sqlite3.OperationalError`. Сужение типа перехватываемого исключения предотвращает проглатывание других потенциальных ошибок.

### Изменённые файлы

- [`src/database/migrations.py`](src/database/migrations.py) — добавлен `import sqlite3`, заменён `except Exception` → `except sqlite3.OperationalError`

---

## 2026-05-19 — Консолидация миграций + исправление TD-DB-001

### Выполненные задачи

- **migrations.py — дополнение v1:** В `migrate_v1_initial_schema()` в `CREATE TABLE IF NOT EXISTS clinics` добавлены 3 колонки: `city`, `discovery_patient_adult`, `discovery_patient_child` ([`src/database/migrations.py:33`](src/database/migrations.py:33)).
- **migrations.py — удаление v2:** Удалена функция `migrate_v2_clinics_columns()` — её логика (ALTER TABLE) теперь избыточна, т.к. колонки создаются в v1.
- **migrations.py — удаление v5:** Удалена функция `migrate_v5_seed_new_config_keys()` — полностью дублируется вызовом `seed_config_from_defaults()` в `main.py`.
- **migrations.py — очистка импортов:** Удалён `import sqlite3` (больше не используется в файле).
- **migrations.py — список MIGRATIONS:** Удалены записи `(2, migrate_v2_clinics_columns)` и `(5, migrate_v5_seed_new_config_keys)`. Актуальный список: `v1, v6`.
- **database.py — TD-DB-001:** В `seed_specialty_aliases_from_fallback()` и `seed_config_from_defaults()` заменён `logger.warning` → `logger.error` в блоках `except Exception` ([`src/database/database.py:628`](src/database/database.py:628), [`src/database/database.py:676`](src/database/database.py:676)).

### Обоснование

v1 не содержала колонки `city`, `discovery_patient_adult`, `discovery_patient_child` — они добавлялись через `ALTER TABLE` в v2. После дополнения v1 этими колонками v2 становится избыточной. v5 (`INSERT OR IGNORE INTO config`) полностью дублируется вызовом `seed_config_from_defaults()` в `main.py`, который содержит больше ключей. TD-DB-001: обе функции сидирования используют `try/except Exception: logger.warning`, из-за чего ошибки незаметны — заменено на `logger.error`.

### Изменённые файлы

- [`src/database/migrations.py`](src/database/migrations.py) — дополнена v1 (3 колонки), удалены v2, v5, `import sqlite3`, обновлён список MIGRATIONS
- [`src/database/database.py`](src/database/database.py) — `logger.warning` → `logger.error` в двух seed-функциях

---

## 2026-05-19 — Аудит TECH_DEBT.md + консолидация миграций + исправление TD-DB-001

### Выполненные задачи

- **Аудит TECH_DEBT.md** — проверены 7 записей TD-DB-001..007 в [`src/database/database.py`](src/database/database.py), [`src/database/manager.py`](src/database/manager.py), [`src/database/migrations.py`](src/database/migrations.py).

- **TD-DB-006 (миграции):** Сужен `except Exception` → `except sqlite3.OperationalError` в `migrate_v2_clinics_columns()`. Позже функция удалена полностью.

- **Анализ системы миграций:** Установлено, что v1 не содержит 3 колонки (`city`, `discovery_patient_adult`, `discovery_patient_child`), v2 избыточна после дополнения v1, v5 дублируется `seed_config_from_defaults()`, v3/v4 уже удалены.

- **Консолидация миграций** в [`src/database/migrations.py`](src/database/migrations.py):
  - `migrate_v1_initial_schema()`: добавлены колонки `city`, `discovery_patient_adult`, `discovery_patient_child` в `CREATE TABLE clinics`
  - Удалены функции `migrate_v2_clinics_columns()` и `migrate_v5_seed_new_config_keys()`
  - Удалён `import sqlite3`
  - Список MIGRATIONS: v1, v6

- **TD-DB-001** в [`src/database/database.py`](src/database/database.py): `logger.warning` → `logger.error` в `seed_specialty_aliases_from_fallback()` и `seed_config_from_defaults()`.

- **Обновление [`docs/agents/TECH_DEBT.md`](docs/agents/TECH_DEBT.md):**
  - Удалены TD-DB-001 (исправлено), TD-DB-002 (не баг), TD-DB-003 (не баг), TD-DB-004 (не баг), TD-DB-006 (исправлено), TD-DB-007 (исправлено)
  - Обновлена TD-DB-005: строки и приоритет

### Обоснование

Аудит TECH_DEBT.md выявил, что из 7 записей TD-DB-001..007 три были реальными багами (TD-DB-001, TD-DB-006, TD-DB-007), три — не багами, а штатным поведением (TD-DB-002, TD-DB-003, TD-DB-004), и одна (TD-DB-005) — действующая. В ходе консолидации миграций v1 дополнена недостающими колонками, v2 и v5 удалены как избыточные.

### Изменённые файлы

- [`src/database/migrations.py`](src/database/migrations.py) — дополнена v1 (3 колонки), удалены v2, v5, `import sqlite3`, обновлён список MIGRATIONS
- [`src/database/database.py`](src/database/database.py) — `logger.warning` → `logger.error` в двух seed-функциях
- [`docs/agents/TECH_DEBT.md`](docs/agents/TECH_DEBT.md) — удалены 6 записей, обновлена TD-DB-005

---

## 2026-05-19 — TD-DB-005: удаление legacy-формата в `get_last_message_id()`

### Выполненные задачи

- **TD-DB-005** в [`src/database/manager.py`](src/database/manager.py:142): удалена проверка `isinstance(val, int)` из `get_last_message_id()`.
  - Функция теперь ожидает только `dict` в кэше (текущий формат).
  - Legacy-формат (`int`) больше не поддерживается.
  - Ruff check пройден успешно (0 errors).

### Изменённые файлы

- [`src/database/manager.py`](src/database/manager.py:148-152) — удалены строки 151-152 (legacy-проверка `isinstance(val, int)`).
- [`docs/agents/TECH_DEBT.md`](docs/agents/TECH_DEBT.md:19) — удалена запись TD-DB-005.

---

## 2026-05-19 — TD-HND-001/004/005/006: 4 пункта технического долга хендлеров

### Выполненные задачи

- **TD-HND-005** — подсказка про дефис для двойных фамилий в сообщении об ошибке валидации ФИО:
  - [`src/handlers/registration.py:39-46`](src/handlers/registration.py:39) — обновлён текст ошибки в `process_fio()`.
  - [`src/api/zdrav_client.py:133-143`](src/api/zdrav_client.py:133) — обновлён текст ошибки в `fetch_patient_id()`.

- **TD-HND-006** — двухэтапный поиск пациента по всем clinic_id в `process_bday()`:
  - [`src/handlers/registration.py:75-100`](src/handlers/registration.py:75) — добавлен перебор: DEFAULT_CLINIC_ID → пустая строка → все активные clinic_id из БД.
  - При первом успешном `p_id is not None` поиск прекращается.
  - Использует `db._db.get_active_clinic_ids()` для получения списка клиник.

- **TD-HND-004** — хелпер для унифицированного парсинга callback_data:
  - Создан новый файл [`src/handlers/callback_parser.py`](src/handlers/callback_parser.py) с функцией `_parse_callback_arg()`.
  - Применён в [`src/handlers/common.py:638`](src/handlers/common.py:638) (`select_clinic`) и [`src/handlers/common.py:853-854`](src/handlers/common.py:853) (`stop_patient_monitoring`).

- **TD-HND-001** — очистка глобального кэша `_user_clinic_city_idx`:
  - [`src/handlers/common.py:410-413`](src/handlers/common.py:410) — в `cmd_start()` удаляются все ключи пользователя.
  - [`src/handlers/common.py:463-467`](src/handlers/common.py:463) — в `back_to_main()` удаляются все ключи пользователя.

### Изменённые файлы

- [`src/handlers/registration.py`](src/handlers/registration.py:39-100) — TD-HND-005 (текст ошибки), TD-HND-006 (multi-clinic search).
- [`src/api/zdrav_client.py`](src/api/zdrav_client.py:133-143) — TD-HND-005 (текст ошибки).
- [`src/handlers/callback_parser.py`](src/handlers/callback_parser.py) — **новый файл** с `_parse_callback_arg()`.
- [`src/handlers/common.py`](src/handlers/common.py:11,638,853-854,410-413,463-467) — импорт хелпера, применение к двум хендлерам, очистка кэша.
- [`docs/agents/TECH_DEBT.md`](docs/agents/TECH_DEBT.md:19-24) — удалены записи TD-HND-001/004/005/006.

### Проверки

- Ruff check: 0 errors, all checks passed.

---

## 2026-05-19 — Исправление 3 ошибок mypy в common.py после TD-HND-004

### Выполненные задачи

- **mypy fix** — устранение несоответствия типов `str | None` vs `str` для `city_idx`:
  - [`src/handlers/callback_parser.py:13`](src/handlers/callback_parser.py:13) — сигнатура `_parse_callback_arg()` уже возвращает `str` (default: `str = "all"`, а не `str | None = None`). **Вариант A** был применён ранее — функция гарантированно возвращает `str`.
  - [`src/handlers/common.py:650`](src/handlers/common.py:650) — вызов `_parse_callback_arg(parts, 4, "all")` в `select_clinic()`.
  - [`src/handlers/common.py:866`](src/handlers/common.py:866) — вызов `_parse_callback_arg(parts, 4, "all")` в `stop_patient_monitoring()`.
  - Строки 665, 690, 909 — `city_idx` теперь гарантированно `str`, ошибок mypy нет.

### Изменённые файлы

- [`src/handlers/callback_parser.py`](src/handlers/callback_parser.py:13) — сигнатура уже исправлена (default: `str = "all"`).
- [`src/handlers/common.py`](src/handlers/common.py:650,866) — оба вызова уже передают `"all"` явно.

### Проверки

- mypy: `Success: no issues found in 2 source files`.
- Ruff check: `All checks passed!`.

---

## 2026-05-19 — Верификация исправления 3 ошибок mypy в common.py

### Выполненные задачи

- **Верификация mypy fix** — проверка, что 3 ошибки `str | None` vs `str` для `city_idx` устранены:
  - [`src/handlers/callback_parser.py:13`](src/handlers/callback_parser.py:13) — сигнатура `_parse_callback_arg()` возвращает `str` (default: `str = "all"`).
  - [`src/handlers/common.py:650`](src/handlers/common.py:650) — `city_idx = _parse_callback_arg(parts, 4, "all")` (тип `str`).
  - [`src/handlers/common.py:665`](src/handlers/common.py:665) — присвоение в `_user_clinic_city_idx` (ожидает `str`).
  - [`src/handlers/common.py:690`](src/handlers/common.py:690) — передача `city_idx` в `get_doctor_selection()` (ожидает `str`).
  - [`src/handlers/common.py:866`](src/handlers/common.py:866) — `city_idx = _parse_callback_arg(parts, 4, "all")` (тип `str`).
  - [`src/handlers/common.py:909`](src/handlers/common.py:909) — передача `city_idx` в `get_clinic_selection()` (ожидает `str`).

### Проверки

- mypy (весь `src/`): `Success: no issues found in 35 source files`.
- Ruff check: `All checks passed!`.
- Markdownlint: `0 errors`.
- Prettier: все файлы без изменений.

---

## 2026-05-19 — Коммит исправления RUF002 и добавления правил Ruff

### Выполненные задачи

- **Git commit** — закоммичены изменения в двух файлах:
  - [`src/handlers/callback_parser.py`](src/handlers/callback_parser.py:10) — восстановлен кириллический символ `с` → `со` в docstring, добавлен `# noqa: RUF002` на закрывающей кавычке.
  - [`pyproject.toml`](pyproject.toml:68) — в список правил Ruff добавлены `B`, `UP`, `SIM`, `RUF`.

### Результат

- Коммит `6971337` с сообщением: `fix: suppress RUF002 false positive for Cyrillic in docstring, enable additional Ruff rules`

---

## 2026-05-19 — Обновление сессионных логов согласно протоколу

### Выполненные задачи

- Перенесена предыдущая запись из [`SESSION_LOG.md`](docs/agents/SESSION_LOG.md) в [`SESSION_ARCHIVE.md`](docs/agents/SESSION_ARCHIVE.md)
- Создана новая запись о текущей сессии
- Проверен [`AGENT_TASKS.md`](docs/agents/AGENT_TASKS.md) — задачи, связанные с RUF002/callback_parser, отсутствуют, удаление не требуется
- Выполнена проверка markdownlint — 0 ошибок
- Выполнено форматирование через prettier

### Изменённые файлы

| Файл                                                               | Действие  |
| ------------------------------------------------------------------ | --------- |
| [`docs/agents/SESSION_LOG.md`](docs/agents/SESSION_LOG.md)         | Переписан |
| [`docs/agents/SESSION_ARCHIVE.md`](docs/agents/SESSION_ARCHIVE.md) | Изменён   |

### Результаты проверок

| Инструмент   | Результат   |
| ------------ | ----------- |
| markdownlint | ✅ 0 errors |
| prettier     | ✅ 0 errors |

---

## 2026-05-19 — Проектирование интернационализации (F4)

### Выполненные задачи

- Проведён полный аудит проекта: прочитаны [`ARCHITECTURE.md`](docs/ARCHITECTURE.md), [`config.py`](src/config.py:28), [`pyproject.toml`](pyproject.toml), [`openapi.yaml`](docs/openapi.yaml)
- Проанализированы все модули с пользовательскими строками
- Составлен каталог из **98 уникальных строк** по доменам (`bot` — 88, `data` — 10)
- Создан дизайн-документ [`docs/design/i18n_design.md`](docs/design/i18n_design.md)
- Обновлён [`AGENT_TASKS.md`](docs/agents/AGENT_TASKS.md) — F4 переведён в 🔄

### Изменённые файлы

| Файл                                                       | Действие  |
| ---------------------------------------------------------- | --------- |
| [`docs/design/i18n_design.md`](docs/design/i18n_design.md) | Создан    |
| [`docs/agents/SESSION_LOG.md`](docs/agents/SESSION_LOG.md) | Переписан |
| [`docs/agents/AGENT_TASKS.md`](docs/agents/AGENT_TASKS.md) | Изменён   |

### Результаты проверок

| Инструмент   | Результат                      |
| ------------ | ------------------------------ |
| markdownlint | ⚠️ Не запущен (architect mode) |
| prettier     | ⚠️ Не запущен (architect mode) |

---

## 2026-05-19 — Реализация интернационализации (F4) — Кодинг

### Выполненные задачи

- Реализован модуль [`src/i18n/__init__.py`](src/i18n/__init__.py):
  - Функция `setup_i18n(lang)` — инициализация gettext для доменов `bot` и `data`
  - Функция `_(msgid)` — основная gettext-обёртка
  - Функция `_n(msgid1, msgid2, n)` — плюрализация
  - Функция `_data(msgid)` — переводы домена `data`
  - Функция `load_json_data(filename)` — загрузка JSON-словарей с fallback
- Создана структура `locales/`:
  - `ru/LC_MESSAGES/bot.po` — 98 русских переводов
  - `ru/LC_MESSAGES/data.po` — 8 переводов (дни недели + "Прочее")
  - `en/LC_MESSAGES/bot.po` — английские переводы
  - `en/LC_MESSAGES/data.po` — английские переводы
  - `ru/data/specialty_aliases.json` — 55+ псевдонимов
  - `en/data/specialty_aliases.json` — английские псевдонимы
- Скомпилированы `.po` → `.mo` через `pybabel compile`
- Добавлен `BOT_LANGUAGE` в [`src/config.py`](src/config.py:132)
- Добавлен вызов `setup_i18n()` в [`src/main.py`](src/main.py:140)
- Заменены все пользовательские строки на `_()` в:
  - [`src/handlers/common.py`](src/handlers/common.py) — все сообщения, кнопки, статусы
  - [`src/handlers/registration.py`](src/handlers/registration.py) — FSM, валидации
  - [`src/keyboards/inline.py`](src/keyboards/inline.py) — тексты кнопок
  - [`src/middleware/ratelimit.py`](src/middleware/ratelimit.py:105) — rate limit toast
  - [`src/api/zdrav_client.py`](src/api/zdrav_client.py) — ошибки API
  - [`src/services/monitor.py`](src/services/monitor.py) — заголовки уведомлений
  - [`src/services/healthcheck.py`](src/services/healthcheck.py) — /status
  - [`src/services/export.py`](src/services/export.py) — заголовки CSV/JSON
  - [`src/database/database.py`](src/database/database.py:43) — "Прочее" → `_data()`
  - [`src/utils/helpers.py`](src/utils/helpers.py:14) — дни недели через `_data()`
- Исправлено shadowing `_` (переименованы unpacking variables `_` → `__`)
- Добавлен `babel` в [`pyproject.toml`](pyproject.toml:60) (dev-зависимость)
- Добавлен `BOT_LANGUAGE=ru` в [`.env.example`](.env.example:56)
- Добавлен `locales/**/*.mo` в [`.gitignore`](.gitignore:35)
- Обновлён [`tests/conftest.py`](tests/conftest.py:18) — autouse-фикстура `_init_i18n`

### Изменённые файлы

| Файл                                     | Действие |
| ---------------------------------------- | -------- |
| `src/i18n/__init__.py`                   | Создан   |
| `locales/ru/LC_MESSAGES/bot.po`          | Создан   |
| `locales/ru/LC_MESSAGES/data.po`         | Создан   |
| `locales/en/LC_MESSAGES/bot.po`          | Создан   |
| `locales/en/LC_MESSAGES/data.po`         | Создан   |
| `locales/ru/data/specialty_aliases.json` | Создан   |
| `locales/en/data/specialty_aliases.json` | Создан   |
| `src/config.py`                          | Изменён  |
| `src/main.py`                            | Изменён  |
| `src/handlers/common.py`                 | Изменён  |
| `src/handlers/registration.py`           | Изменён  |
| `src/keyboards/inline.py`                | Изменён  |
| `src/middleware/ratelimit.py`            | Изменён  |
| `src/api/zdrav_client.py`                | Изменён  |
| `src/services/monitor.py`                | Изменён  |
| `src/services/healthcheck.py`            | Изменён  |
| `src/services/export.py`                 | Изменён  |
| `src/utils/helpers.py`                   | Изменён  |
| `src/database/database.py`               | Изменён  |
| `pyproject.toml`                         | Изменён  |
| `.env.example`                           | Изменён  |
| `.gitignore`                             | Изменён  |
| `tests/conftest.py`                      | Изменён  |

### Результаты проверок

| Инструмент                 | Результат                                |
| -------------------------- | ---------------------------------------- |
| ruff check src/            | 54 предупреждений (все предсуществующие) |
| pytest (релевантные тесты) | 147 passed ✅                            |
| markdownlint               | ⏳ Проверить                             |
| prettier                   | ⏳ Проверить                             |

---

## 2026-05-19 — Проектирование детектора изменений API (F8) — Architect

### Выполненные задачи

- Собран контекст проекта:
  - [`ARCHITECTURE.md`](docs/ARCHITECTURE.md) — дерево директорий, зоны ответственности, граф зависимостей
  - [`src/api/models.py`](src/api/models.py) — 12 Pydantic-моделей для валидации ответов API
  - [`src/api/zdrav_client.py`](src/api/zdrav_client.py:87) — текущий механизм `_validate_response()`
  - [`src/services/error_notifier.py`](src/services/error_notifier.py) — NTFY + Sentry (singleton)
  - [`src/services/metrics.py`](src/services/metrics.py) — Prometheus-метрики (Gauge + Counter)
  - [`src/config.py`](src/config.py) — pydantic-settings с двухуровневым переопределением
  - [`src/main.py`](src/main.py) — сборка бота, запуск фоновых asyncio-задач
  - [`src/services/healthcheck.py`](src/services/healthcheck.py) — пример фонового цикла
  - [`docs/openapi.yaml`](docs/openapi.yaml) — SSOT архитектуры данных
  - [`docs/design/i18n_design.md`](docs/design/i18n_design.md) — образец формата дизайн-документа
  - [`pyproject.toml`](pyproject.toml) — зависимости проекта (без deepdiff)
- Создан дизайн-документ [`docs/design/api_change_detector_design.md`](docs/design/api_change_detector_design.md):
  - Архитектурная схема (Mermaid): компонентная диаграмма + sequence diagram
  - Компонент 1: скрипт `scripts/generate_api_schemas.py` — генерация эталонных JSON Schema
  - Компонент 2: модуль `src/services/schema_watcher.py` — загрузка, сравнение, цикл проверки
  - Компонент 3: фоновый цикл `schema_check_loop` — интеграция в `main.py`
  - Компонент 4: метод `notify_schema_change()` в `ErrorNotifier` (tag: `api_schema_change`)
  - Компонент 5: метрики `zdrav_api_schema_drift` (Gauge) + `zdrav_api_schema_changes_total` (Counter)
  - Компонент 6: конфигурация `SCHEMA_CHECK_INTERVAL`, `SCHEMA_CHECK_ENABLED`
  - Алгоритм сравнения схем: рекурсивный diff (чистый Python, без deepdiff)
  - План тестирования: 20 тестов (14 модульных + 6 интеграционных)
  - Обработка ошибок и граничные случаи (9 сценариев)

### Изменённые файлы

| Файл                                        | Действие |
| ------------------------------------------- | -------- |
| `docs/design/api_change_detector_design.md` | Создан   |
| `docs/agents/SESSION_LOG.md`                | Изменён  |
| `docs/agents/SESSION_ARCHIVE.md`            | Изменён  |

### Результаты проверок

| Инструмент   | Результат                 |
| ------------ | ------------------------- |
| markdownlint | ⏳ Проверить (после diff) |
| prettier     | ⏳ Проверить (после diff) |

---

## 2026-05-19 — Проектирование веб-дашборда (F5) — Architect

### Выполненные задачи

1. **Сбор информации:** Проанализированы ключевые файлы проекта:
   - [`ARCHITECTURE.md`](docs/ARCHITECTURE.md) — дерево директорий, зоны ответственности, граф зависимостей
   - [`main.py`](src/main.py) — asyncio-процесс, фоновые задачи, graceful shutdown
   - [`config.py`](src/config.py) — pydantic-settings, `load_config_from_db()`
   - [`database.py`](src/database/database.py) — SQLite-движок, CRUD, `monitoring_log`, `clinics`, `doctors`
   - [`manager.py`](src/database/manager.py) — `DatabaseManager` с in-memory кэшем и `asyncio.Lock`
   - [`healthcheck.py`](src/services/healthcheck.py) — `HealthMetrics` dataclass, `_metrics_lock`
   - [`monitor.py`](src/services/monitor.py) — цикл мониторинга, классификация слотов, `monitoring_log`
   - [`metrics.py`](src/services/metrics.py) — `PrometheusMetrics` (Gauge/Counter)
   - [`schema_watcher.py`](src/services/schema_watcher.py) — детектор изменений схем API (F8)
   - [`migrations.py`](src/database/migrations.py) — схема БД (таблицы `monitoring_log`, `clinics`, `doctors`, etc.)
   - [`pyproject.toml`](pyproject.toml) — зависимости, конфигурация ruff/mypy
   - [`.env.example`](.env.example) — существующие ключи конфигурации

2. **Уточнение требований:** Согласованы решения:
   - Аутентификация: `X-API-Key` заголовок (статический ключ из `.env`)
   - Порт дашборда: 8080
   - Prometheus `/metrics`: остаётся на отдельном aiohttp-сервере на порту 9090

3. **Создан дизайн-документ** [`docs/design/web_dashboard_design.md`](docs/design/web_dashboard_design.md):
   - **Раздел 1:** Архитектурная схема (2 Mermaid-диаграммы) — встраивание FastAPI в asyncio-процесс, поток запроса
   - **Раздел 2:** Структура пакета `src/web/` (7 модулей: `app.py`, `auth.py`, `dependencies.py`, `routers/pages.py`, `routers/api.py`, `templates/`, `static/`)
   - **Раздел 3:** Детальное описание каждого компонента с сигнатурами и примерами кода
   - **Раздел 4:** Дизайн всех 6 страниц (текстовые wireframe'ы: сводка, пользователи, лог, клиники, API-статус, детали пользователя)
   - **Раздел 5:** Схема БД-запросов — 3 новых метода (`get_all_monitoring_logs`, `get_all_monitoring_logs_count`, `get_clinic_doctor_count`, `get_total_stats`) с SQL
   - **Раздел 6:** API-контракты — 7 JSON-эндпоинтов с полными схемами ответов
   - **Раздел 7:** Интеграция с существующей архитектурой:
     - Изменения в [`main.py`](src/main.py) — запуск `run_dashboard()` как `asyncio.Task`
     - Изменения в [`config.py`](src/config.py) — 3 новых ключа (`WEB_DASHBOARD_ENABLED`, `WEB_DASHBOARD_PORT`, `WEB_DASHBOARD_API_KEY`)
     - Изменения в [`.env.example`](.env.example) — блок Web Dashboard
     - Новые зависимости: `fastapi`, `uvicorn[standard]`, `jinja2`
     - Обновление `ARCHITECTURE.md` и `openapi.yaml`
   - **Раздел 8:** План тестирования — 5 тестовых файлов, 2 категории (unit + integration)
   - **Раздел 9:** Сводка конфигурационных ключей
   - **Раздел 10:** Ограничения и допущения
   - **Раздел 11:** Сравнение с `/status` командой бота

### Изменённые файлы

| Файл                                  | Действие |
| ------------------------------------- | -------- |
| `docs/design/web_dashboard_design.md` | Создан   |
| `docs/agents/SESSION_LOG.md`          | Изменён  |
| `docs/agents/SESSION_ARCHIVE.md`      | Изменён  |
| `docs/agents/AGENT_TASKS.md`          | Изменён  |

### Результаты проверок

| Инструмент   | Результат                |
| ------------ | ------------------------ |
| markdownlint | Ожидается (после записи) |
| prettier     | Ожидается (после записи) |

---

## 2026-05-19 — Реализация веб-дашборда мониторинга (F5) — Code

### Выполненные задачи

1. **Шаг 1: Зависимости** — Добавлены `fastapi`, `uvicorn[standard]`, `jinja2` в [`pyproject.toml`](pyproject.toml:23) и [`requirements.txt`](requirements.txt:1).

2. **Шаг 2: Конфигурация** — В [`src/config.py`](src/config.py) добавлены:
   - Поля `WEB_DASHBOARD_ENABLED` (bool, `True`), `WEB_DASHBOARD_PORT` (int, `8080`), `WEB_DASHBOARD_API_KEY` (str, `""`)
   - Константы `CONFIG_KEY_WEB_DASHBOARD_ENABLED`, `CONFIG_KEY_WEB_DASHBOARD_PORT`
   - Маппинг в `load_config_from_db()`
   - Секция в [`.env.example`](.env.example)

3. **Шаг 3: Новые методы БД** — В [`src/database/database.py`](src/database/database.py) и [`src/database/manager.py`](src/database/manager.py) добавлены:
   - `get_total_stats()` — агрегированная статистика (users, patients, monitored doctors)
   - `get_all_monitoring_logs()` — лог с пагинацией и фильтрацией (uid, status)
   - `get_all_monitoring_logs_count()` — количество записей для пагинации
   - `get_clinic_doctor_count()` — количество врачей в клинике

4. **Шаг 4: Пакет `src/web/`** — Созданы 15 файлов:
   - `__init__.py` — пустой
   - `auth.py` — `APIKeyMiddleware` (проверка X-API-Key, отключается при пустом ключе)
   - `dependencies.py` — `get_db()`, `get_health_metrics()`, `get_prometheus_metrics()`
   - `app.py` — `create_app()` фабрика FastAPI с lifespan, статикой, шаблонами, роутерами
   - `routers/__init__.py` — пустой
   - `routers/pages.py` — 6 HTML-эндпоинтов (сводка, пользователи, детали, логи, клиники, API-статус)
   - `routers/api.py` — 7 JSON-эндпоинтов (`/api/dashboard/*` + `/api/health`)
   - `templates/base.html` — базовый шаблон (навигация, футер, тёмная тема)
   - `templates/summary.html` — сводка: uptime, статус API, фоновые задачи, последние алерты
   - `templates/users.html` — таблица пользователей
   - `templates/user_detail.html` — детали пользователя (пациенты, врачи)
   - `templates/logs.html` — лог с пагинацией и фильтрацией
   - `templates/clinics.html` — справочник клиник
   - `templates/api_status.html` — состояние API
   - `static/dashboard.css` — минимальный CSS в тёмной теме (zebra striping, бейджи, таблицы)

5. **Шаг 5: Интеграция в `main.py`** — Добавлены:
   - `import uvicorn`
   - `from src.services.healthcheck import metrics as health_metrics`
   - `run_dashboard()` — запускает uvicorn.Server программно
   - В `main()`: запуск дашборда как `asyncio.Task` после Prometheus-сервера
   - В `finally`: остановка дашборда через `task.cancel()`

6. **Шаг 6: Проверки**:
   - Ruff: 0 ошибок на новых/изменённых файлах
   - Pytest: 31 passed, 0 failed
   - Markdownlint: предсуществующие ошибки в дизайн-документах
   - Prettier: выполнено

### Изменённые файлы

| Файл                                 | Действие |
| ------------------------------------ | -------- |
| `pyproject.toml`                     | Изменён  |
| `requirements.txt`                   | Изменён  |
| `src/config.py`                      | Изменён  |
| `.env.example`                       | Изменён  |
| `src/database/database.py`           | Изменён  |
| `src/database/manager.py`            | Изменён  |
| `src/main.py`                        | Изменён  |
| `src/web/__init__.py`                | Создан   |
| `src/web/auth.py`                    | Создан   |
| `src/web/dependencies.py`            | Создан   |
| `src/web/app.py`                     | Создан   |
| `src/web/routers/__init__.py`        | Создан   |
| `src/web/routers/pages.py`           | Создан   |
| `src/web/routers/api.py`             | Создан   |
| `src/web/templates/base.html`        | Создан   |
| `src/web/templates/summary.html`     | Создан   |
| `src/web/templates/users.html`       | Создан   |
| `src/web/templates/user_detail.html` | Создан   |
| `src/web/templates/logs.html`        | Создан   |
| `src/web/templates/clinics.html`     | Создан   |
| `src/web/templates/api_status.html`  | Создан   |
| `src/web/static/dashboard.css`       | Создан   |
| `tests/test_doctor_discovery.py`     | Изменён  |
| `docs/agents/SESSION_LOG.md`         | Изменён  |
| `docs/agents/SESSION_ARCHIVE.md`     | Изменён  |
| `docs/agents/AGENT_TASKS.md`         | Изменён  |

---

## 2026-05-19 — Исправление ошибки привязки порта веб-дашборда (F5) — Code

### Выполненные задачи

#### Исправление ошибки bind порта веб-дашборда

- **Проблема:** При запуске бота ошибка `[WinError 10013] — сделана попытка доступа к сокету методом, запрещенным правами доступа` на порту 8080 роняла весь бот.
- **Решение:**
  - Создана функция [`_run_dashboard_safe()`](src/main.py:162) с перебором портов (основной → 8081 → 8082 → 8083) при ошибке привязки.
  - Функция [`run_dashboard()`](src/main.py:196) обёрнута в безопасный запуск через `_run_dashboard_safe()`.
  - Из [`main()`](src/main.py:348) убран преждевременный `logger.info` — результат теперь логируется внутри `run_dashboard()`.

### Изменённые файлы

- `src/main.py` — `_run_dashboard_safe()`, обновлённая `run_dashboard()`, изменён блок запуска дашборда

### Результаты проверок

| Инструмент | Результат          |
| ---------- | ------------------ |
| ruff check | 0 errors           |
| pytest     | Все тесты пройдены |

---

## 2026-05-19 — Диагностика и исправление проблем запуска бота

### Выполненные задачи

#### Проблема 1: `%d` не интерполирован в логах (loguru использует `{}`, а не C-style)

- [`src/main.py:128`](src/main.py:128) — `%dс` → `{}с`
- [`src/services/cleanup.py:22`](src/services/cleanup.py:22) — `TTL=%d с, интервал=%d с` → `TTL={} с, интервал={} с`
- [`src/services/cleanup.py:80`](src/services/cleanup.py:80) — `msg_id=%d ... возраст=%.1fч` → `msg_id={} ... возраст={:.1f}ч`
- [`src/services/cleanup.py:91`](src/services/cleanup.py:91) — `%d сообщений` → `{} сообщений`

#### Проблема 2: Веб-дашборд не логирует запуск

[`_run_dashboard_safe()`](src/main.py:162) вызывал `await server.serve()`, который никогда не возвращается при успешном запуске, поэтому строка логирования `"Веб-дашборд запущен на порту {result}"` в [`run_dashboard()`](src/main.py:197) никогда не достигалась. Логирование перенесено в `_run_dashboard_safe()` ДО `server.serve()`.

#### Проблема 3: Бот сразу останавливается (корневая причина — uvicorn в том же event loop)

**Диагностика:** [`uvicorn.Server.serve()`](src/main.py:162) при запуске в том же asyncio event loop, что и aiogram, переконфигурирует event loop (вызывает `config.setup_event_loop()`), что на Windows (ProactorEventLoop/IOCP) приводит к немедленной остановке aiogram polling.

**Исправление:** Uvicorn теперь запускается в отдельном daemon-потоке через [`_run_uvicorn_sync()`](src/main.py:162) с собственным event loop. [`_run_dashboard_safe()`](src/main.py:176) запускает поток, ждёт 0.8с и проверяет `thread.is_alive()` для подтверждения успешного старта.

### Изменённые файлы

- [`src/main.py`](src/main.py) — исправлены форматные строки (loguru), переписан запуск uvicorn в отдельном потоке
- [`src/services/cleanup.py`](src/services/cleanup.py) — исправлены форматные строки (loguru)

### Результаты проверок

| Инструмент | Результат                                              |
| ---------- | ------------------------------------------------------ |
| Ruff       | 15 предсуществующих замечаний (не связаны с правками)  |
| Pytest     | 185 passed, 1666 warnings (pytest_asyncio deprecation) |

---

## 2026-05-19 — Исправление краха процесса при ошибке порта веб-дашборда

### Выполненные задачи

#### Проблема: bind порта 8080 убивает весь процесс

**Диагностика:** Uvicorn при ошибке `[WinError 10013]` вызывает `sys.exit()` внутри `server.run()`, что завершает весь Python-процесс, несмотря на daemon-поток.

**Исправление:** Полная изоляция ошибок запуска uvicorn:

1. [`_run_uvicorn_sync()`](src/main.py:163) — переписан: принимает `(app, host, port)` вместо `config`; запускает uvicorn во внутреннем daemon-потоке с `try/except`, перехватывающим все исключения; возвращает `bool` (True если сервер успешно стартовал).
2. [`_run_dashboard_safe()`](src/main.py:192) — переписан на `asyncio.to_thread()` для запуска `_run_uvicorn_sync()` без блокировки event loop; логирует каждую попытку порта.
3. Fallback-порты изменены с `[8081, 8082, 8083]` на `[8091, 8092, 8093]`.
4. Порт по умолчанию `WEB_DASHBOARD_PORT` изменён с 8080 на 8090.

### Изменённые файлы

- [`src/main.py`](src/main.py) — переписан `_run_uvicorn_sync()` и `_run_dashboard_safe()`, добавлен `import time`, изменены fallback-порты
- [`src/config.py`](src/config.py:148) — `WEB_DASHBOARD_PORT: 8080` → `8090`
- [`.env.example`](.env.example:101) — `WEB_DASHBOARD_PORT=8080` → `8090`
- [`.env`](.env:100) — `WEB_DASHBOARD_PORT=8080` → `8090`

### Результаты проверок

| Инструмент | Результат            |
| ---------- | -------------------- |
| Ruff       | All checks passed!   |
| Pytest     | 185 passed, 0 failed |

---

## 2026-05-19 — Исправление 500 ошибки веб-дашборда (Starlette 1.0.0 TemplateResponse)

### Выполненные задачи

#### Проблема: `GET /` возвращает 500 Internal Server Error

**Диагностика:**

1. Проанализирован [`logs/error.log`](logs/error.log) — обнаружен 404 (не 500), но без traceback.
2. Проверены 7 гипотез: методы `get_total_stats()`, `uptime_str()`, `api_health_str()`, Jinja2-шаблоны, auth middleware, конфликты маршрутов.
3. Изменён `log_level="error"` → `"info"` в [`_run_uvicorn_sync()`](src/main.py:176), добавлен `logger.exception` в `_serve()`.
4. Добавлен `try/except` с `logger.exception` в [`dashboard_summary()`](src/web/routers/pages.py:32-66).
5. После перезапуска получен traceback: `TypeError: cannot use 'tuple' as a dict key (unhashable type: 'dict')` в [`starlette/templating.py:148`](.venv/Lib/site-packages/starlette/templating.py:148).

**Корневая причина:** Установлен Starlette 1.0.0, в котором сигнатура `Jinja2Templates.TemplateResponse()` изменилась — добавлен обязательный первый параметр `request: Request`. Код вызывал старую сигнатуру `TemplateResponse(name, context)`, из-за чего `"summary.html"` попадал в `request`, а словарь контекста — в `name`. Jinja2 пытался использовать dict как имя шаблона.

**Исправление:** Во всех 7 вызовах `TemplateResponse` в [`pages.py`](src/web/routers/pages.py) добавлен `request` первым параметром, убран дублирующийся `"request": request` из контекста (Starlette 1.0.0 добавляет его автоматически).

### Изменённые файлы

- [`src/main.py`](src/main.py:176) — `log_level="error"` → `"info"`, добавлен `logger.exception` в `_serve()`
- [`src/web/routers/pages.py`](src/web/routers/pages.py) — добавлен `from loguru import logger`, `try/except` в `dashboard_summary()`, `request` первым параметром во все 7 вызовов `TemplateResponse`

### Результаты проверок

| Инструмент | Результат            |
| ---------- | -------------------- |
| Ruff check | All checks passed!   |
| Pytest     | 185 passed, 0 failed |

---

## 2026-05-19 — Убрана заглушка на странице API-статуса дашборда

### Выполненные задачи

#### Проблема: на странице `/api-status` отображается «требуется F8 schema_watcher»

**Диагностика:**

1. Прочитан [`src/web/routers/pages.py`](src/web/routers/pages.py:194) — `api_status()` содержит пустой блок `try/except` (строки 216-224), который не читает schema-метрики. `schema_status` и `schema_drift_details` всегда передаются как пустые `{}`.
2. Прочитан [`src/web/templates/api_status.html`](src/web/templates/api_status.html:95) — проверка `{% if schema_status %}` на пустой dict falsy, поэтому показывается заглушка.
3. Прочитан [`src/services/metrics.py`](src/services/metrics.py:197) — `PrometheusMetrics` имеет `set_schema_drift()` для записи в Gauge, но нет метода для чтения текущего состояния.
4. Прочитан [`src/services/schema_watcher.py`](src/services/schema_watcher.py:440) — `schema_check_loop` корректно вызывает `metrics.set_schema_drift()` при каждом цикле проверки.

**Исправления:**

1. В [`src/services/metrics.py`](src/services/metrics.py:68) добавлено поле `self._schema_status: dict[str, bool] = {}` для хранения состояния схем.
2. В [`src/services/metrics.py`](src/services/metrics.py:201) `set_schema_drift()` теперь сохраняет значение не только в Gauge, но и в `_schema_status[endpoint]`.
3. В [`src/services/metrics.py:209`](src/services/metrics.py:209) добавлен метод `get_schema_status() -> dict[str, bool]` — возвращает копию `_schema_status`.
4. В [`src/web/routers/pages.py:218`](src/web/routers/pages.py:218) пустой блок `try/except` заменён на вызов `pm.get_schema_status()`.
5. В [`src/web/templates/api_status.html:95-114`](src/web/templates/api_status.html:95) заглушка заменена на реальные бейджи: ✅ Совпадает / ⚠️ Расхождение.

### Изменённые файлы

- [`src/services/metrics.py`](src/services/metrics.py:68) — добавлен `_schema_status`, обновлён `set_schema_drift()`, добавлен `get_schema_status()`
- [`src/web/routers/pages.py`](src/web/routers/pages.py:218) — пустой try/except заменён на реальный вызов `pm.get_schema_status()`
- [`src/web/templates/api_status.html`](src/web/templates/api_status.html:95) — заглушка заменена на данные с бейджами

### Результаты проверок

| Инструмент | Результат            |
| ---------- | -------------------- |
| Ruff check | All checks passed!   |
| Pytest     | 185 passed, 0 failed |

---

## 2026-05-19 — Добавлен `.gitattributes` для подавления CRLF-предупреждений

### Выполненные задачи

#### Проблема: Git при коммите выдаёт 12 warnings вида `LF will be replaced by CRLF` для JSON-файлов в `docs/schemas/`

**Исправления:**

1. Создан [`.gitattributes`](.gitattributes:1) с правилом `*.json text eol=lf` — явное указание LF для всех JSON-файлов.
2. Выполнен `git add --renormalize docs/schemas/*.json` — применение нового атрибута к уже отслеживаемым файлам.
3. Выполнен коммит `chore: add .gitattributes — LF for JSON files`.

### Изменённые файлы

- [`.gitattributes`](.gitattributes:1) — создан, правило LF для JSON

### Результаты проверок

| Инструмент | Результат                                    |
| ---------- | -------------------------------------------- |
| git status | Working tree clean, 1 commit ahead of origin |

---

## 2026-05-19 — Замена `%s`/`%d` на `{}` в logger-вызовах loguru

### Выполненные задачи

1. Замена `%s`/`%d` на `{}` во всех вызовах `logger.info()`, `logger.error()`, `logger.warning()`, `logger.debug()` в 4 файлах.

### Изменённые файлы

- [`src/services/doctor_discovery.py:113`](../src/services/doctor_discovery.py:112) — `%s` → `{}`
- [`src/services/error_notifier.py:177`](../src/services/error_notifier.py:177) — `%s` → `{}`
- [`src/services/error_notifier.py:199`](../src/services/error_notifier.py:199) — `%s` → `{}`
- [`src/utils/logging.py:133`](../src/utils/logging.py:132) — `%s` → `{}`
- [`src/services/schema_watcher.py:216`](../src/services/schema_watcher.py:216) — `%s` → `{}`
- [`src/services/schema_watcher.py:225`](../src/services/schema_watcher.py:225) — `%s` → `{}`
- [`src/services/schema_watcher.py:227`](../src/services/schema_watcher.py:227) — `%d` → `{}`
- [`src/services/schema_watcher.py:252`](../src/services/schema_watcher.py:252) — `%s` → `{}`
- [`src/services/schema_watcher.py:257`](../src/services/schema_watcher.py:257) — `%s` → `{}`
- [`src/services/schema_watcher.py:266`](../src/services/schema_watcher.py:266) — `%s` → `{}`
- [`src/services/schema_watcher.py:272`](../src/services/schema_watcher.py:272) — `%s` → `{}`
- [`src/services/schema_watcher.py:284`](../src/services/schema_watcher.py:284) — `%s` → `{}`
- [`src/services/schema_watcher.py:384`](../src/services/schema_watcher.py:384) — `%s` → `{}`
- [`src/services/schema_watcher.py:414`](../src/services/schema_watcher.py:414) — `%d` → `{}`
- [`src/services/schema_watcher.py:426`](../src/services/schema_watcher.py:426) — `%s`/`%d` → `{}`
- [`src/services/schema_watcher.py:431`](../src/services/schema_watcher.py:431) — `%s` → `{}`
- [`src/services/schema_watcher.py:443`](../src/services/schema_watcher.py:443) — `%s` → `{}`
- [`src/services/schema_watcher.py:448`](../src/services/schema_watcher.py:448) — `%s` → `{}`
- [`src/services/schema_watcher.py:461`](../src/services/schema_watcher.py:461) — `%s` → `{}`

### Результаты проверок

| Инструмент                 | Результат              |
| -------------------------- | ---------------------- |
| `%s`/`%d` в logger-вызовах | 0 остаточных вхождений |

---

## 2026-05-19 — Диагностика и исправление `%s`/`%d` в loguru

### Выполненные задачи

1. Диагностирован баг: Loguru 0.7.3 не поддерживает `%s`/`%d`-форматирование при вызове `logger.info/error/warning/debug()` с позиционными аргументами. Все `%s`-плейсхолдеры в проекте выводились буквально, без подстановки аргументов.
2. Заменены все `%s` и `%d` на `{}` в вызовах `loguru.logger` в 4 файлах (см. ниже).
3. Финишная проверка `Select-String` подтвердила 0 остаточных вхождений `%s`/`%d` в logger-вызовах.

### Изменённые файлы

- [`src/services/doctor_discovery.py:113`](../src/services/doctor_discovery.py:113) — `%s` → `{}` (1 вызов)
- [`src/services/error_notifier.py:177,199`](../src/services/error_notifier.py:177) — `%s` → `{}` (2 вызова)
- [`src/services/schema_watcher.py`](../src/services/schema_watcher.py) — `%s`/`%d` → `{}` (15 вызовов)
- [`src/utils/logging.py:133`](../src/utils/logging.py:133) — `%s` → `{}` (1 вызов)

### Результаты тестов

Не запускались (изменения чисто строковые, не затрагивают логику).

---

## 2026-05-19 — Диагностика: запуск mypy для проверки типов

### Выполненные задачи

1. Проверена конфигурация [`[tool.mypy]`](../pyproject.toml:85) в `pyproject.toml`.
2. Запущен `python -m mypy src` с перенаправлением вывода в `.tmp_mypy_results.txt`.
3. Результаты проанализированы и классифицированы, временный файл удалён.
4. Исправления не производились — только диагностика.

### Результаты mypy

- **Проверено:** 44 исходных файла
- **Ошибок:** 11 (в 2 файлах)
- **Exit code:** 1

| Файл                                                    | Ошибок | Типы ошибок                                                |
| ------------------------------------------------------- | ------ | ---------------------------------------------------------- |
| [`src/i18n/__init__.py`](../src/i18n/__init__.py)       | 8      | `unused-ignore` (4), `assignment` (2), `no-any-return` (2) |
| [`src/web/dependencies.py`](../src/web/dependencies.py) | 3      | `no-any-return` (3)                                        |

### Результаты тестов

Не запускались (диагностика без изменений кода).

---

## 2026-05-19 — Исправление 22 ruff-ошибок

### Выполненные задачи

1. Исправлены 13 ошибок **E501** (line too long) в [`tests/test_monitor_full.py`](../tests/test_monitor_full.py) — длинные строки разбиты с обёрткой в `(` `)` и правильными отступами.
2. Исправлены 4 ошибки **RUF012** (mutable default) в [`tests/test_keyboards.py`](../tests/test_keyboards.py) — добавлена аннотация `ClassVar` для классовых атрибутов + импорт `from typing import ClassVar`.
3. Исправлены 2 ошибки **SIM115** (context manager) в [`src/services/export.py`](../src/services/export.py) — `NamedTemporaryFile` обёрнут в `with`-контекстный менеджер.
4. Исправлены 2 ошибки **B904** (raise ... from e) в [`src/utils/proxy_discovery.py`](../src/utils/proxy_discovery.py) — добавлено `from exc` / `from e` в `except`-блоках.
5. Исправлена 1 ошибка **SIM105** (try-except-pass) в [`src/services/cleanup.py`](../src/services/cleanup.py) — заменено на `with suppress(TelegramAPIError)`.

### Результаты проверок

- `ruff check src tests` — **0 ошибок**
- `pytest tests/ -v` — **185 passed, 0 failed**

---

## 2026-05-19 — TD-TST-001: Реорганизация структуры `tests/` — зеркалирование `src/`

### Выполненные задачи

1. Созданы поддиректории `tests/api/`, `tests/database/`, `tests/handlers/`, `tests/keyboards/`, `tests/services/`, `tests/utils/`.
2. В каждую поддиректорию добавлен пустой `__init__.py`.
3. Перемещены 10 тестовых файлов согласно таблице зеркалирования пакетов `src/`:
   - `tests/api/test_zdrav_client.py`
   - `tests/database/test_database_manager.py`
   - `tests/handlers/test_handlers_common.py`
   - `tests/handlers/test_handlers_registration.py`
   - `tests/keyboards/test_keyboards.py`
   - `tests/services/test_doctor_discovery.py`
   - `tests/services/test_export.py`
   - `tests/services/test_monitor_classify.py`
   - `tests/services/test_monitor_full.py`
   - `tests/utils/test_cache.py`
4. Исправлен относительный импорт в [`tests/handlers/test_handlers_common.py:17`](../tests/handlers/test_handlers_common.py:17): `from tests.test_handlers_registration` → `from tests.handlers.test_handlers_registration`.
5. Проверен `pytest.ini` (`pythonpath = .`) — покрывает и `src/`, и `tests/`, изменений не требуется.
6. `tests/conftest.py` не содержит жёстких путей — фикстуры применяются ко всем поддиректориям автоматически.

### Результаты проверок

- `pytest tests/ -x --tb=short` — **185 passed, 0 failed** ✅

---

## 2026-05-19 — Закрытие технического долга (5 задач)

### Выполненные задачи

| Задача      | Описание                                       | Файлы                                                                                                            |
| ----------- | ---------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| TD-KEY-001  | Замена `.days // 365` на `relativedelta`       | [`inline.py:4,255`](src/keyboards/inline.py:4), [`pyproject.toml:46`](pyproject.toml:46)                         |
| TD-TST-001  | Реорганизация `tests/` — зеркалирование `src/` | 6 поддиректорий, 10 файлов перемещены, [`test_handlers_common.py:17`](tests/handlers/test_handlers_common.py:17) |
| TD-TST-002  | Подавление loguru в тестах                     | [`conftest.py:297-305`](tests/conftest.py:297)                                                                   |
| TD-MAIN-001 | `_metrics_lock` для чтений в веб-роутерах      | [`api.py:59-61`](src/web/routers/api.py:59), [`pages.py:47-51,208-210`](src/web/routers/pages.py:47)             |
| TD-MAIN-002 | Проверка `bot.session.closed` перед close      | [`main.py:422`](src/main.py:422)                                                                                 |

### Изменённые файлы

- `src/keyboards/inline.py` — импорт `relativedelta`, переписан расчёт возраста
- `pyproject.toml` — добавлена зависимость `python-dateutil`
- `tests/conftest.py` — фикстура `_silence_loguru`
- `src/web/routers/api.py` — чтения метрик под `_metrics_lock`
- `src/web/routers/pages.py` — чтения метрик под `_metrics_lock` (2 блока)
- `src/main.py` — проверка `bot.session.closed`
- `tests/` — созданы поддиректории `api/`, `database/`, `handlers/`, `keyboards/`, `services/`, `utils/`; 10 тестовых файлов перемещены; исправлен импорт в `test_handlers_common.py`

### Результаты тестов

**185 passed, 0 failed** — все тесты проходят на обновлённой структуре.

### Проверки

- `ruff check` — All checks passed

---

## 2026-05-19 — Установка type stubs для dateutil

### Выполненные задачи

| Задача  | Описание                                                                      | Файлы                                      |
| ------- | ----------------------------------------------------------------------------- | ------------------------------------------ |
| TYP-001 | Установка `types-python-dateutil` как dev-зависимости                         | [`pyproject.toml`](pyproject.toml)         |
| TYP-002 | Удаление `# pyright: ignore[reportMissingModuleSource]` из импорта `dateutil` | [`inline.py:4`](src/keyboards/inline.py:4) |
| TYP-003 | Удаление `[[tool.mypy.overrides]]` для `dateutil.*`                           | [`pyproject.toml:98`](pyproject.toml:98)   |

### Изменённые файлы

- `pyproject.toml` — добавлена зависимость `types-python-dateutil`; удалён mypy override для `dateutil.*`
- `src/keyboards/inline.py` — убран `# pyright: ignore[reportMissingModuleSource]`

### Результаты проверок

| Инструмент                     | Результат                                    |
| ------------------------------ | -------------------------------------------- |
| `mypy src/keyboards/inline.py` | ✅ Success: no issues found in 1 source file |

---

## 2026-05-19 — Исправление TelegramBadRequest «no text in the message to edit»

### Выполненные задачи

| Задача  | Описание                                                                   | Файлы                                                   |
| ------- | -------------------------------------------------------------------------- | ------------------------------------------------------- |
| FIX-001 | Замена `edit_text()` на delete+answer в `handle_delete_patient` action=ask | [`common.py:1023`](src/handlers/common.py:1023)         |
| FIX-002 | Замена `edit_text()` на delete+answer в `start_add_patient`                | [`registration.py:28`](src/handlers/registration.py:28) |

### Изменённые файлы

- `src/handlers/common.py:1023-1029` — `handle_delete_patient(action="ask")`: удаление старого фото-сообщения и отправка нового текстового через `call.message.answer()` вместо `edit_text()`
- `src/handlers/registration.py:1` — добавлен `import contextlib`
- `src/handlers/registration.py:28-33` — `start_add_patient`: удаление старого фото-сообщения и отправка нового текстового через `call.message.answer()` вместо `edit_text()`

### Результаты проверок

| Инструмент                                                       | Результат            |
| ---------------------------------------------------------------- | -------------------- |
| `ruff check src/handlers/common.py src/handlers/registration.py` | ✅ All checks passed |

---

## 2026-05-19 — Batch-исправление технического долга MIN-004..MIN-015

### Выполненные задачи

| ID      | Описание                                                                                     | Файлы                                                        |
| ------- | -------------------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| MIN-004 | Убрать `.encode("utf-8")` в `_notify_ntfy()` — httpx принимает строки                        | [`error_notifier.py:89`](src/services/error_notifier.py)     |
| MIN-005 | Удалить дублирующий `import sentry_sdk` внутри `_notify_sentry()`, вынести на уровень модуля | [`error_notifier.py:12,112`](src/services/error_notifier.py) |
| MIN-006 | Унифицировать rate limiter: CallbackQuery → throttling с ожиданием как у Message             | [`ratelimit.py:102-107`](src/middleware/ratelimit.py)        |
| MIN-008 | Убрать избыточную проверку `if call.bot is None` в `handle_delete_patient`                   | [`common.py:1031-1032`](src/handlers/common.py)              |
| MIN-009 | Вынести дублирующий код `skip_alias()`/`cancel_registration()` в `_show_patient_selection()` | [`registration.py`](src/handlers/registration.py)            |
| MIN-010 | Вынести `from loguru import logger` на уровень модуля в `helpers.py`                         | [`helpers.py:9,34`](src/utils/helpers.py)                    |
| MIN-013 | Добавить fallback-формат (проверка на одно слово) в `_short_clinic_label()`                  | [`inline.py:158-160`](src/keyboards/inline.py)               |
| MIN-014 | Добавить `logger.exception()` в голый `except` в `get_clinic_selection()`                    | [`inline.py:257`](src/keyboards/inline.py)                   |
| MIN-015 | Добавить валидацию URL для `PROXY_URL` через `urlparse` в `main.py`                          | [`main.py:303-309`](src/main.py)                             |

### Изменённые файлы

- `src/services/error_notifier.py:1,12,89,112` — добавлен `import sentry_sdk` на уровне модуля; убраны `.encode("utf-8")` и дублирующий `import sentry_sdk` внутри `_notify_sentry()`
- `src/middleware/ratelimit.py:1,11,102-107` — добавлен `import asyncio`; CallbackQuery при rate limit — `await asyncio.sleep(1)` + `return await handler(event, data)`
- `src/handlers/common.py:1031-1032` — удалены строки `if call.bot is None: return`
- `src/handlers/registration.py` — добавлен `_show_patient_selection()`; `skip_alias()` и `cancel_registration()` используют общий helper
- `src/utils/helpers.py:9,34` — `from loguru import logger` вынесен на уровень модуля
- `src/keyboards/inline.py:3` — добавлен `from loguru import logger`; в `_short_clinic_label()` добавлен fallback для однословных названий; в `get_clinic_selection()` добавлен `logger.exception()`
- `src/main.py:303-309` — добавлена валидация `PROXY_URL` через `urlparse`
- `docs/agents/TECH_DEBT.md:90-100` — удалены строки MIN-004..MIN-015 (выполнены)

### Результаты проверок

| Инструмент                                      | Результат            |
| ----------------------------------------------- | -------------------- |
| `ruff check src` (изменённые файлы)             | ✅ All checks passed |
| `npx markdownlint "docs/**/*.md"`               | ✅ 0 errors          |
| `npx prettier --write docs/agents/TECH_DEBT.md` | ✅                   |

---

## 2026-05-19 — Исправление type safety для MIN-008

### Выполненные задачи

| Задача | Описание    | Файлы                                                                                                                  |
| ------ | ----------- | ---------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------- |
|        | MIN-008-fix | Замена удалённой проверки `if call.bot is None: return` на `assert call.bot is not None` для сохранения type narrowing | [`common.py:1034`](src/handlers/common.py:1034) |

### Изменённые файлы

- `src/handlers/common.py:1034` — добавлен `assert call.bot is not None` перед вызовом `_delete_cleanup_msg_entries()` для устранения ошибки mypy `Argument "bot" has incompatible type "Bot | None"; expected "Bot"`.

### Результаты проверок

| Инструмент                    | Результат                                    |
| ----------------------------- | -------------------------------------------- |
| `mypy src/handlers/common.py` | ✅ Success: no issues found in 1 source file |

---

## 2026-05-19 — Коммит техдолга MIN-004..MIN-015

### Выполненные задачи

| Задача           | Описание                                                                         | Файлы          |
| ---------------- | -------------------------------------------------------------------------------- | -------------- |
| MIN-004..MIN-015 | Коммит всех изменений по техническому долгу: чистка кода, типизация, логирование | Все файлы ниже |

### Изменённые файлы

- `src/services/error_notifier.py` — MIN-004, MIN-005: чистка кода, типизация
- `src/middleware/ratelimit.py` — MIN-006: чистка кода
- `src/handlers/common.py` — MIN-008: type safety, assert вместо удалённой проверки
- `src/handlers/registration.py` — MIN-009: чистка кода
- `src/utils/helpers.py` — MIN-010: чистка кода
- `src/keyboards/inline.py` — MIN-013, MIN-014: чистка кода, логирование
- `src/main.py` — MIN-015: чистка кода
- `docs/agents/TECH_DEBT.md` — обновление статусов выполненных задач
- `docs/agents/SESSION_LOG.md` — запись сессии
- `docs/agents/SESSION_ARCHIVE.md` — архив предыдущей записи

### Коммит

```text
c729fb6 fix: техдолг MIN-004..MIN-015 — чистка кода, типизация, логирование
```

### Результаты проверок

| Инструмент          | Результат         |
| ------------------- | ----------------- |
| `ruff` (pre-commit) | ✅ Passed         |
| `git commit`        | ✅ Успешно создан |

---

## 2026-05-19 — Техдолг src/services/ (TD-SVC-001..008)

**Задача:** Устранение 8 пунктов технического долга из секции `src/services/` согласно [`TECH_DEBT.md`](TECH_DEBT.md).

### Выполненные задачи

| ID         | Описание                                                                                                    | Файл                                                                  |
| ---------- | ----------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| TD-SVC-001 | Рефакторинг `_classify_slot_change()` → `_handle_disappeared()`, `_handle_appeared()`, `_handle_decrease()` | [`monitor.py:54-113`](src/services/monitor.py:54)                     |
| TD-SVC-002 | Частичное сохранение врачей в `discovery_loop` (per-specialty commit)                                       | [`doctor_discovery.py:87-114`](src/services/doctor_discovery.py:87)   |
| TD-SVC-003 | Фиксированная пауза 0.7с вместо `random.uniform(1,3)`                                                       | [`doctor_discovery.py:116`](src/services/doctor_discovery.py:116)     |
| TD-SVC-004 | `exc_info=False` после 3 последовательных ошибок в `sync_clinic_names()`                                    | [`doctor_discovery.py:139-169`](src/services/doctor_discovery.py:139) |
| TD-SVC-005 | Per-metric `asyncio.Lock` вместо глобального lock                                                           | [`healthcheck.py:101-106`](src/services/healthcheck.py:101)           |
| TD-SVC-006 | Пакетная обработка (батчи по 50) вместо загрузки всех пользователей                                         | [`cleanup.py:40`](src/services/cleanup.py:40)                         |
| TD-SVC-007 | Валидация `uid` через `try/except (ValueError, TypeError)` перед `int()`                                    | [`cleanup.py:81`](src/services/cleanup.py:81)                         |
| TD-SVC-008 | Обрезка traceback с начала: `tb_str[:2000]` вместо `tb_str[-2000:]`                                         | [`error_notifier.py:78`](src/services/error_notifier.py:78)           |

### Изменённые файлы

- [`src/services/monitor.py`](src/services/monitor.py)
- [`src/services/doctor_discovery.py`](src/services/doctor_discovery.py)
- [`src/services/healthcheck.py`](src/services/healthcheck.py)
- [`src/services/cleanup.py`](src/services/cleanup.py)
- [`src/services/error_notifier.py`](src/services/error_notifier.py)
- [`docs/agents/TECH_DEBT.md`](docs/agents/TECH_DEBT.md) — удалены выполненные строки

### Результаты проверок

- `ruff check src/services/` — All checks passed!
- `markdownlint` — без ошибок
- `prettier` — отформатировано

---

## 2026-05-19 — Выполнение техдолга (TD-UTL-003, TD-UTL-004, TD-OTHER-001..004)

### Выполненные задачи

| ID           | Описание                                         | Файлы                                                                                                                                                                 | Результат                                                                              |
| ------------ | ------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| TD-OTHER-001 | Синхронизация pyproject.toml с requirements.txt  | `pyproject.toml:31`, `poetry.lock`                                                                                                                                    | `prometheus-client` добавлен, `requirements.txt` оставлен (используется Dockerfile/CI) |
| TD-UTL-003   | Импорт `redis.asyncio.Redis` под `TYPE_CHECKING` | `src/utils/redis.py:23-24,112`                                                                                                                                        | Тип `Any` заменён на `Redis`, импорт под `TYPE_CHECKING`                               |
| TD-OTHER-002 | Добавить цели `heal`/`heal-types` в Makefile     | `Makefile:17-18,23,65-69`                                                                                                                                             | Цели `apply-heuristics`, `apply-heuristic-types`                                       |
| TD-OTHER-004 | Пароль Redis в docker-compose                    | `docker-compose.yml:8-10`, `.env:17`, `.env.example:18`, `src/config.py:47,152-163`                                                                                   | `REDIS_PASSWORD` прокинут через все слои                                               |
| TD-OTHER-003 | `before_send` фильтрация в Sentry                | `src/services/error_notifier.py:8-15,21,66`                                                                                                                           | 6 категорий несущественных ошибок фильтруются                                          |
| TD-UTL-004   | TypedDict вместо строковых литералов             | `src/database/types.py` (новый), `src/database/manager.py`, `src/services/monitor.py`, `src/handlers/common.py`, `src/web/routers/api.py`, `src/web/routers/pages.py` | 8 TypedDict, ruff 0 errors                                                             |

### Изменённые файлы

- `pyproject.toml`
- `poetry.lock`
- `src/utils/redis.py`
- `Makefile`
- `docker-compose.yml`
- `.env`
- `.env.example`
- `src/config.py`
- `src/services/error_notifier.py`
- `src/database/types.py` (новый)
- `src/database/manager.py`
- `src/services/monitor.py`
- `src/handlers/common.py`
- `src/web/routers/api.py`
- `src/web/routers/pages.py`
- `docs/agents/TECH_DEBT.md`
- `docs/design/td-utl-004-typeddict-design.md` (новый)

### Результаты проверок

- `ruff check` целевых файлов: 0 errors
- `poetry check`: All set!

---

## Лог сессии

## 2026-05-19 — Выполнение техдолга (TD-UTL-003, TD-UTL-004, TD-OTHER-001..004)

### Выполненные задачи

| ID           | Описание                                                                                 | Файлы                                                                                                                                                                                                                                                                                  | Результат                                                              |
| ------------ | ---------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| TD-OTHER-001 | Синхронизация pyproject.toml; перевод Dockerfile/CI на Poetry; удаление requirements.txt | `pyproject.toml:31`, `poetry.lock`, `Dockerfile:33-34`, `.github/workflows/ci.yml`                                                                                                                                                                                                     | Poetry вместо pip, prometheus-client добавлен, requirements.txt удалён |
| TD-UTL-003   | Импорт `redis.asyncio.Redis` под `TYPE_CHECKING`                                         | `src/utils/redis.py:23-24,112`                                                                                                                                                                                                                                                         | Тип `Any` заменён на `Redis`                                           |
| TD-OTHER-002 | Цели в Makefile для heuristic-скриптов                                                   | `Makefile:17-18,23,65-69`                                                                                                                                                                                                                                                              | `apply-heuristics`, `apply-heuristic-types`                            |
| TD-OTHER-004 | Пароль Redis                                                                             | `docker-compose.yml:8-10`, `.env:17`, `.env.example:18`, `src/config.py:47,152-163`                                                                                                                                                                                                    | `REDIS_PASSWORD` прокинут через все слои                               |
| TD-OTHER-003 | Sentry `before_send` фильтрация                                                          | `src/services/error_notifier.py:8-15,21,66`                                                                                                                                                                                                                                            | 6 категорий несущественных ошибок фильтруются                          |
| TD-UTL-004   | TypedDict вместо строковых литералов                                                     | `src/database/types.py` (новый), `src/database/database.py`, `src/database/manager.py`, `src/services/monitor.py`, `src/handlers/common.py`, `src/handlers/registration.py`, `src/services/export.py`, `src/web/routers/api.py`, `src/web/routers/pages.py`, `src/keyboards/inline.py` | 8 TypedDict, 10 файлов, все cast() убраны                              |

### Аудит кодовой базы

- **mypy:** 5 pre-existing ошибок исправлено → **0 errors**
- **ruff:** **0 errors**
- **Подавления:** 10 `# type: ignore` (все легитимны), 3 `# noqa` (все легитимны)
- **`except Exception: pass`:** 2 заменены на логирование
- Мёртвый код `log_by_key` удалён из `src/services/export.py`

### Изменённые файлы (24 файла)

- `pyproject.toml`
- `poetry.lock`
- `Dockerfile`
- `.github/workflows/ci.yml`
- `Makefile`
- `docker-compose.yml`
- `.env`
- `.env.example`
- `src/config.py`
- `src/utils/redis.py`
- `src/services/error_notifier.py`
- `src/services/monitor.py`
- `src/services/export.py`
- `src/database/types.py` (новый)
- `src/database/database.py`
- `src/database/manager.py`
- `src/handlers/common.py`
- `src/handlers/registration.py`
- `src/keyboards/inline.py`
- `src/web/routers/api.py`
- `src/web/routers/pages.py`
- `docs/agents/TECH_DEBT.md`
- `docs/design/td-utl-004-typeddict-design.md` (новый)
- `requirements.txt` (удалён)

---

## 2026-05-19 — OPT-K & OPT-L: Консолидация фикстур + аннотации async-функций

### Выполненные задачи

- **OPT-K** — Консолидация тестовых фикстур через [`tests/conftest.py`](tests/conftest.py):
  - Добавлено 7 общих хелперов: `TEST_USER_ID`, `make_message()`, `make_callback()`, `make_mock_api()`, `make_mock_bot()`, `seed_clinic()`, `seed_doctors()` (строки 311–399)
  - Из [`tests/handlers/test_handlers_common.py`](tests/handlers/test_handlers_common.py) удалено ~26 строк дублирования setup-логики
  - [`tests/keyboards/test_keyboards.py`](tests/keyboards/test_keyboards.py) — без изменений
- **OPT-L** — Аннотации `-> None` для async-функций без возвращаемого типа:
  - 91 функция в 21 файле `src/`: 72 `-> None`, 18 typed (`-> Any`, `-> dict[str, Any]`, `-> TemplateResponse`, `-> Response`), 1 `-> AsyncGenerator[None, None]`
  - Ключевые файлы: [`src/database/manager.py`](src/database/manager.py) (13), [`src/database/database.py`](src/database/database.py) (19), [`src/handlers/common.py`](src/handlers/common.py) (17), [`src/handlers/registration.py`](src/handlers/registration.py) (7), [`src/web/routers/api.py`](src/web/routers/api.py) (7), [`src/web/routers/pages.py`](src/web/routers/pages.py) (6)

### Изменённые файлы

- [`tests/conftest.py`](tests/conftest.py) — добавлены общие хелперы
- [`tests/handlers/test_handlers_common.py`](tests/handlers/test_handlers_common.py) — удалено дублирование
- 21 файл в `src/` — добавлены аннотации возвращаемого типа

### Результаты проверок

- **Ruff**: 0 errors

---

## 2026-05-20

### Выполненные задачи

- **Коммит и пуш проекта** — зафиксированы изменения в [`pages.py`](src/web/routers/pages.py) (рефакторинг `TemplateResponse` → `HTMLResponse`, явный `cast` к `Jinja2Templates`), удалён [`TECH_DEBT.md`](docs/agents/TECH_DEBT.md). Коммит [`0202d7f`](https://github.com/acidmsg/lenreg_ticket_bot.git).

### Изменённые файлы

| Файл                       | Действие |
| -------------------------- | -------- |
| `src/web/routers/pages.py` | Изменён  |
| `docs/agents/TECH_DEBT.md` | Удалён   |

### Результаты

- Коммит `0202d7f` отправлен в `origin/main` (22 insertions, 64 deletions)
- **Pytest**: 181 passed, 4 failed (pre-existing, не связаны с изменениями)

---

## 2026-05-19 — Исправление F821 Undefined name и arg-type ошибок в тестах

### Выполненные задачи

- **F821** — Исправлена ошибка `Undefined name` в [`tests/handlers/test_handlers_common.py`](tests/handlers/test_handlers_common.py):
  - Проблема: использовались неопределённые имена `_seed_clinic` и `_seed_doctors`. В `conftest.py` функции называются `seed_clinic` и `seed_doctors` (без префиксного подчёркивания).
  - Добавлен импорт с алиасами: `seed_clinic as _seed_clinic, seed_doctors as _seed_doctors`
- **arg-type** — Исправлена ошибка типизации в [`tests/keyboards/test_keyboards.py`](tests/keyboards/test_keyboards.py):
  - Проблема: `get_city_selection()` ожидает `list[ClinicInfo] | None`, а тесты передавали `list[dict[str, str]]`.
  - Заменены вызовы на корректно типизированные `list[ClinicInfo]` с импортом `ClinicInfo` из `src.database.types`.

### Изменённые файлы

- [`tests/handlers/test_handlers_common.py`](tests/handlers/test_handlers_common.py) — добавлены импорты с алиасами
- [`tests/keyboards/test_keyboards.py`](tests/keyboards/test_keyboards.py) — исправлены типы аргументов

### Результаты проверок

- **Ruff**: 0 errors

---

## 2026-05-20 — Починка GitHub Actions CI

### Выполненные задачи

1. **Диагностика падения CI** — корневая причина: Poetry 2.x breaking change, `poetry install` без `--with dev` не устанавливает ruff/mypy/pytest.
2. **Исправление [`ci.yml`](.github/workflows/ci.yml)** — 7 правок:
   - `pip install poetry==2.4.1` (фиксация версии, строки 34, 58, 93)
   - `poetry install --with dev` (установка dev-зависимостей, строки 36, 60, 95)
   - Унификация `mypy` с pre-commit (строка 63)
3. **Исправление ошибок mypy** (3 ошибки → 0):
   - [`auth.py:9`](src/web/auth.py:9) — аннотация `call_next: Callable[[Request], Awaitable[Response]]`
   - [`api.py:144`](src/web/routers/api.py:144) — возврат `dict[str, Any] | JSONResponse`
4. **Починка тестов** (4 failed → 0):
   - [`test_handlers_common.py`](tests/handlers/test_handlers_common.py) — `edit_text`→`answer`, `mock_bot`
   - [`test_handlers_registration.py`](tests/handlers/test_handlers_registration.py) — `edit_text`→`answer`

### Изменённые файлы

| Файл                                                                                           | Изменения                                           |
| ---------------------------------------------------------------------------------------------- | --------------------------------------------------- |
| [`.github/workflows/ci.yml`](.github/workflows/ci.yml)                                         | 7 правок: Poetry 2.4.1, --with dev, mypy унификация |
| [`src/web/auth.py`](src/web/auth.py)                                                           | Импорт Callable/Awaitable, аннотация call_next      |
| [`src/web/routers/api.py`](src/web/routers/api.py)                                             | Аннотация возврата dict \| JSONResponse             |
| [`tests/handlers/test_handlers_common.py`](tests/handlers/test_handlers_common.py)             | edit_text→answer, mock_bot для test_delete_yes_no   |
| [`tests/handlers/test_handlers_registration.py`](tests/handlers/test_handlers_registration.py) | edit_text→answer в 2 тестах                         |

### Результаты тестов

- **ruff:** All checks passed (68 файлов)
- **mypy:** Success: no issues found (47 файлов)
- **pytest:** 185 passed, 0 failed
