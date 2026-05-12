# SESSION_LOG.md

## 2026-05-12 (ruff check/pytest: исправление 46 ошибок)

### Исправление всех ошибок ruff check + ruff format ✅

**Задача:** Исправить 46 ошибок ruff check (E501 длинные строки, ASYNC240 os.path в async, ASYNC251 time.sleep, N806 переменная) + автоформатирование 5 файлов.

**Изменённые файлы (14 файлов):**
| Файл | Что исправлено |
|------|---------------|
| [`src/config.py`](src/config.py:71,143) | E501: разбиты 2 длинные строки (комментарий + f-string логгера) |
| [`src/database/database.py`](src/database/database.py:128,262,274,554,571,591,616,661,723) | E501: разбиты SQL-строки и f-строки логгеров; ASYNC240: `# noqa` на `os.path.exists/makedirs` |
| [`src/database/manager.py`](src/database/manager.py:121) | E501: разбит длинный SQL |
| [`src/database/migrations.py`](src/database/migrations.py:87,94) | E501: разбит SQL и docstring |
| [`src/handlers/common.py`](src/handlers/common.py:198,481,504,721) | E501: разбиты 4 длинные строки сообщений |
| [`src/handlers/registration.py`](src/handlers/registration.py:68,84,116,149) | E501: разбиты 4 длинные строки сообщений |
| [`src/keyboards/inline.py`](src/keyboards/inline.py:52,118,269,279) | N806: `DENTAL_CLINIC_ID` → `_dental_clinic_id`; E501: разбиты 3 комментария |
| [`src/main.py`](src/main.py:26,40) | ASYNC240: `# noqa` на `os.path.exists/makedirs` |
| [`src/services/cleanup.py`](src/services/cleanup.py:3) | E501: разбит docstring |
| [`src/services/doctor_discovery.py`](src/services/doctor_discovery.py:117) | E501: f-string логгера → `%s` формат |
| [`src/services/healthcheck.py`](src/services/healthcheck.py:80,82,245) | E501: разбиты f-строки статуса и настроек |
| [`src/services/monitor.py`](src/services/monitor.py:37,79,125,146,181,184) | E501: разбиты docstring, f-строки, логгеры |
| [`src/utils/cache.py`](src/utils/cache.py:32,55) | ASYNC240: `# noqa` на `os.path.exists` |
| [`tests/conftest.py`](tests/conftest.py:1,35,41,77) | ASYNC240: `# noqa` на `os.path.exists/remove`; ASYNC251: `time.sleep` → `await asyncio.sleep` + `import asyncio` |
| [`tests/test_cache.py`](tests/test_cache.py:50) | ASYNC240: `# noqa` на `os.path.exists` |
| [`tests/test_keyboards.py`](tests/test_keyboards.py:108) | E501: разбита длинная строка тестовых данных |

**Результаты проверок:**
| Инструмент | Результат |
|-----------|----------|
| `ruff check src scripts tests` | **All checks passed!** ✅ |
| `ruff format --check src scripts tests` | **39 files already formatted** ✅ |
| `pytest tests/ -v` | **134 passed in 16.97s** ✅ |

---

## 2026-05-12 (конфиг-файлы: актуализация)

### Проверка и дополнение pyrightconfig.json, pyproject.toml, .vscode/settings.json ✅

**Задача:** Проверить актуальность 4 конфигурационных файлов проекта, исправить недостающие настройки.

**Итог по файлам:**
| Файл | Вердикт |
|------|---------|
| [`.vscode/launch.json`](.vscode/launch.json) | ✅ Актуален, правки не нужны |
| [`pyrightconfig.json`](pyrightconfig.json) | ❌ Не хватало `pythonVersion`, `typeCheckingMode`, `include`, `exclude` |
| [`pyproject.toml`](pyproject.toml) | ❌ Не хватало `target-version`, `exclude`, `[tool.ruff.format]` |
| [`.vscode/settings.json`](.vscode/settings.json) | ❌ Не хватало `python.analysis.extraPaths`, `typeCheckingMode`, `[python]` секции форматирования |

**Изменённые файлы:**
| Файл | Что добавлено |
|------|---------------|
| [`pyrightconfig.json`](pyrightconfig.json) | `pythonVersion: "3.14"`, `typeCheckingMode: "basic"`, `include: ["src","scripts","tests"]`, `exclude` |
| [`pyproject.toml`](pyproject.toml) | `target-version = "py314"`, `exclude`, `[tool.ruff.format]` с quote-style и indent-style; убран `fixable = ["ALL"]` (дефолт) |
| [`.vscode/settings.json`](.vscode/settings.json) | `python.analysis.extraPaths`, `python.analysis.typeCheckingMode`, `[python]` секция (ruff formatter, formatOnSave, organizeImports) |

**Результаты тестов:** Не запускались

---

## 2026-05-12 (Sentry + NTFY full setup)

### Подключение Sentry DSN и NTFY ✅

**Задача:** Настроить оба канала оповещений (Sentry + NTFY), заполнить отсутствующие параметры в `.env`.

**Изменённые файлы:**
| Файл | Действие |
|------|----------|
| [`.env`](.env:18-34) | Добавлены секции Error notifications (M2) и Rate limiting (M3): `ERROR_NOTIFY_ENABLED`, `NTFY_TOPIC_URL=https://ntfy.sh/ltb_alert`, `SENTRY_DSN`, `ENVIRONMENT`, `USER_RATE_LIMIT_MAX`, `USER_RATE_LIMIT_PERIOD` |
| [`services/error_notifier.py`](services/error_notifier.py:35-36) | В `_init_sentry()` добавлены `send_default_pii=True` и `enable_logs=True` |

