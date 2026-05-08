# Теперь я проведу полный ревью кода проекта. Это Telegram-бот для мониторинга свободных талонов к врачам в поликлиниках Ленинградской области (zdrav.lenreg.ru)

## 📋 Ревью кода проекта lenreg_ticket_bot

### ✅ **Сильные стороны**

1. **Хорошая архитектура**:
    - Чёткое разделение на слои (API, handlers, services, database, utils)
    - Использование Router для хендлеров aiogram
    - Асинхронная архитектура с правильным использованием asyncio
2. **Надёжное хранение данных**:
    - Переход с JSON на SQLite с атомарными транзакциями
    - Автоматическая миграция из JSON при первом запуске
    - WAL-режим для лучшей производительности SQLite
3. **Защита от внешних API проблем**:
    - Rate limiting (aiolimiter) для запросов к API
    - Retry-логика при ошибках 5xx
    - Защита от блокировок (403/429)
    - Random User-Agent ротация
4. **Кэширование и защита от дубликатов**:
    - TTLCache для spam protection
    - Атомарные операции с кэш-файлом через lock
    - Функция `swap_cache_key` для предотвращения TOCTOU race conditions
5. **Graceful shutdown**:
    - Правильная отмена фоновых задач
    - Закрытие HTTP-сессий и бота
6. **Мониторинг и observability**:
    - Healthcheck-цикл с метриками
    - Команда /status для проверки состояния
    - Логирование с разными уровнями
7. **Тесты**:
    - Покрытие тестами ключевых компонентов
    - Использование pytest-asyncio и моков

---

### ⚠️ **Критические проблемы и рекомендации**

#### 1. **Безопасность — Hardcoded данные**

**Файл**: `config.py`

```python
DISCOVERY_PATIENT_ID_ADULT: str = "2343192"
DISCOVERY_PATIENT_ID_CHILD: str = "2509768"
```

**Проблема**: ID пациентов захардкожены. Это может быть нарушением приватности и создаёт риски.

**Рекомендация**:

- Вынести в `.env` как sensitive data
- Добавить предупреждение в README о необходимости использовать тестовые аккаунты

---

#### 2. **Гонки данных в DatabaseManager.get_user_data()**

**Файл**: `database/manager.py`, строки 38-54

```python
def get_user_data(self, uid: str) -> Dict[str, Any]:
    """Синхронный метод для обратной совместимости."""
    uid = str(uid)
    if uid not in self._data_cache:
        # Создаём структуру по умолчанию
        self._data_cache[uid] = { ... }
```

**Проблема**: Синхронный метод модифицирует кэш без lock'а. При конкурентном доступе из разных корутин возможна гонка данных.

**Рекомендация**:

```python
async def get_user_data(self, uid: str) -> Dict[str, Any]:
    async with self._cache_lock:
        if uid not in self._data_cache:
            await self._ensure_user_in_db(uid)
            user = await self._db.get_user(uid)
            if user:
                self._data_cache[uid] = user
            else:
                self._data_cache[uid] = { ... }
        return self._data_cache[uid].copy()  # Возвращать копию!
```

---

#### 3. **Отсутствие валидации входных данных от API**

**Файл**: `api/zdrav_client.py`, строки 161-170

```python
data = res.json().get("response", {})
# ...
for date, items in data.items():
    for s in items:
        t = s.get("date_start", {}).get("time")
```

**Проблема**: Нет проверки типов данных. Если API изменит формат ответа, код упадёт с исключением.

**Рекомендация**: Добавить валидацию через pydantic модели:

```python
from pydantic import BaseModel, Field

class SlotInfo(BaseModel):
    date_start: dict[str, str]
class AppointmentResponse(BaseModel):
    slots: list[SlotInfo] = Field(default_factory=list)
```

---

#### 4. **Потенциальная утечка памяти в monitor_loop**

**Файл**: `services/monitor.py`, строка 91

```python
empty_counts = {}
```

**Проблема**: Словарь `empty_counts` растёт неограниченно для каждого нового `cache_key`. Старые ключи никогда не удаляются.

**Рекомендация**:

```python
from cachetools import TTLCache
empty_counts = TTLCache(maxsize=10000, ttl=3600)  # TTL 1 час
```

Или периодически очищать:

```python
# В конце каждого цикла
if len(empty_counts) > 1000:
    old_keys = list(empty_counts.keys())[:500]
    for k in old_keys:
        del empty_counts[k]
```

---

#### 5. **Небезопасное использование f-string для SQL**

**Файл**: `database/database.py`, строка 254

```python
await c.execute(
    f"UPDATE users SET {field} = ? WHERE uid = ?",
    (json.dumps(value, ensure_ascii=False), uid),
)
```

**Проблема**: Хотя значение параметризировано, имя поля подставляется напрямую. Теоретически возможна SQL-инъекция если `field` контролируется пользователем.

