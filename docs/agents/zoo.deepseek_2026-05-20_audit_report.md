# Комплексный аудит проекта zdrav.lenreg — Executive Summary

**Дата:** 2026-05-20
**Модель:** zoo.deepseek (orchestrator + project-research + code + architect + debug + documentation-writer)
**Охват:** 7 фаз, 38 модулей `src/`, 185 тестов, 6 инфраструктурных файлов
**Метод:** делегирование специализированным режимам

---

## Общая статистика

| Метрика                   | Значение                                                     |
| ------------------------- | ------------------------------------------------------------ |
| Всего найдено проблем     | **80** (без учёта уязвимостей зависимостей)                  |
| Critical                  | **6**                                                        |
| Major                     | **37**                                                       |
| Minor                     | **37**                                                       |
| Уязвимости в зависимостях | **4** (idna, pytest, urllib3 ×2)                             |
| Автоматические проверки   | **5/6 PASS** (ruff, mypy, pytest, ruff format, markdownlint) |
| Spec-First Compliance     | **78/100**                                                   |
| Покрытие тестами          | **31.6%** модулей                                            |
| ARCHITECTURE.md полнота   | **45/100**                                                   |
| pytest                    | **185/185 passed**                                           |

---

## 🔴 CRITICAL (6 проблем — требуют немедленного исправления)

### C1. Docker multistage-сборка: финальный образ не содержит Python-зависимостей

- **Severity:** critical
- **Приоритет:** high
- **Файл:** [`Dockerfile:72`](Dockerfile:72)
- **Описание:** `COPY --from=builder /root/.local` копирует неверный путь. Poetry с `virtualenvs.create false` устанавливает пакеты в системные site-packages, а не в `/root/.local`. Контейнер упадёт с `ModuleNotFoundError` при запуске.
- **Рекомендация:** `COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages`

### C2. CI использует несуществующие версии GitHub Actions

- **Severity:** critical
- **Приоритет:** high
- **Файл:** [`.github/workflows/ci.yml:23-26`](.github/workflows/ci.yml:23)
- **Описание:** `actions/checkout@v6` и `actions/setup-python@v6` не существуют. Актуальные: `@v4` и `@v5`. CI сломан на первом шаге.
- **Рекомендация:** `actions/checkout@v4`, `actions/setup-python@v5`

### C3. Реальные ID пациентов захардкожены в коде

- **Severity:** critical
- **Приоритет:** high
- **Файл:** [`src/config.py:70-71`](src/config.py:70)
- **Описание:** `DISCOVERY_PATIENT_ID_ADULT="2343192"` и `DISCOVERY_PATIENT_ID_CHILD="2509768"` как default-значения. Это PII-данные (персональные идентификаторы пациентов), которые попадают в репозиторий и Docker-образ.
- **Рекомендация:** Убрать default-значения, оставить только `.env`; в `.env.example` заменить на `your_discovery_patient_id_adult_here`

### C4. Отсутствует retry-логика в `fetch_patient_id`

- **Severity:** critical
- **Приоритет:** high
- **Файл:** [`src/api/zdrav_client.py:156-193`](src/api/zdrav_client.py:156)
- **Описание:** Единственный метод API-клиента без retry (3 попытки). При сбое `/check_patient/` пользователь сразу получает ошибку.
- **Рекомендация:** Добавить retry-цикл `for i in range(3)` по образцу `fetch_speciality_list`

### C5. Отсутствуют поля `doctor_form-history_id` и `doctor_form-appointment_type` в `check_slots`

- **Severity:** critical
- **Приоритет:** high
- **Файл:** [`src/api/zdrav_client.py:294-298`](src/api/zdrav_client.py:294)
- **Описание:** Спецификация требует эти поля в `AppointmentListRequest`, но payload их не содержит.
- **Рекомендация:** Добавить `doctor_form-history_id: ""` и `doctor_form-appointment_type: ""`

### C6. CI не запускает markdownlint и prettier

- **Severity:** critical
- **Приоритет:** high
- **Файл:** [`.github/workflows/ci.yml`](.github/workflows/ci.yml)
- **Описание:** В пайплайне отсутствуют шаги проверки markdown-файлов.
- **Рекомендация:** Добавить шаги `markdownlint` и `prettier --check`

---

## 🟠 MAJOR (37 проблем — приоритетные к исправлению)

### Архитектура и Spec-First (7 major)