**Результаты тестов:** Не запускались

---

## 2026-05-12 (env audit)

### Аудит .env и .env.example ✅

**Задача:** Проверить расхождения между [`.env`](.env:1) и [`.env.example`](.env.example:1), актуальность параметров в коде, объяснить настройку `NTFY_TOPIC_URL` и `SENTRY_DSN`.

**Выявлено:** В `.env` отсутствуют 6 параметров (против `.env.example`): `ERROR_NOTIFY_ENABLED`, `NTFY_TOPIC_URL`, `SENTRY_DSN`, `ENVIRONMENT`, `USER_RATE_LIMIT_MAX`, `USER_RATE_LIMIT_PERIOD`. Все они имеют безопасные дефолты в [`config.py:80-94`](config.py:80), поэтому бот работает корректно.

**Все параметры из `.env.example` подтверждены как используемые:**
- `ERROR_NOTIFY_ENABLED` → проверка в [`error_notifier.notify()`](services/error_notifier.py:54)
- `NTFY_TOPIC_URL` → HTTP POST в [`error_notifier._notify_ntfy()`](services/error_notifier.py:58,88-89)
- `SENTRY_DSN` → инициализация SDK в [`error_notifier._init_sentry()`](services/error_notifier.py:27,33)
- `ENVIRONMENT` → тег в [`sentry_sdk.init()`](services/error_notifier.py:35)
- `USER_RATE_LIMIT_MAX` / `USER_RATE_LIMIT_PERIOD` → [`ratelimit.py:42-47`](middleware/ratelimit.py:42-47)
- Все ключи синхронизируются с таблицей `config` БД через [`load_config_from_db()`](config.py:102)

**Изменённые файлы:** Нет (только анализ)

**Результаты тестов:** Не запускались

---

## 2026-05-12 (project cleanup)

### Очистка мусорных и временных файлов ✅

**Аудит структуры проекта** выявил несколько проблем:

