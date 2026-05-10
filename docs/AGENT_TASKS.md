# Task Tracker для агента

## Легенда

- ✅ **Выполнено** — задача завершена
- 🔄 **В процессе** — задача в работе
- ⬜ **Не начато** — задача ещё не начата
- 📌 **Бэклог** — запланировано на будущее

---

## Завершённые задачи (2026-05-07 / 2026-05-08)

### Тесты

| # | Задача | Статус | Примечание |
|---|---|---|---|
| 1 | Создать тестовую инфраструктуру (conftest, фикстуры, моки) | ✅ | `tests/conftest.py` |
| 2 | Unit-тесты для DatabaseManager | ✅ | 14 тестов, все проходят |
| 3 | Unit-тесты для DoctorManager | ✅ | 7 тестов, все проходят |
| 4 | Unit-тесты для utils/cache | ✅ | 12 тестов, все проходят |
| 5 | Unit-тесты для `_classify_slot_change()` | ✅ | 12 тестов, все проходят |
| 6 | Unit-тесты для ZdravClient (mocked HTTP) | ✅ | 20 тестов, все проходят |
| 7 | Установить и настроить pytest + pytest-asyncio | ✅ | `pytest.ini`, `requirements.txt` |

### Healthcheck

| # | Задача | Статус | Примечание |
|---|---|---|---|
| 8 | Создать модуль healthcheck | ✅ | `services/healthcheck.py` |
| 9 | Реализовать `HealthMetrics` dataclass | ✅ | uptime, статистика API, ошибки |
| 10 | Реализовать `healthcheck_loop()` | ✅ | Фоновый цикл проверки API |
| 11 | Реализовать `format_status_report()` | ✅ | Форматирование отчёта |
| 12 | Добавить команду `/status` | ✅ | `handlers/common.py` |
| 13 | Интегрировать healthcheck в `main.py` | ✅ | Фоновая задача + graceful shutdown |
| 14 | Интегрировать метрики в monitor_loop | ✅ | Обновление `metrics.monitor_loop_alive` |
| 15 | Зарегистрировать discovery-задачи в метриках | ✅ | `metrics.discovery_tasks_alive` |

### SQLite-миграция (ночная сессия 2026-05-07)

| # | Задача | Статус | Примечание |
|---|---|---|---|
| D2 | Переход с JSON на SQLite | ✅ | `database/database.py`, миграция из JSON |
| 23 | Создать `database/database.py` — единый SQLite-движок | ✅ | Таблицы users, clinics, doctors |
| 24 | Переписать `DatabaseManager` на SQLite (адаптер) | ✅ | Полная обратная совместимость |
| 25 | Переписать `DoctorManager` на SQLite (адаптер) | ✅ | Загрузка из SQLite в кэш |
| 26 | Исправить `reportOptionalMemberAccess` в database.py | ✅ | `assert c is not None` во всех методах |
| 27 | Обновить `config.py` (DB_PATH → bot.db) | ✅ | `data/bot.db` |
| 28 | Обновить `main.py` (новая инициализация + миграция) | ✅ | `run_migration=True` |
| 29 | Обновить тесты под SQLite (conftest, manager, doctor) | ✅ | 64 теста, все проходят |

### Исправления

| # | Задача | Статус | Примечание |
|---|---|---|---|
| 16 | Исправить валидацию IdDoc в DoctorManager | ✅ | Строгая проверка на None |
| 17 | Исправить Pylance-предупреждения в healthcheck.py | ✅ | Удалены неиспользуемые импорты |
| 18 | Исправить Pylance-предупреждения в conftest.py | ✅ | Удалены дублирующие фикстуры |

### Исправления Pylance (вечерняя сессия 2026-05-07)

| # | Задача | Статус | Примечание |
|---|---|---|---|
| 19 | Исправить `reportOperatorIssue` в test_monitor_classify.py:54 | ✅ | Добавлен `assert display_slots is not None` |
| 20 | Исправить `reportOptionalIterable` в test_monitor_classify.py:111 | ✅ | Добавлен `assert display_slots is not None` |
| 21 | Исправить `reportArgumentType` в test_zdrav_client.py:24 | ✅ | Аннотация `dict = None` → `dict \| None = None` |
| 22 | Настроить Pylance на `.venv` | ✅ | Создан `pyrightconfig.json`, установлены пакеты в `.venv` |

### Ревью SQLite (вечерняя сессия 2026-05-08)

