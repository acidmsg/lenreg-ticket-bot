# SESSION_LOG.md

## 2026-05-19 — TD-DB-005: удаление legacy-формата в `get_last_message_id()`

### Выполненные задачи

- **TD-DB-005** в [`src/database/manager.py`](src/database/manager.py:142): удалена проверка `isinstance(val, int)` из `get_last_message_id()`.
  - Функция теперь ожидает только `dict` в кэше (текущий формат).
  - Legacy-формат (`int`) больше не поддерживается.
  - Ruff check пройден успешно (0 errors).

### Изменённые файлы

- [`src/database/manager.py`](src/database/manager.py:148-152) — удалены строки 151-152 (legacy-проверка `isinstance(val, int)`).
- [`docs/agents/TECH_DEBT.md`](docs/agents/TECH_DEBT.md:19) — удалена запись TD-DB-005.
