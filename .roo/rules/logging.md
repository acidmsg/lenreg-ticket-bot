# Правила логирования сессии и задач

## SESSION_LOG.md (активный) + SESSION_ARCHIVE.md (история)

- **Активный лог:** [`docs/agents/SESSION_LOG.md`](docs/agents/SESSION_LOG.md) — только последняя сессия (шаблон: дата, задачи, файлы, тесты).
- **Архив:** [`docs/agents/SESSION_ARCHIVE.md`](docs/agents/SESSION_ARCHIVE.md) — полная хронология всех прошлых сессий.
- **Перед КАЖДЫМ вызовом `attempt_completion`** ОБЯЗАН:
  1. Дописать запись в [`docs/agents/SESSION_LOG.md`](docs/agents/SESSION_LOG.md) с:
     - Датой
     - Списком выполненных задач (со ссылками на файлы и номера строк)
     - Списком изменённых файлов
     - Результатами тестов (если запускались)
  2. Перенести предыдущую запись из `SESSION_LOG.md` в конец [`docs/agents/SESSION_ARCHIVE.md`](docs/agents/SESSION_ARCHIVE.md) (под заголовок `---`).
- `attempt_completion` = конец сессии. Нельзя вызывать его, пока лог не обновлён.

## AGENT_TASKS.md

- **В начале сессии** — прочитать [`docs/agents/AGENT_TASKS.md`](docs/agents/AGENT_TASKS.md), сверить актуальность.
- **Перед `attempt_completion`** — **удалить** выполненные задачи из таблицы и чек-листа (не зачёркивать, не отмечать `[x]`, а полностью удалить строку).
- Выполненные задачи НЕ хранятся в `AGENT_TASKS.md` — их история в `SESSION_LOG.md` и `SESSION_ARCHIVE.md`.

## Порядок перед attempt_completion (обязательный)

1. `apply_diff` → обновить [`docs/agents/SESSION_LOG.md`](docs/agents/SESSION_LOG.md)
2. `apply_diff` → перенести старую запись в [`docs/agents/SESSION_ARCHIVE.md`](docs/agents/SESSION_ARCHIVE.md)
3. `apply_diff` → обновить [`docs/agents/AGENT_TASKS.md`](docs/agents/AGENT_TASKS.md)
4. `execute_command` → `npx markdownlint "docs/**/*.md" ".roo/**/*.md" "*.md"` (исправить ошибки если есть)
5. `execute_command` → `npx prettier --write` на изменённые .md файлы
6. Только после этого → `attempt_completion`
