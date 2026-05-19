# Технический долг (Technical Debt)

> **Последнее обновление:** 2026-05-19
> **Источники:** [`code_review.md`](code_review.md) (2026-05-14), [`docs/agents/CODE_REVIEW.md`](docs/agents/CODE_REVIEW.md) (2026-05-11), [`docs/code_review_optimization.md`](docs/code_review_optimization.md) (2026-05-15)
>
> **Это НЕ план работ.** Это каталог известных проблем, которые будут исправляться по мере возможности.
> Активные задачи (CRITICAL, HIGH, MEDIUM, FEATURES) вынесены в [`AGENT_TASKS.md`](AGENT_TASKS.md).
> **Статус:** ⬜ — не начато. Исправленные пункты удаляются из списка.
> **Верификация:** 2026-05-19 — сверка против кода. 6 оптимизаций выполнено и удалено, 2 дубликата объединено, 11 записей техдолга очищено (включая TD-HND-001/004/005/006, TD-DB-005).

---

## 🟢 LOW / TECH DEBT

### src/database/

### src/handlers/

### src/services/

### src/middleware/

### src/utils/

### src/keyboards/

### tests/

### src/main.py

### Прочее

---

## 🔵 OPTIMIZATION

| ID    | Задача                                                                                                                         | Файлы                                                                                                                                                            | Экономия  | Статус |
| ----- | ------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------- | ------ |
| OPT-K | Улучшить переиспользование общих фикстур через [`conftest.py`](tests/conftest.py) в тестах — снизить дублирование setup-логики | [`tests/conftest.py`](tests/conftest.py), [`tests/test_handlers_common.py`](tests/test_handlers_common.py), [`tests/test_keyboards.py`](tests/test_keyboards.py) | ~10 строк | ⬜     |

> **Исключены из плана:**
>
> - OPT-C (дублирование шаблона сообщения) — частично решено в сессии T6 (`format_slots()`)
> - OPT-F (дублирование check_slots в toggle_doctor) — логика разошлась после T4/T5/T6
> - OPT-H (вынос proxy_discovery) — уже выполнено, модуль [`src/utils/proxy_discovery.py`](src/utils/proxy_discovery.py) существует

---

## ⚪ MINOR

Пусто
