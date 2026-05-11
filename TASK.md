# План реализации: вынос параметров в БД

## ✅ Выполнено

### Новые/изменённые таблицы

- `clinics` — добавлены `type`, `is_active`, `city`, `discovery_patient_adult`, `discovery_patient_child`
- `config` (новая) — `key` TEXT PK, `value` TEXT
- `specialty_aliases` (новая) — `full_name` TEXT PK, `short_name` TEXT

### Что сделано

1. **database.py** — схема изменена, добавлены методы работы с config, specialty_aliases, clinics
2. **migration** — скрипт `scripts/migrate_configs_to_db.py` для переноса старых данных
3. **config.py** — загрузка из БД (`load_config_from_db()`), `CLINICS_REGISTRY` удалён
4. **utils/helpers.py** — загрузка `SPECIALTY_ALIASES` из БД (`load_specialty_aliases_from_db()`)
5. **keyboards/inline.py** — получение данных клиник из БД (без fallback на хардкод)
6. **Остальные файлы** — адаптированы под новые источники данных
7. **Тестирование** — импорты и старт бота проверены