- **M1-M3:** 403/429 не обрабатываются в `fetch_speciality_list`, `fetch_all_doctors`, `fetch_clinic_list` ([`zdrav_client.py`](src/api/zdrav_client.py))
- **M4:** Таблица `monitoring_log` отсутствует в openapi.yaml ([`migrations.py:74`](src/database/migrations.py:74))
- **M5:** 15 полей конфигурации Settings отсутствуют в openapi.yaml `AppConfig` ([`config.py`](src/config.py))
- **M6:** Веб-дашборд (FastAPI, 7+ эндпоинтов) полностью не документирован в openapi.yaml
- **M7:** `ClinicListRequest` определён inline вместо `$ref` в openapi.yaml

### Качество кода (6 major)

- **M8:** Вводящее в заблуждение сообщение об ошибке в `fetch_patient_id` — всегда `api-timeout` ([`zdrav_client.py:190`](src/api/zdrav_client.py:190))
- **M9:** Отсутствие `exc_info=True` при логировании ошибок API во всех методах клиента
- **M10:** Синхронный файловый I/O в `export.py` — `tempfile.NamedTemporaryFile` блокирует event loop ([`export.py:53`](src/services/export.py:53))
- **M11:** Полное подавление проверок типов в `redis.py` — `# mypy: ignore-errors` на весь файл ([`redis.py:8`](src/utils/redis.py:8))
- **M12:** `.env.example` не содержит 7 ключей из `Settings`: `CHECK_INTERVAL`, `DISCOVERY_INTERVAL`, `CLEANUP_INTERVAL`, `SLOT_DETAIL_THRESHOLD`, `SLOT_COMPACT_THRESHOLD`, `DENTAL_CLINIC_ID`, `SIGNUP_URL`
- **M13:** Healthcheck Docker проверяет файл БД, а не живость процесса бота ([`Dockerfile:83`](Dockerfile:83))

### Документация (11 major)

- **M14-M22:** ARCHITECTURE.md: отсутствуют модули `filters/`, `i18n/`, `web/`; middleware описан на 25%; services на 62%; utils на 60%; структура тестов неверна; имена `.roo/rules/` полностью не совпадают; Mermaid-граф не содержит 15+ узлов
- **M23:** Только 12 из ~28 схем имеют JSON-файлы в `docs/schemas/`
- **M24:** `CSRF_TOKEN` в `.env.example` указан как `your_csrf_token_here` вместо статического `NOTPROVIDED`

### Тесты (3 major)

- **M25:** Тесты API-клиента не покрывают `fetch_clinic_list`, retry на сетевые ошибки, rate limiter, Pydantic-валидацию
- **M26:** DatabaseManager: ~60% методов не тестируются напрямую; Database не тестируется изолированно
- **M27:** Обработчики: отсутствуют edge cases с ошибками API, `from_user=None`, `del_p_no`

### Инфраструктура (10 major)

- **M28-M37:** CI не запускает `ruff format --check` и сборку Docker; `prettier` не в `devDependencies`; Makefile `clean` несовместим с Windows; healthcheck `start_period` расходится (30s vs 60s); pytest подавляет все DeprecationWarning глобально; `check-merge-conflict` отсутствует в pre-commit; markdownlint-cli v0.44 требует Node 18

---

## 🟡 MINOR (37 проблем — рекомендации)

### Spec-First (6 minor)

- Отсутствуют Pydantic request-модели (тела запросов формируются как сырые `dict`)
- `LastDate`/`NearestDate`: nullable в коде, не-nullable в спецификации
- `PatientInfo.clinic_id` не документирован в `DB_Patient`
- Устаревшие номера строк в описаниях openapi.yaml
- 4 чувствительных поля конфигурации отсутствуют в `AppConfig`
- `ClinicInfo` TypedDict не включает discovery-поля

### Качество кода (6 minor)

- Подавление ошибок WAL checkpoint без реального логирования
- Подавление ошибок сидирования БД без `exc_info=True`
- `except Exception` в `_send_notification` без `exc_info`
- Прямой доступ к `db._db` в обход `DatabaseManager` в `cleanup.py`
- Использование `Any` вместо конкретных типов в `schema_watcher.py`
- Отсутствие type hint для параметра `limiter` в `doctor_discovery.py`
- Несогласованное поведение `get_config()` при отсутствии соединения

### Документация (7 minor)

- README.md: неточный интервал мониторинга «60 секунд»
- README.md: раздел «Разработка» не упоминает schema_watcher и web dashboard
- openapi.yaml: `contact` не содержит email/url
- openapi.yaml: `RateLimitConfig` — пустые properties
- Нет `clinic_list.md` в `docs/knowledge/`
- `knowledge/_INDEX.md` не упоминает `clinic_list`
- README.md актуальнее ARCHITECTURE.md в части middleware и utils

