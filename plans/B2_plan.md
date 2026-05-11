## План по замене `empty_counts` на `TTLCache`

**Цель:** Предотвратить утечку памяти, заменив бесконечно растущий `dict` `empty_counts` на `TTLCache` с ограниченным размером и временем жизни элементов.

**Подробные шаги:**

1. **Добавить `cachetools` в `requirements.txt`**: Убедиться, что библиотека `cachetools` указана в зависимостях проекта.
2. **Импортировать `TTLCache`**: Добавить импорт `TTLCache` из `cachetools` в [`services/monitor.py`](services/monitor.py:1).
3. **Инициализировать `TTLCache`**: Заменить инициализацию `empty_counts = {}` (строка 90) на `empty_counts = TTLCache(maxsize=settings.EMPTY_COUNTS_MAXSIZE, ttl=settings.EMPTY_COUNTS_TTL)`.
    * `settings.EMPTY_COUNTS_MAXSIZE`: Максимальное количество элементов в кэше.
    * `settings.EMPTY_COUNTS_TTL`: Время жизни элемента в секундах.
    * Эти параметры нужно будет добавить в `config.py`.
4. **Обновить использование `empty_counts`**: Убедиться, что все операции с `empty_counts` (получение, установка, инкремент) совместимы с API `TTLCache`. В данном случае, текущие операции `empty_counts[cache_key] = ...` и `empty_counts.get(cache_key, 0)` будут работать без изменений, так как `TTLCache` реализует интерфейс словаря.
5. **Добавить настройки в `config.py`**:
    * `EMPTY_COUNTS_MAXSIZE`: Например, `1000`.
    * `EMPTY_COUNTS_TTL`: Например, `3600` (1 час).
6. **Проверить смежные изменения**: Убедиться, что изменение не повлияет на логику работы с `swap_cache_key` и `_classify_slot_change`. (Предварительный анализ показывает, что не должно).
7. **Провести тестирование**:
    * Модульные тесты для `services/monitor.py` (если есть).
    * Интеграционные тесты для проверки поведения при отсутствии слотов и сброса счетчика.

**Mermaid Diagram:**

```mermaid
graph TD
    A[Начало] --> B{Задача: B2 - Утечка памяти в `empty_counts`}
    B --> C[Изменить `requirements.txt`]
    C --> D[Добавить `cachetools` в зависимости]
    D --> E[Изменить `config.py`]
    E --> F[Добавить `EMPTY_COUNTS_MAXSIZE` и `EMPTY_COUNTS_TTL`]
    F --> G[Изменить `services/monitor.py`]
    G --> H[Импортировать `TTLCache` из `cachetools`]
    H --> I[Заменить `empty_counts = {}` на `TTLCache(...)`]
    I --> J[Проверить использование `empty_counts` в коде]
    J --> K[Проверить смежные изменения]
    K --> L[Тестирование]
    L --> M[Завершение]