| # | Задача | Статус | Примечание |
|---|---|---|---|
| 30 | Анализ SQLite-реализации (код + тесты) | ✅ | 64 теста, найдено 8 проблем |
| 31 | P1 — единая транзакция в `update_user()` | ✅ | BEGIN / COMMIT / ROLLBACK |
| 32 | P2 — whitelist полей в `update_user_field()` | ✅ | `_ALLOWED_FIELDS` frozenset |
| 33 | P3 — `data` → deepcopy | ✅ | Защита от мутации кэша |
| 34 | P5 — убран shallow copy в `monitor_loop()` | ✅ | Deepcopy уже делает `db.data` |
| 35 | P7 — все `assert c is not None` → `raise RuntimeError` | ✅ | Production-безопасность |
| 36 | P8 — удалён закомментированный import | ✅ | Чистота кода |
| 37 | P9 — упрощён INSERT в `ensure_user()` | ✅ | 1 параметр, 1 плейсхолдер |

### Документация

| # | Задача | Статус | Примечание |
|---|---|---|---|
| 19 | Создать лог сессии 2026-05-07 | ✅ | `docs/SESSION_2026-05-07.md` |
| 20 | Создать task tracker | ✅ | `docs/AGENT_TASKS.md` |
| 21 | Восстановить лог сессии 2026-05-01 | ✅ | `docs/SESSION_2026-05-01.md` (из DEVELOPMENT_HISTORY.md) |
| 22 | Восстановить лог сессии 2026-05-03 | ✅ | `docs/SESSION_2026-05-03.md` (из DEVELOPMENT_HISTORY.md) |
| 23 | Восстановить лог сессии 2026-05-04 | ✅ | `docs/SESSION_2026-05-04.md` (из DEVELOPMENT_HISTORY.md) |
| 24 | Восстановить лог сессии 2026-05-05 | ✅ | `docs/SESSION_2026-05-05.md` (из DEVELOPMENT_HISTORY.md) |
| 25 | Восстановить лог сессии 2026-05-06 | ✅ | `docs/SESSION_2026-05-06.md` (из SESSION_LOG.md) |
| 26 | Создать лог сессии 2026-05-08 | ✅ | `docs/SESSION_2026-05-08.md` |

### Перенос иконок (вечерняя сессия 2026-05-08)

| # | Задача | Статус | Примечание |
|---|---|---|---|
| 38 | Перенести иконки из main в test (handlers/common.py) | ✅ | 👋, 📋, 🏥, ❌, ⚙️, ⏳, 🤷‍♂️, 🔗, 🧑‍⚕️, 👤 |
| 39 | Перенести иконки из main в test (handlers/registration.py) | ✅ | ✅, ❌, 📋 |
| 40 | Перенести иконки из main в test (keyboards/inline.py) | ✅ | 🔍, 🛑, 👤, 🗑, ➕, ✅, ▫️, ⬅️, ❌ |
| 41 | Коммит `df8225e` | ✅ | "перенесены иконки из main в test..." |

### Финальная чистка JSON (вечерняя сессия 2026-05-08)

| # | Задача | Статус | Примечание |
|---|---|---|---|
| 42 | Исправить `get_doctors_for_clinic()` на чтение из SQLite | ✅ | `handlers/common.py` — удалена старая функция |
| 43 | Убрать JSON-пути из `config.py` | ✅ | Удалены `DOCTORS_PATH`, `USERS_JSON_PATH`, `DOCTORS_JSON_PATH` |
| 44 | Убрать `DOCTORS_PATH` из `.env` и `.env.example` | ✅ | |
| 45 | Удалить `data/doctors.json` и `data/users_config.json` | ✅ | 🗑 |
| 46 | Захардкодить пути миграции в `manager.py` | ✅ | Убрана зависимость от `settings` |
| 47 | Проверить тесты (64/64) | ✅ | Все тесты проходят |
| 48 | Коммит `c7d7384` | ✅ | "финальная чистка JSON..." |

### UI/UX улучшения (вечерняя сессия 2026-05-08)