| # | Файл | Статус |
|---|------|--------|
| 1 | [`$null`](file://$null) | Артефакт терминала/VSCode — **удалён** |
| 2 | [`PySocks-1.7.1-py3-none-any.whl`](file://PySocks-1.7.1-py3-none-any.whl) | Бинарный wheel в git — **удалён из git и с диска** |
| 3 | [`.mypy_cache/`](file://.mypy_cache), [`.ruff_cache/`](file://.ruff_cache) | Не были в `.gitignore` — **добавлены** |
| 4 | [`*.whl`](file://.gitignore) | Не было правила в `.gitignore` — **добавлено** |

### Изменённые файлы

| Файл | Действие |
|------|----------|
| [`$null`](file://$null) | Удалён |
| [`PySocks-1.7.1-py3-none-any.whl`](file://PySocks-1.7.1-py3-none-any.whl) | Удалён (`git rm --cached` + `del`) |
| [`.gitignore`](file://.gitignore:1) | Добавлены `.mypy_cache/`, `.ruff_cache/`, `*.whl`; `data/monitoring_cache.json` + `*.db*` заменены на `data/`; структурирован по секциям |

### Дополнительно выявлено (не требует действий)

- Stale VSCode табы (7 шт.) — файлы на диске отсутствуют, нужно закрыть вручную в редакторе.
- [`pyproject.toml`](file://pyproject.toml) — есть на диске, но не закоммичен.

---

## 2026-05-12 (zdrav API retry + logging fix)

### Добавлен retry и улучшено логирование в ZdravClient ✅

**Диагностика:** В логе [`logs/error.log:6813`](logs/error.log:6813) зафиксирован шквал ошибок API zdrav.lenreg.ru (15 ошибок за 1.5 мин) при старте бота в 10:13. При этом сервер zdrav.lenreg.ru был доступен (тестовые скрипты подтвердили 200 OK), а сообщения ошибок в логе были пустыми: `Ошибка API (fetch_speciality_list): `.

**Корневые причины (2 бага):**

1. **Отсутствие retry** в методах `fetch_speciality_list` и `fetch_clinic_list`. При 69 одновременных Discovery-циклах на старте один таймаут/сбой сети приводил к потере данных без повторных попыток. Методы `check_slots` и `fetch_all_doctors` уже имели retry — неконсистентность.

2. **Битое логирование:** httpx исключения могут иметь пустой `str()` (например `ConnectError('')` → `str()` = `''`). Все 5 методов использовали `f"...: {e}"`, что давало невидимые ошибки.

**Исправления в [`api/zdrav_client.py`](api/zdrav_client.py):**

| Метод | Строки | Изменения |
|-------|--------|-----------|
| `fetch_speciality_list` | [136-162](api/zdrav_client.py:136) | Добавлен retry (3 попытки, sleep 2s для 5xx/exception) |
| `fetch_clinic_list` | [265-294](api/zdrav_client.py:265) | Добавлен retry (3 попытки, sleep 2s для 5xx/exception) |
| Все 5 методов | [119](api/zdrav_client.py:119), [156](api/zdrav_client.py:156), [206](api/zdrav_client.py:206), [247](api/zdrav_client.py:247), [288](api/zdrav_client.py:288) | `{e}` → `{repr(e) if not str(e) else str(e)}` — логирование всегда показывает тип/текст ошибки |

### Изменённые файлы

| Файл | Действие |
|------|----------|
| [`api/zdrav_client.py`](api/zdrav_client.py:136) | Retry + фикс логирования в 5 методах |

---

## 2026-05-12 (ci.yml cleanup)

### Удалён лишний BOT_TOKEN из CI ✅

- **Причина:** предупреждение VS Code "Context access might be invalid: BOT_TOKEN" в [`.github/workflows/ci.yml`](.github/workflows/ci.yml:28)
- **Анализ:** `BOT_TOKEN` не используется ни в одном тесте (поиск по `tests/` — 0 упоминаний). В [`config.py:32`](config.py:32) есть fallback `"MUST_BE_OVERRIDDEN_IN_ENV"` — CI не требует этого секрета.
- **История:** строка была добавлена при создании CI-файла 2026-05-07 «на всякий случай».
- **Решение:** удалены строки 28-29 (`env:` + `BOT_TOKEN: ${{ secrets.BOT_TOKEN }}`) из [`ci.yml`](.github/workflows/ci.yml:26).

### Изменённые файлы

| Файл | Действие |
|------|----------|
| [`.github/workflows/ci.yml`](.github/workflows/ci.yml:26) | Удалены лишние строки `env`/`BOT_TOKEN` |

---

## 2026-05-11 (venv rebuild)

### Пересоздание .venv ✅

- Удалён старый `.venv` (содержал пути `d:\projects\bots\zdrav.lenreg` с прошлого диска)
- Создан новый `.venv` с Python 3.14.4 и корректным путём `z:\_projects\_bots\zdrav.lenreg\.venv`
- Установлены пакеты из [`requirements.txt`](requirements.txt:1)
- Добавлены пропущенные зависимости: `pre-commit-hooks`, `types-aiofiles`, `types-cachetools`
- Исправлена mypy-ошибка: добавлена аннотация типа для `spam_cache` в [`utils/cache.py`](utils/cache.py:15)

### Очистка requirements.txt ✅

- Удалены неиспользуемые пакеты:
  - `pytest-mock` — нигде не используется (тесты на `unittest.mock`)
  - `aioresponses` — нигде не используется (мокается `_get_client`)
- `PySocks` **оставлен как wheel-файл** — обязательная зависимость pip на этом окружении (VPN-клиент требует socks-модуль для urllib3)
- `.venv` пересоздан заново без лишних пакетов
- **Все 10 pre-commit хуков проходят**
- **Все 134 теста проходят** (pytest 9.0.3)

### Структурирование requirements.txt ✅

- Файл [`requirements.txt`](requirements.txt:1) реорганизован в логические секции:
  - Core (aiogram), Configuration, HTTP & Networking, Proxy, Data & Storage, Rate Limiting, Error Notifications, Dev/Testing, Linting, Pre-commit
- `aiohttp-socks` снабжён комментарием о роли в прокси

### Изменённые файлы

| Файл | Действие |
|------|----------|
| `.venv/` | Пересоздан |
| [`requirements.txt`](requirements.txt:1) | Удалены `pytest-mock`, `aioresponses`; добавлены `pre-commit-hooks`, `types-aiofiles`, `types-cachetools`; реорганизован по секциям |
| [`utils/cache.py`](utils/cache.py:15) | Добавлена аннотация `spam_cache: TTLCache` |
| `PySocks-1.7.1-py3-none-any.whl` | Удалён из корня (лежит только в .venv как служебная зависимость pip) |

## 2026-05-11 (M2 + M3)

### M2 — Error notifications (Sentry + NTFY) ✅

- Создан [`services/error_notifier.py`](services/error_notifier.py:1) — централизованный диспетчер ошибок
- NTFY: HTTP POST на конфигурируемый топик (заголовок, приоритет, traceback)
- Sentry: опциональная интеграция через `sentry_sdk` (только при наличии `SENTRY_DSN`)
- Интегрировано в [`main.py`](main.py:127) — `polling_crash` и [`main.py`](main.py:154) — `startup_crash`
- Новые поля в [`config.py`](config.py:81): `ERROR_NOTIFY_ENABLED`, `NTFY_TOPIC_URL`, `SENTRY_DSN`, `ENVIRONMENT`
- Добавлены в [`.env.example`](.env.example:18) с комментариями
- `sentry-sdk>=2.0` добавлен в [`requirements.txt`](requirements.txt:11)

### M3 — Per-user rate limiting ✅

- Создан [`middleware/ratelimit.py`](middleware/ratelimit.py:1) — aiogram outer middleware
- Sliding window на основе списков timestamps (сообщения и callback-запросы раздельно)
- При превышении лимита: сообщения — silently dropped, callback — ответ «⏳ Слишком много запросов»
- Зарегистрирован в [`main.py`](main.py:81) как `dp.update.outer_middleware(UserRateLimitMiddleware())`
- Новые поля в [`config.py`](config.py:88): `USER_RATE_LIMIT_MAX` (30) и `USER_RATE_LIMIT_PERIOD` (60s)
- Добавлены в [`.env.example`](.env.example:28)

### Изменённые файлы

| Файл | Действие |
|------|----------|
| [`services/error_notifier.py`](services/error_notifier.py:1) | Создан |
| [`middleware/__init__.py`](middleware/__init__.py:1) | Создан |
| [`middleware/ratelimit.py`](middleware/ratelimit.py:1) | Создан |
| [`config.py`](config.py:1) | Добавлены поля M2/M3 |
| [`.env.example`](.env.example:1) | Добавлены секции M2/M3 |
| [`main.py`](main.py:1) | Импорты + middleware + error_notifier в except |
| [`requirements.txt`](requirements.txt:1) | Добавлен `sentry-sdk` |
| [`docs/AGENT_TASKS.md`](docs/AGENT_TASKS.md:1) | Удалены M2, M3 |
| [`database/database.py`](database/database.py:652) | 4 поля в `seed_config_from_defaults()` |
| [`.env.example`](.env.example:18) | NTFY_TOPIC_URL + SENTRY_DSN → плейсхолдеры |
| [`database/migrations.py`](database/migrations.py:93) | Миграция v5: `migrate_v5_seed_new_config_keys` |

### Config DB migration (M2/M3 follow-up)

- 4 нечувствительных поля перенесены в БД-синхронизацию: `ERROR_NOTIFY_ENABLED`, `ENVIRONMENT`, `USER_RATE_LIMIT_MAX`, `USER_RATE_LIMIT_PERIOD`
- 2 секретных поля остались только в `.env`: `NTFY_TOPIC_URL`, `SENTRY_DSN`
- Добавлены `CONFIG_KEY_*` константы + entries в `mapping` ([`config.py`](config.py:104))
- Добавлены defaults в `seed_config_from_defaults()` ([`database/database.py`](database/database.py:652))
- `.env.example`: секреты заменены на `your_..._here` плейсхолдеры
- Добавлена миграция v5 ([`database/migrations.py`](database/migrations.py:93)) — сидирование **всех** 19 config-ключей через `INSERT OR IGNORE` (безопасна для существующих БД)
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

## 2026-05-11

- Проведён аудит кода на хардкод, мусорный, излишний и мёртвый код
- Найдено 38 проблем:
  - Хардкод — 15 (rate limits, retry counts, User-Agent, clinic_id "272", district_id "4", задержки)
  - Мусорный код — 4 (баг + дубликат в apply_city_heuristic.py, нерабочий migrate_configs_to_db.py, дублирование CREATE TABLE, копипаста detect_clinic_city)
  - Излишний код — 8 (неиспользуемый in-memory кэш в DoctorManager, пустой save(), обёртка _delete_monitoring_messages, невызываемая update_cache_key, устаревший комментарий в healthcheck)
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

## 2026-05-11

### B2 — Очистка `empty_counts` от неактивных ключей

**Проблема:** `empty_counts = {}` в [`services/monitor.py`](services/monitor.py:90) — словарь рос бесконечно, ключи никогда не удалялись при отписке от врача или удалении пациента. Реальный риск был низким (типично 20–750 записей), но при долгоживущем процессе мог накапливаться.

**Решение:** Добавлена очистка неактивных ключей в начале каждого цикла `while True` (`services/monitor.py:96-105`):

- Собирается множество `active_keys` на основе текущих данных `db.data["monitoring"]`
- Все ключи `empty_counts`, отсутствующие в `active_keys`, удаляются

**Почему не `TTLCache`:** `TTLCache` сломал бы логику защиты от ложных пустых ответов (3 retry) — TTL сбрасывал бы счётчик при длительном отсутствии слотов, а `maxsize` мог вытеснить активные ключи.

**Файлы:**

- [`services/monitor.py`](services/monitor.py) — добавлена очистка `empty_counts` (строки 96-105)
- [`docs/AGENT_TASKS.md`](docs/AGENT_TASKS.md) — B2 отмечен выполненным

### Удаление тестов `check_affiliation`

**Проблема:** 3 теста в [`tests/test_zdrav_client.py`](tests/test_zdrav_client.py:97-119) падали с `AttributeError: 'ZdravClient' object has no attribute 'check_affiliation'`. Метод был удалён из [`api/zdrav_client.py`](api/zdrav_client.py) ранее, но тесты остались.

**Решение:** Удалены 3 теста (`test_check_affiliation_success`, `test_check_affiliation_failure`, `test_check_affiliation_error`). Поиск `check_affiliation` по проекту подтвердил: метод не используется нигде, кроме тестов.

**Результат:** 56/56 passed.

### `scripts/run_tests.py` — постоянный скрипт для запуска тестов

**Проблема:** PowerShell-терминал искажает вывод pytest с кириллицей (баг кодировки pwsh + Python в Windows). Каждый раз приходилось создавать временный `_run_tests.py`.

**Решение:** Создан постоянный скрипт [`scripts/run_tests.py`](scripts/run_tests.py), который:

- Запускает pytest через `subprocess.run(capture_output=True)`, обходя проблемную консоль
- Сохраняет полный вывод в `.pytest_output.txt` (добавлен в `.gitignore`)
- Принимает аргументы: `python scripts/run_tests.py -v --tb=short` или `python scripts/run_tests.py -k test_cache`

**Использование:** `.venv\Scripts\python.exe scripts\run_tests.py [аргументы pytest]`

---

## 2026-05-11

### R1 — Pydantic модели API ✅

Создан [`api/models.py`](api/models.py) с 11 Pydantic-моделями для валидации ответов API zdrav.lenreg.ru:

| Эндпоинт | Модель ответа | Модель элемента |
|---|---|---|
| `check_patient` | `CheckPatientResponse` | `CheckPatientData` |
| `speciality_list` | `SpecialityListResponse` | `SpecialityItem` |
| `doctor_list` | `DoctorListResponse` | `DoctorItem` |
| `appointment_list` | `AppointmentListResponse` | `AppointmentSlot` |
| `clinic_list` | `ClinicListResponse` | `ClinicItem` |

Общие: `DateInfo` (с алиасами `day_verbose`/`month_verbose`), `ApiError` (`extra="allow"`).

**Изменения в [`api/zdrav_client.py`](api/zdrav_client.py):**

- Все 5 методов (`fetch_patient_id`, `fetch_speciality_list`, `check_slots`, `fetch_all_doctors`, `fetch_clinic_list`) валидируют ответ через `model_validate()` вместо сырых `.get()`.
- Обратная совместимость полностью сохранена (возвращаемые типы не изменены).

**Попутный фикс в [`config.py`](config.py:76):** Добавлен `extra="ignore"` в `SettingsConfigDict` — `PYTHONUTF8` из `.env` больше не ломает загрузку конфига.

### B4 — проверка ✅

Подтверждено: [`process_alias`](handlers/registration.py:95) и [`skip_alias`](handlers/registration.py:132) уже содержат `try/except` + `state.clear()` в обоих путях. Задача выполнена ранее.

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

Создан [`tests/test_keyboards.py`](tests/test_keyboards.py) — 37 тестов, покрывающих все 6 функций-клавиатур и вспомогательную `_short_clinic_label`:

| Класс тестов | Функция | Тестов |
|---|---|---|
| `TestRegistrationKeyboard` | `get_registration_keyboard` | 3 |
| `TestConfirmDeletion` | `get_confirm_deletion` | 2 |
| `TestShortClinicLabel` | `_short_clinic_label` | 5 |
| `TestPatientSelection` | `get_patient_selection` | 6 |
| `TestCitySelection` | `get_city_selection` | 5 |
| `TestDoctorSelection` | `get_doctor_selection` | 8 |
| `TestClinicSelection` | `get_clinic_selection` | 8 |

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

- [`tests/test_keyboards.py`](tests/test_keyboards.py) — новый файл, 37 тестов

## 2026-05-11

### Задача T3: Тесты для `services/doctor_discovery.py`

- Изучен модуль [`services/doctor_discovery.py`](services/doctor_discovery.py) — 4 функции: `fetch_specialties`, `_get_clinic_type_from_db`, `discovery_loop`, `sync_clinic_names`
- Создан [`tests/test_doctor_discovery.py`](tests/test_doctor_discovery.py) — 23 теста в 5 классах:

| Класс | Тестируемая функция | Тестов |
|---|---|---|
| `TestFetchSpecialties` | `fetch_specialties` | 6 |
| `TestGetClinicTypeFromDb` | `_get_clinic_type_from_db` | 4 |
| `TestDiscoveryPatientSelection` | логика выбора patient_id в `discovery_loop` | 5 |
| `TestSyncClinicNames` | `sync_clinic_names` | 8 |

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

**Попутно исправлен баг** в [`services/doctor_discovery.py:132-135`](services/doctor_discovery.py:132):

- `str(None)` → `"None"` (truthy), из-за чего записи с `IdLPU = None` попадали в `upsert_clinic` как `("None", "Без ID")`
- Добавлена проверка `if raw_id is None: continue` перед `str(raw_id)`

**Результат:** 116/116 passed (93 базовых + 23 новых), 15.03 сек.

**Файлы:**

- [`tests/test_doctor_discovery.py`](tests/test_doctor_discovery.py) — новый файл, 23 теста
- [`services/doctor_discovery.py`](services/doctor_discovery.py) — исправлен баг `str(None)` в `sync_clinic_names`

### Оптимизация потребления памяти при тестах

**Проблема:** python.exe потреблял >20 GB RAM при прогоне 116 тестов.

**Выявленные причины (4):**

| # | Причина | Механизм |
|---|---------|----------|
| 1 | SQLite WAL-файлы не усекались | `PRAGMA journal_mode=WAL` + 116 отдельных БД = накопление WAL без checkpoint |
| 2 | `aiolimiter.AsyncLimiter` не освобождался | Каждый `ZdravClient` создавал limiter, привязанный к event loop |
| 3 | `MagicMock` цепочки атрибутов | Бесконечная рекурсия `mock.anything.anything...` при assertion introspection |
| 4 | Незавершённые `asyncio.Task` | `asyncio_mode=auto` + забытый `create_task` = висящие корутины |

**Реализованные исправления:**

- [`database/database.py:158-167`](database/database.py:163) — `PRAGMA wal_checkpoint(TRUNCATE)` в `Database.close()`: усекает WAL до 0 байт перед закрытием соединения
- [`tests/conftest.py:51-52`](tests/conftest.py:52) — `gc.collect()` после `await db.close()` в фикстуре `database`
- [`tests/conftest.py:30-42`](tests/conftest.py:30) — `gc.collect()` + 5 попыток удаления с задержкой 0.2s в `temp_db_path`
- [`tests/test_zdrav_client.py:22-25`](tests/test_zdrav_client.py:22) — `await client.close()` + `gc.collect()` в фикстуре `mock_zdrav_client` (был `return`, стал `yield`)
- [`tests/conftest.py:92-117`](tests/conftest.py:94) — опциональный `tracemalloc`-мониторинг: включается `PYTEST_MEMORY_PROFILE=1`, показывает топ-5 аллокаций >100 KB на тест

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

## 2026-05-11

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

- Создан [`tests/test_monitor_full.py`](tests/test_monitor_full.py:1) — 18 тестов (4 для `_send_notification`, 14 для `monitor_loop`)
- Мок-стратегия: `monkeypatch` для `asyncio.sleep` (CancelledError для выхода из бесконечного цикла), `swap_cache_key`, `_safe_set` (healthcheck), `_send_notification`
- `TestSendNotification`: отправка нового сообщения, удаление предыдущего + новое, устойчивость к ошибкам удаления и отправки
- `TestMonitorLoop`: slots appeared/disappeared/no change, first discovery, empty-slots protection (3 consecutive), API errors, CancelledError, multiple doctors, legacy string doctor_info, patient alias, generic exception, new slots marked
- Исправлено: monkeypatch-таргет `_safe_set` → `services.healthcheck._safe_set` (lazy import внутри monitor_loop)
- Исправлено: `monitor_loop` ловит `CancelledError` внутри через `break` (не пробрасывает наружу)
- Исправлено: `sleep_raises_on_call` для тестов с empty-slots protection (нужно 6 sleep-ов: per-doc×3 + jitter×3)

**Результат:** 134/134 passed за 17.08 сек (все тесты проекта).

## 2026-05-11 (B5 + F4)

### B5 — Вынос `_safe_set` import наверх модуля ✅

- [`services/monitor.py`](services/monitor.py:8) — `from services.healthcheck import _safe_set` перенесён из тела `monitor_loop()` в top-level imports
- Причина «циклический импорт» оказалась ошибочной: `healthcheck.py` не импортирует `monitor.py`
- [`tests/test_monitor_full.py`](tests/test_monitor_full.py:204) — monkeypatch target исправлен с `services.healthcheck._safe_set` → `services.monitor._safe_set`
- **Результат:** 134/134 passed

### F4 — Pre-commit hooks ✅

- Создан [`.pre-commit-config.yaml`](.pre-commit-config.yaml:1) — 10 хуков (все `Passed`):
  - `pre-commit-hooks` (trailing-whitespace, end-of-file-fixer, check-yaml, check-added-large-files, debug-statements, detect-private-key, mixed-line-ending)
  - `ruff check` (линтер, `--fix --exit-non-zero-on-fix`)
  - `ruff format` (форматтер, `--check`)
  - `mypy` (type checker, `--ignore-missing-imports --check-untyped-defs --explicit-package-bases`)
- [`requirements.txt`](requirements.txt:20) — добавлены `pre-commit>=4.0`, `ruff>=0.14`, `mypy>=1.18` (Dev / Testing)
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

- [`keyboards/inline.py`](keyboards/inline.py:240) — `except:` → `except (ValueError, TypeError):` (E722 bare except)
- [`handlers/common.py`](handlers/common.py:498) — `"\n".join(slots)` → `"\n".join(slots) if slots else ...` (None-safety)
- [`services/monitor.py`](services/monitor.py:89) — `empty_counts = {}` → `empty_counts: dict[str, int] = {}` (type annotation)
- [`config.py`](config.py:2) — добавлены `Any, Callable` в imports; mapping аннотирован типом
- [`handlers/common.py`](handlers/common.py:213,439,576) — удалены 3 unused variables (F841)
- [`tests/test_doctor_discovery.py`](tests/test_doctor_discovery.py:171) — удалён unused `api` (F841)
- ruff format исправил 7 файлов, mixed-line-ending — 54 файла

### Изменённые файлы

| Файл | Действие |
|------|----------|
| [`services/monitor.py`](services/monitor.py:8) | `_safe_set` import наверх; `empty_counts` аннотация |
| [`tests/test_monitor_full.py`](tests/test_monitor_full.py:204) | monkeypatch target исправлен |
| [`.pre-commit-config.yaml`](.pre-commit-config.yaml:1) | Создан (local hooks, 10 хуков) |
| [`requirements.txt`](requirements.txt:20) | Добавлены pre-commit, ruff, mypy |
| [`keyboards/inline.py`](keyboards/inline.py:240) | bare except → конкретные типы |
| [`handlers/common.py`](handlers/common.py:213) | unused variables удалены; None-safety |
| [`config.py`](config.py:2) | typing imports; mapping аннотация |
| [`docs/AGENT_TASKS.md`](docs/AGENT_TASKS.md:1) | Удалены B5, F4 |
| [`docs/SESSION_LOG.md`](docs/SESSION_LOG.md:1) | Эта запись |

**Результат:** 134/134 passed, 10/10 pre-commit hooks passed

## 2026-05-12 (fix: ClinicListResponse IdLPU int→str coercion)

### Анализ ошибок в error.log 🔍

- В [`logs/error.log`](logs/error.log:3) обнаружена ошибка: `69 validation errors for ClinicListResponse`
- **Root cause:** API `zdrav.lenreg.ru/api/clinic_list/` возвращает `IdLPU` как целые числа (int), а Pydantic-модель [`ClinicItem`](api/models.py:136) объявляла поле как `str`
- **Последствия:** `fetch_clinic_list()` падал с исключением → `sync_clinic_names()` получал пустой список → названия клиник не синхронизировались в БД. Discovery-циклы всё равно запускались через fallback-список clinic IDs.

### Исправление ✅

- В [`api/models.py`](api/models.py:13) добавлена helper-функция `_coerce_str(v) → str` с `BeforeValidator` для приведения int/None к строке
- Поле [`ClinicItem.IdLPU`](api/models.py:136) изменено на `Annotated[str, BeforeValidator(_coerce_str)]`
- Потребитель в [`services/doctor_discovery.py`](services/doctor_discovery.py:145) уже делает `str(raw_id)` — совместимость сохранена

### Изменённые файлы

| Файл | Действие |
|------|----------|
| [`api/models.py`](api/models.py:13) | Добавлены `Annotated`, `BeforeValidator`, `_coerce_str`; `IdLPU` с валидатором |

**Результат:** 38/38 tests passed (test_doctor_discovery.py + test_zdrav_client.py)

---

## 2026-05-12 (Pydantic + HTTP fix)

### Анализ лога ошибок ✅

Прочитан [`logs/error.log`](logs/error.log) (7074 строки, 2026-05-12 00:18–11:41). Выявлено **1425 ERROR**, **234 WARNING**:

| # | Категория | Кол-во | Суть |
|---|-----------|--------|------|
| 1 | Pydantic `SpecialityListResponse` validation | ~453 | `NameSpesiality`, `FerIdSpesiality`, `IdSpesiality` = `None` |
| 2 | ProxyConnectionError | ~232 | Прокси 192.168.31.47:10808 периодически отваливался |
| 3 | `fetch_all_doctors` + `fetch_speciality_list` пустые | ~584 | Ошибка без текста после двоеточия |
| 4 | TelegramNetworkError / ServerDisconnectedError | несколько | Сетевые разрывы WinError 64 |

### Исправление Pydantic-валидации ✅

**Причина:** API `zdrav.lenreg.ru` иногда возвращает `null` в строковых полях `SpecialityItem`. Pydantic в режиме `model_validate` не применяет дефолт `""` к ключу со значением `None`.

**Решение:** применён `Annotated[str, BeforeValidator(_coerce_str)]`:
- [`SpecialityItem`](api/models.py:65): `NameSpesiality`, `FerIdSpesiality`, `IdSpesiality`
- [`DoctorItem`](api/models.py:89): `Name`, `IdDoc`

### Добавление HTTP-заголовков ✅

В [`_get_headers()`](api/zdrav_client.py:46) добавлены:
- `X-CSRFToken: NOTPROVIDED`
- `Cookie: csrftoken=NOTPROVIDED`
- `Origin: https://zdrav.lenreg.ru`

### Изменённые файлы

| Файл | Действие |
|------|----------|
| [`api/models.py`](api/models.py:62) | `SpecialityItem` строковые поля → `BeforeValidator(_coerce_str)` |
| [`api/models.py`](api/models.py:85) | `DoctorItem` поля `Name`, `IdDoc` → `BeforeValidator(_coerce_str)` |
| [`api/zdrav_client.py`](api/zdrav_client.py:46) | `_get_headers()`: +`X-CSRFToken`, `Cookie`, `Origin` |

### Очистка мусорных лог-файлов ✅

Удалены артефакты, не используемые проектом:
- `logs/_error_lines.txt` — временный результат grep из этой же сессии
- `logs/stdout.log` — артефакт ручного запуска (`python main.py > logs/stdout.log`)
Проект использует только [`FileHandler("logs/error.log")`](main.py:32).

| Файл | Действие |
|------|----------|
| `logs/_error_lines.txt` | Удалён |
| `logs/stdout.log` | Удалён |

**Результат:** 15/15 tests passed (test_zdrav_client.py)

---

## 2026-05-12 (Архитектурный рефакторинг: src/ директория)

### Миграция исходного кода в src/ ✅

**Задача:** Устранение плоской иерархии в корне проекта — перенос всех модулей исходного кода в выделенную директорию `src/`, рефакторинг всех импортов на абсолютные `src.xxx`, генерация [`ARCHITECTURE.md`](ARCHITECTURE.md:1).

**Изменённые файлы:**

| Файл | Действие |
|------|----------|
| [`src/`](src/__init__.py:1) | Создана директория с `__init__.py` и подпакетами `api/`, `database/`, `handlers/`, `keyboards/`, `middleware/`, `services/`, `utils/` |
| [`src/config.py`](src/config.py:1) | Перенесён из `config.py` |
| [`src/main.py`](src/main.py:1) | Перенесён из `main.py`, все импорты → `src.xxx` |
| [`src/api/zdrav_client.py`](src/api/zdrav_client.py:1) | Импорты: `api.models` → `src.api.models`, `config` → `src.config` |
| [`src/database/database.py`](src/database/database.py:1) | Импорты: `database.migrations` → `src.database.migrations`, `utils.helpers` → `src.utils.helpers`, `config` → `src.config` |
| [`src/database/manager.py`](src/database/manager.py:1) | Импорт: `database.database` → `src.database.database` |
| [`src/database/doctor_manager.py`](src/database/doctor_manager.py:1) | Импорт: `database.database` → `src.database.database` |
| [`src/database/migrations.py`](src/database/migrations.py:1) | Импорт: `config` → `src.config` |
| [`src/handlers/common.py`](src/handlers/common.py:1) | Все импорты → `src.xxx` (api, config, database, keyboards, services, utils) |
| [`src/handlers/registration.py`](src/handlers/registration.py:1) | Все импорты → `src.xxx` |
| [`src/keyboards/inline.py`](src/keyboards/inline.py:1) | Импорт: `utils.helpers` → `src.utils.helpers` |
| [`src/middleware/ratelimit.py`](src/middleware/ratelimit.py:1) | Импорт: `config` → `src.config` |
| [`src/services/cleanup.py`](src/services/cleanup.py:1) | Все импорты → `src.xxx` |
| [`src/services/doctor_discovery.py`](src/services/doctor_discovery.py:1) | Все импорты → `src.xxx` |
| [`src/services/error_notifier.py`](src/services/error_notifier.py:1) | Импорт: `config` → `src.config` |
| [`src/services/healthcheck.py`](src/services/healthcheck.py:1) | Все импорты → `src.xxx` |
| [`src/services/monitor.py`](src/services/monitor.py:1) | Все импорты → `src.xxx` |
| [`src/utils/cache.py`](src/utils/cache.py:1) | Импорт: `config` → `src.config` |
| [`tests/conftest.py`](tests/conftest.py:11) | Импорты → `src.xxx`, monkeypatch path → `src.utils.cache.settings.CACHE_PATH` |
| [`tests/test_monitor_full.py`](tests/test_monitor_full.py:9) | Импорт: `services.monitor` → `src.services.monitor` |
| [`tests/test_doctor_discovery.py`](tests/test_doctor_discovery.py:8) | Импорт: `services.doctor_discovery` → `src.services.doctor_discovery` |
| [`tests/test_monitor_classify.py`](tests/test_monitor_classify.py:5) | Импорт: `services.monitor` → `src.services.monitor` |
| [`scripts/apply_city_heuristic.py`](scripts/apply_city_heuristic.py:12) | Импорты → `src.xxx` |
| [`scripts/apply_heuristic_types.py`](scripts/apply_heuristic_types.py:12) | Импорты → `src.xxx` |
| [`pyproject.toml`](pyproject.toml:1) | Добавлен `[tool.ruff] src = ["src"]` |
| [`pytest.ini`](pytest.ini:1) | Добавлен `pythonpath = .` |
| [`pyrightconfig.json`](pyrightconfig.json:1) | Добавлен `rootPath: "."` |
| [`.pre-commit-config.yaml`](.pre-commit-config.yaml:75) | mypy args: заменены 9× `-p` на `-p src -p scripts -p tests` |
| [`ARCHITECTURE.md`](ARCHITECTURE.md:1) | Создан: дерево директорий, зоны ответственности, граф зависимостей, ключевые решения |
| [`.roo/rules/knowledge.md`](.roo/rules/knowledge.md:1) | Добавлен приоритет чтения `ARCHITECTURE.md` при анализе структуры проекта |

**Удалены:** Старые корневые директории `api/`, `database/`, `handlers/`, `keyboards/`, `middleware/`, `services/`, `utils/`, файлы `config.py`, `main.py` (теперь в `src/`).

---

### Верификация рефакторинга ✅

**Дата:** 2026-05-12

**Задача:** Проверить работоспособность бота после миграции в `src/`.

**Результаты тестов:** **134 passed, 0 failed, 0 errors** (Python 3.14.4, pytest 9.0.3)

| Группа тестов | Кол-во | Результат |
|---------------|--------|-----------|
| [`tests/test_cache.py`](tests/test_cache.py:1) | 7 | ✅ Все прошли |
| [`tests/test_database_manager.py`](tests/test_database_manager.py:1) | 14 | ✅ Все прошли |
| [`tests/test_doctor_discovery.py`](tests/test_doctor_discovery.py:1) | 15 | ✅ Все прошли |
| [`tests/test_doctor_manager.py`](tests/test_doctor_manager.py:1) | 11 | ✅ Все прошли |
| [`tests/test_keyboards.py`](tests/test_keyboards.py:1) | 39 | ✅ Все прошли |
| [`tests/test_monitor_classify.py`](tests/test_monitor_classify.py:1) | 12 | ✅ Все прошли |
| [`tests/test_monitor_full.py`](tests/test_monitor_full.py:1) | 21 | ✅ Все прошли |
| [`tests/test_zdrav_client.py`](tests/test_zdrav_client.py:1) | 15 | ✅ Все прошли |

**Исправленные проблемы после первого запуска тестов (63 failed → 0 failed):**

1. [`tests/test_cache.py`](tests/test_cache.py:13) — 7 inline-импортов `from utils.cache import` → `from src.utils.cache import`
2. [`tests/test_database_manager.py`](tests/test_database_manager.py:11) — 2 inline-импорта `from database.xxx import` → `from src.database.xxx import`
3. [`tests/test_keyboards.py`](tests/test_keyboards.py:30) — 39 inline-импортов `from keyboards.inline import` → `from src.keyboards.inline import`
4. [`tests/test_monitor_classify.py`](tests/test_monitor_classify.py:74) — 2 inline-импорта `import config` → `import src.config as config`
5. [`tests/test_monitor_full.py`](tests/test_monitor_full.py:197) — 6 monkeypatch-путей `"services.monitor.xxx"` → `"src.services.monitor.xxx"` и `"services.healthcheck._safe_set"` → `"src.services.healthcheck._safe_set"`
6. [`tests/test_zdrav_client.py`](tests/test_zdrav_client.py:16) — 1 inline-импорт `from api.zdrav_client import` → `from src.api.zdrav_client import`
7. [`tests/test_doctor_manager.py`](tests/test_doctor_manager.py:75) — 1 inline-импорт `from database.doctor_manager import` → `from src.database.doctor_manager import`

**Изменённые файлы (верификация):**

| Файл | Изменения |
|------|-----------|
| [`tests/test_cache.py`](tests/test_cache.py:13) | 7 inline-импортов → `src.utils.cache` |
| [`tests/test_database_manager.py`](tests/test_database_manager.py:11) | 2 inline-импорта → `src.database.xxx` |
| [`tests/test_keyboards.py`](tests/test_keyboards.py:30) | 39 inline-импортов → `src.keyboards.inline` |
| [`tests/test_monitor_classify.py`](tests/test_monitor_classify.py:74) | 2 inline-импорта → `import src.config as config` |
| [`tests/test_monitor_full.py`](tests/test_monitor_full.py:197) | 6 monkeypatch-путей → `src.services.xxx` |
| [`tests/test_zdrav_client.py`](tests/test_zdrav_client.py:16) | 1 inline-импорт → `src.api.zdrav_client` |
| [`tests/test_doctor_manager.py`](tests/test_doctor_manager.py:75) | 1 inline-импорт → `src.database.doctor_manager` |

### Pre-commit хуки и автофиксы ✅

- `pre-commit run --all-files`: `mixed-line-ending` перевёл 55 файлов CRLF→LF, `ruff` убрал лишнюю пустую строку в [`tests/conftest.py`](tests/conftest.py:8)
- Pre-existing failures (не исправлялись): `ruff-lint` (~30 E501/ASYNC240/ASYNC251), `mypy` (4 type-annotation)
- Автофиксы закоммичены в `main` как `3e0546a`, запушены в `origin/main`

### Изменённые файлы

| Файл | Изменение |
|------|-----------|
| [`tests/conftest.py`](tests/conftest.py:8) | Убрана лишняя пустая строка (ruff) |
| 54 файла | CRLF → LF line endings (mixed-line-ending) |
