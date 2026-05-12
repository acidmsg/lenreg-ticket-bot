# Стандарты кодирования

## Обработка ошибок

- Явные проверки на `None` для `call.message`, `call.from_user` и подобных объектов aiogram.
- Различать типы исключений (не голый `except Exception`).
- Всегда логировать трассировку при перехвате ошибок API.

## Взаимодействие с API

- Все запросы включают заголовки: `X-Requested-With`, `Content-Type`, `X-CSRFToken`, `Cookie` (csrftoken), `Origin`, `Referer`.
- Rate limiting через `aiolimiter` — отдельные лимитеры для разных типов задач (мониторинг, discovery, healthcheck, пользовательские запросы).
- Retry для методов API: 3 попытки с задержкой 2 с на 5xx и сетевые ошибки.

## Конкурентность

- `asyncio.Lock` для атомарных операций с разделяемыми данными.
- `aiofiles` для асинхронного файлового I/O.
- `asyncio.Task` для фоновых задач; корректная отмена через `task.cancel()` + `asyncio.gather(return_exceptions=True)`.

## Хранение данных

- Runtime-данные (SQLite БД, файловый кэш) — в `data/`.
- Слой базы данных: [`src/database/database.py`](src/database/database.py) — ядро SQLite (WAL-режим, миграции), [`src/database/manager.py`](src/database/manager.py) — адаптер с in-memory кэшем, [`src/database/doctor_manager.py`](src/database/doctor_manager.py) — кэш справочника врачей.

## Конфигурация

- Конфиденциальные данные — только в `.env`, не хардкодить.
- Нечувствительные параметры — в БД (таблица `config`) с переопределением через `load_config_from_db()`.

## Тестирование

- Временные SQLite-файлы в `tests/test_data/`, очистка после сессии.
- Моки через `unittest.mock` и monkeypatch.
- `gc.collect()` в фикстурах для контроля памяти.