| # | Задача | Статус | Примечание |
|---|---|---|---|
| 49 | Счётчик врачей в кнопках клиник | ✅ | `get_clinic_selection()` |
| 50 | Кабинеты внизу списка без специальности | ✅ | `is_cabinet()` + разделение списков |
| 51 | Псевдонимы ФИО и специальностей | ✅ | `shorten_fio()`, `shorten_specialty()` |
| 52 | Убрать разделитель "Кабинеты" | ✅ | Кнопки идут подряд |
| 53 | Убрать alert при повторном нажатии | ✅ | Тихое игнорирование (spam_cache) |
| 54 | Кнопка сброса всего мониторинга | ✅ | `stop_all` на главной |
| 55 | Кнопка сброса мониторинга пациента | ✅ | `stop_patient_` на странице клиник |
| 56 | Кнопка сброса мониторинга клиники | ✅ | `stop_clinic_` на странице врачей |
| 57 | Удаление сообщений при отключении/сбросе | ✅ | `bot.delete_message()` во всех сценариях |
| 58 | `delete_cache_keys_by_prefix()` | ✅ | `utils/cache.py` |
| 59 | Создан `utils/helpers.py` | ✅ | `is_cabinet`, `shorten_fio`, `shorten_specialty` |
| 60 | Коммит и пуш | ✅ | |

### Устранение хардкодов (сессия 2026-05-09, ч.2)

| # | Задача | Статус | Примечание |
|---|---|---|---|
| 61 | Аудит хардкодов по всему проекту | ✅ | Найдено 8 проблем |
| 62 | `config.py` — новые настройки (API_BASE_URL, REFERER_URL, CSRF_TOKEN, DEFAULT_CLINIC_ID, DEFAULT_BIRTHDAY) | ✅ | |
| 63 | `api/zdrav_client.py` — вынос URL, Referer, CSRF в settings | ✅ | |
| 64 | `handlers/registration.py` — исправлена битая UTF-8 кодировка | ✅ | Были кракозябры вместо русского текста |
| 65 | `handlers/registration.py` — clinic_id "272" → settings.DEFAULT_CLINIC_ID | ✅ | |
| 66 | `services/doctor_discovery.py` — "161" → CLINICS_REGISTRY | ✅ | Двойной discovery для стоматологии (adult + child) |
| 67 | `keyboards/inline.py` — дублирование clinics → import CLINICS_REGISTRY | ✅ | |
| 68 | `handlers/common.py` — "1990-01-01" → settings.DEFAULT_BIRTHDAY (3 места) | ✅ | |
| 69 | `services/monitor.py` — "272" → settings.DEFAULT_CLINIC_ID | ✅ | |
| 70 | Тесты пройдены (64/64) | ✅ | |
| 71 | Обновлён лог сессии docs/SESSION_2026-05-09.md | ✅ | |

### Аудит и оптимизация inline-клавиатур (сессия 2026-05-10)

| # | Задача | Статус | Примечание |
|---|---|---|---|
| 72 | Проверка `keyboards/inline.py` на неактуальные строки | ✅ | Найдено: `get_main_menu()`, `from aiogram import types`, `ReplyKeyboardBuilder` |
| 73 | Удалён мёртвый код: `get_main_menu()`, `types`, `ReplyKeyboardBuilder` | ✅ | 3 неактуальных конструкции |
| 74 | Исправлен импорт в `handlers/common.py` | ✅ | Убран `get_main_menu` из импорта |
| 75 | Создан отчёт `docs/inline_review_report.md` | ✅ | Полный анализ callback_data и функций |

### Исправление /status и проверка healthcheck.py (сессия 2026-05-10, ч.2)

| # | Задача | Статус | Примечание |
|---|---|---|---|
| 76 | Диагностика: хэндлер `/status` отсутствовал в роутерах | ✅ | Функция `format_status_report()` была, но не было роутера |
| 77 | Добавлен хэндлер `cmd_status` в `handlers/common.py` | ✅ | Проверка прав через `settings.ADMIN_IDS` |
| 78 | Убран неиспользуемый параметр `api` из `format_status_report()` | ✅ | `services/healthcheck.py` |
| 79 | Добавлена настройка `ADMIN_IDS` в `config.py` и `.env.example` | ✅ | Список Telegram ID администраторов |
| 80 | Аудит `healthcheck.py` на актуальность | ✅ | Все импорты используются, мёртвого кода нет |
| 81 | ADMIN_IDS: `list[int]` → `str` (строка с разделителями) | ✅ | В .env без квадратных скобок, единообразно с др. ID |
| 82 | `.env.example` — все значения заменены на плейсхолдеры | ✅ | Без реальных данных пользователя |

## Задачи в бэклоге

### Тесты

| # | Задача | Приоритет | Примечание |
|---|---|---|---|
| T1 | Интеграционные тесты для хендлеров (mocked aiogram) | 🟡 Средний | Требует глубокого мокинга aiogram |
| T2 | Тесты для `services/monitor.py` (весь цикл) | 🟡 Средний | Нужно мокать API + Bot |
| T3 | Тесты для `services/doctor_discovery.py` | 🟢 Низкий | Менее критично |
| T4 | Тесты для `keyboards/inline.py` | 🟢 Низкий | UI-логика |
| T5 | Настроить CI (GitHub Actions) | ✅ | `.github/workflows/ci.yml` — тесты при push/PR в main |