**Рекомендация**:

```python
ALLOWED_FIELDS = {"patients", "monitoring", "last_messages"}
if field not in ALLOWED_FIELDS:
    raise ValueError(f"Invalid field: {field}")
```

---

#### 6. **Отсутствие обработки ошибок в registration.py**

**Файл**: `handlers/registration.py`, строки 78-88

```python
async def process_alias(message: Message, state: FSMContext, db: DatabaseManager):
    # ...
    p_info = {"fio": data["fio"], "bday": data["bday"], "alias": message.text}
    await db.add_patient(uid, p_id, p_info)
```

**Проблема**: Если `db.add_patient()` выбросит исключение, состояние FSM не будет очищено, пользователь останется в подвешенном состоянии.

**Рекомендация**:

```python
try:
    await db.add_patient(uid, p_id, p_info)
    await state.clear()
    # ...
except Exception as e:
    logger.error(f"Ошибка добавления пациента: {e}")
    await message.answer("Произошла ошибка. Попробуйте ещё раз.")
    await state.clear()  # Всё равно очистить состояние
```

---

#### 7. **Проблема с proxy в healthcheck_loop**

**Файл**: `services/healthcheck.py`, строки 112-116

```python
specialties = await api.fetch_speciality_list(
    settings.DISCOVERY_PATIENT_ID_ADULT, str(settings.CLINICS[0])
)
```

**Проблема**: Healthcheck использует только одну клинику. Если проблема именно с другой клиникой — она не будет обнаружена.

**Рекомендация**: Проверять несколько клиник или рандомизировать выбор.

---

### 🔧 **Улучшения архитектуры**

#### 8. **Глобальное состояние metrics**

**Файл**: `services/healthcheck.py`, строка 92

```python
metrics = HealthMetrics()
```

**Проблема**: Глобальная переменная усложняет тестирование и может привести к гонкам.

**Рекомендация**: Использовать dependency injection или Singleton с lock:

```python
class MetricsRegistry:
    _instance: Optional['MetricsRegistry'] = None
    _lock = asyncio.Lock()
    @classmethod
    async def get_instance(cls) -> 'HealthMetrics':
        async with cls._lock:
            if cls._instance is None:
                cls._instance = HealthMetrics()
            return cls._instance
```

---

#### 9. **Дублирование кода CLINICS_REGISTRY**

**Файл**: `config.py`, строки 17-21 и `CLINICS: list = [272, 271, 161]`

**Проблема**: Список клиник задан в двух местах. Возможно рассогласование.

**Рекомендация**:

```python
CLINICS_REGISTRY: dict[str, ClinicInfo] = { ... }
CLINICS: list[str] = list(CLINICS_REGISTRY.keys())  # Единый источник истины
```

---

#### 10. **Отсутствие rate limiting между разными сервисами**

**Файл**: `api/zdrav_client.py`, строки 18-20

```python
self.limiter = aiolimiter.AsyncLimiter(max_rate=10, time_period=60)
```

**Проблема**: Один лимитер на все запросы. Но `monitor_loop`, `discovery_loop` и `healthcheck_loop` работают параллельно и могут превысить лимит.

**Рекомендация**:

- Увеличить лимит или
- Использовать отдельный лимитер для каждого типа операций
- Добавить приоритизацию запросов

---

### 📝 **Стилевые замечания**

1. **Несогласованность имён**:
    - `IdSpesiality` (опечатка в API) vs `specialty` в коде
    - Рекомендуется создать mapping слой
2. **Избыточные комментарии**:
    - Строки вроде `# import sqlite3 # Удален...` — лучше убрать
3. **Магические числа**:
    - `random.uniform(42, 85)` — вынести в константы с пояснением
4. **Типизация**:
    - Местами отсутствует (`-> Dict[str, Any]` вместо конкретных типов)
    - Рекомендуется включить mypy в CI

---

### 🎯 **Приоритетные действия**

|Приоритет|Проблема|Сложность|
|---|---|---|
|🔴 Критично|Гонка данных в `get_user_data()`|Средняя|
|🔴 Критично|Утечка памяти в `empty_counts`|Низкая|
|🟡 Высокий|SQL-инъекция через `field`|Низкая|
|🟡 Высокий|Hardcoded patient IDs|Низкая|
|🟢 Средний|Валидация API ответов|Средняя|
|🟢 Средний|Обработка ошибок в registration|Низкая|

---

### 💡 **Дополнительные рекомендации**

1. **CI/CD**: Добавить pre-commit hooks (black, flake8, mypy)
2. **Docker**: Создать Dockerfile для деплоя
3. **Monitoring**: Добавить экспорт метрик в Prometheus format
4. **Secrets**: Использовать external secrets manager для продакшена
5. **Документация**: Расширить README с примерами использования и troubleshooting

В целом проект хорошо структурирован, но требует доработки в области безопасности и обработки краевых случаев.
