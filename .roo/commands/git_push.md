---
description: "Git push: markdownlint → авто-сообщение → git add -A → commit → push"
---

Выполни commit и push всех изменений в проекте с предварительной проверкой markdownlint:

1. Запусти проверку markdownlint на всех .md файлах:

   ```powershell
   npx markdownlint "docs/**/*.md" ".roo/**/*.md" "*.md" > .tmp_mdlint.txt 2>&1
   ```

   Прочитай `.tmp_mdlint.txt`. Если есть ошибки — покажи их пользователю, удали `.tmp_mdlint.txt` и остановись (commit не выполняй).

2. Если markdownlint прошёл чисто — удали `.tmp_mdlint.txt` и продолжай.

3. Получи список изменённых файлов: `git diff --stat`

4. На основе вывода `git diff --stat` сгенерируй осмысленный commit message на русском языке в формате Conventional Commits (например, `feat: ...`, `fix: ...`, `chore: ...`, `docs: ...`). Сообщение должно кратко отражать суть изменений.

5. Выполни последовательно:
   - `git add -A`
   - `git commit -m "сгенерированное_сообщение"`
   - `git push origin HEAD`

6. Сообщи пользователю: ветку, commit hash (короткий), commit message.

Никаких других проверок (lint/test) кроме markdownlint не выполнять.