### Инфраструктура

| # | Задача | Приоритет | Примечание |
|---|---|---|---|
| D1 | Docker-контейнеризация (Dockerfile + docker-compose.yml) | 🟡 Средний | Упростит развёртывание |
| D2 | Переход с JSON на SQLite/PostgreSQL | ✅ | `database/database.py` |
| D3 | Healthcheck endpoint через Telegram | 🟢 Низкий | Уже реализована команда /status |
| D4 | Добавить миграции данных | 🟡 Средний | При смене структуры JSON/SQL |

### Мониторинг и алертинг

| # | Задача | Приоритет | Примечание |
|---|---|---|---|
| M1 | Экспорт метрик в Prometheus | 🟢 Низкий | Для прод-окружения |
| M2 | Интеграция с Sentry/NTFY для ошибок | 🟡 Средний | Уведомления об ошибках |
| M3 | Rate limiting на уровне пользователя | 🟡 Средний | Сейчас только глобальный |

### Улучшения кода

| # | Задача | Приоритет | Примечание |
|---|---|---|---|
| R1 | Вынести discovery patient ID в .env или реестр клиник | 🟡 Средний | Сейчас жёстко закодированы |
| R2 | Использовать Redis для кэша вместо JSON-файла | 🟡 Средний | Производительность |
| R3 | Pre-commit hooks (форматтеры, линтеры) | 🟢 Низкий | Качество кода |
| R4 | Исправить Pydantic deprecation (Config -> ConfigDict) | ✅ | `config.py` — заменено на `SettingsConfigDict` |

### Новый функционал

| # | Задача | Приоритет | Примечание |
|---|---|---|---|
| F1 | Поддержка выбора нескольких пациентов в одном сообщении | 🟢 Низкий | UX |
| F2 | Возможность настроить интервал мониторинга для каждого врача | 🟢 Низкий | Гибкость |
| F3 | Статистика "сколько раз слоты появлялись за период" | 🟢 Низкий | Аналитика |
| F4 | Фильтрация врачей в стоматологии по возрасту пациента | ✅ | `utils/helpers.py` — is_child(); `keyboards/inline.py` — фильтр по "детск"; `handlers/common.py` — передача bday |

---

## Примечания для агента

### Как запустить тесты

```bash
python -m pytest tests/ -v --tb=short
```

### Ключевые конфигурационные файлы

| Файл | Назначение |
|---|---|
| `config.py` | Настройки, реестр клиник |
| `pytest.ini` | Конфигурация pytest (asyncio_mode = auto) |
| `requirements.txt` | Зависимости (prod + dev) |

### SQLite (database.py)

```python
from database.database import Database
from database.manager import DatabaseManager

# Инициализация
database = Database("data/bot.db")
db = DatabaseManager(database)
await db.load(run_migration=True)  # миграция из JSON при первом запуске

# Доступные таблицы
# users: uid TEXT PK, patients JSON, monitoring JSON, last_messages JSON, extra JSON
# clinics: clinic_id TEXT PK, name TEXT
# doctors: clinic_id TEXT, doctor_id TEXT, name TEXT, specialty TEXT
```

### Глобальный healthcheck-объект

```python
from services.healthcheck import metrics

# Доступные поля:
metrics.start_time           # Время запуска
metrics.api_checks_total     # Всего проверок API
metrics.api_errors_total     # Ошибок API
metrics.monitor_loop_alive   # Жив ли monitor_loop
metrics.healthcheck_loop_alive  # Жив ли healthcheck_loop
metrics.discovery_tasks_alive   # Количество discovery-задач
```

### Как запустить миграцию из JSON

```bash
# Автоматически выполняется при bot.db не существует
# или когда таблица users пуста.
# Пути к JSON: settings.USERS_JSON_PATH, settings.DOCTORS_JSON_PATH
```

### Структура тестов

```
tests/
├── conftest.py                    # Фикстуры (SQLite, временные файлы, моки)
├── test_database_manager.py       # DatabaseManager (15 тестов)
├── test_doctor_manager.py         # DoctorManager (7 тестов)
├── test_cache.py                  # utils/cache (12 тестов)
├── test_monitor_classify.py       # _classify_slot_change (12 тестов)
└── test_zdrav_client.py           # ZdravClient mocked HTTP (20 тестов)
