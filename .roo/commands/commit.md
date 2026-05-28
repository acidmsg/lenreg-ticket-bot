---
description: "Commit + push: авто-генерация сообщения, git add -A, коммит, push в текущую ветку"
---

Выполни commit и push всех изменений в проекте:

1. Получи список изменённых файлов: `git diff --stat`
2. На основе вывода `git diff --stat` сгенерируй осмысленный commit message на русском языке в формате Conventional Commits (например, `feat: ...`, `fix: ...`, `chore: ...`, `docs: ...`). Сообщение должно кратко отражать суть изменений.
3. Выполни последовательно:
   - `git add -A`
   - `git commit -m "сгенерированное_сообщение"`
   - `git push origin HEAD`
4. Сообщи пользователю: ветку, commit hash (короткий), commit message.

Никаких проверок (lint/test) не выполнять. Только commit и push.