### Тесты (11 minor)

- Тесты регистрации не проверяют сценарий ошибки API в `process_bday`
- Тесты мониторинга: отсутствует тест частичного сбоя API
- Дублирование фабрик в `test_handlers_registration.py`
- `export.py`: тесты не проверяют сценарий с несколькими пользователями и спецсимволами
- `test_keyboards.py`: отсутствуют edge cases с пустыми данными
- Устаревшая фикстура `clear_spam_cache`
- Синхронные операции в асинхронной фикстуре `temp_db_path`
- `pytest_sessionfinish`: нет логирования при ошибке очистки

### Инфраструктура (7 minor)

- `check-merge-conflict` отсутствует в pre-commit
- `markdownlint-cli` v0.44 требует Node 18 (не задокументировано)
- `prettier` не указан в `devDependencies` package.json
- Placeholder-поля в package.json (`description`, `repository`)
- Глобальное подавление `DeprecationWarning` в pytest.ini
- `filterwarnings` в pytest.ini дублируется с pyproject.toml
- `pyrightconfig.json`: `typeCheckingMode: "basic"` вместо `"strict"`

---

## 📊 Сводка по областям

| Область                 | Оценка | Critical | Major | Minor |
| ----------------------- | ------ | -------- | ----- | ----- |
| Автоматические проверки | ✅ 5/6 | 0        | 0     | 1     |
| Spec-First Compliance   | 🟡 78% | 2        | 7     | 6     |
| Качество кода           | 🟢     | 0        | 6     | 6     |
| Документация            | 🔴     | 0        | 11    | 7     |
| Тесты                   | 🟡 32% | 0        | 3     | 11    |
| Инфраструктура          | 🔴     | 4        | 10    | 7     |
| Безопасность            | 🟡     | 1        | 0     | 1     |

---

## 🎯 Приоритетный план исправлений (Roadmap)

### Фаза 0: Критические исправления (день 1)

1. Исправить Docker multistage-сборку — иначе контейнер не запустится
2. Исправить версии GitHub Actions в CI — иначе CI сломан
3. Убрать хардкод ID пациентов из `config.py`
4. Добавить retry в `fetch_patient_id`
5. Добавить недостающие поля в `check_slots`
6. Добавить markdownlint + prettier в CI

### Фаза 1: Инфраструктура и безопасность (день 1-2)

1. Добавить `ruff format --check` в CI
1. Синхронизировать `.env.example` с `Settings` (добавить 7 ключей)
1. Исправить healthcheck Docker
1. Обновить уязвимые зависимости: `idna` (→3.15), `pytest` (→9.0.3), `urllib3` (→2.7.0)
1. Исправить `CSRF_TOKEN` в `.env.example` на `NOTPROVIDED`

### Фаза 2: Документация (день 2-3)

1. Полная ресинхронизация ARCHITECTURE.md (модули, дерево, Mermaid, тесты)
1. Добавить веб-дашборд эндпоинты в openapi.yaml
1. Синхронизировать openapi.yaml `AppConfig` (+15 полей)
1. Сгенерировать недостающие JSON-схемы в `docs/schemas/`
1. Создать `docs/knowledge/clinic_list.md`

### Фаза 3: Код и тесты (день 3-5)

1. Добавить `exc_info=True` в логирование ошибок API
1. Заменить синхронный I/O на `aiofiles` в `export.py`
1. Точечно подавить проверки типов в `redis.py` вместо файла целиком
1. Написать тесты для `healthcheck.py`, `middleware/*`, `schema_watcher.py`, `config.py`
1. Расширить тесты API-клиента (`fetch_clinic_list`, retry, rate limiter)
1. Расширить тесты DatabaseManager (логирование, конфигурация, клиники/врачи)

---

## ✅ Сильные стороны проекта

- **Чистый код:** 0 ошибок Ruff, 0 ошибок mypy, 185/185 тестов
- **Качественный API-клиент:** rate limiting, User-Agent ротация, валидация Pydantic
- **Graceful degradation:** Redis-зависимости корректно деградируют
- **Двухуровневая конфигурация:** `.env` → pydantic → БД с приведением типов
- **Хорошо покрытый мониторинг:** классификация слотов протестирована исчерпывающе
- **Качественный conftest.py:** in-memory Redis fallback, очистка, tracemalloc-профилирование
- **OpenAPI-спецификация:** детально описывает контракты (30+ схем, заголовки, коды ошибок)
- **Полная контейнеризация:** двухэтапный Dockerfile (с поправкой на баг), docker-compose с healthcheck
