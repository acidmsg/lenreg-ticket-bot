---
description: "Линтинг: ruff (check+fix+format) + mypy + markdownlint + prettier"
---

Выполни полный цикл линтинга и форматирования проекта:

**Python:**

1. `python -m ruff check src --fix > .tmp_lint_ruff.txt 2>&1`
2. `python -m ruff format src > .tmp_lint_fmt.txt 2>&1`
3. `python -m mypy src --check-untyped-defs > .tmp_lint_mypy.txt 2>&1`

**Markdown:**

4. `npx markdownlint "docs/**/*.md" ".roo/**/*.md" "*.md" > .tmp_lint_mdlint.txt 2>&1`
5. `npx prettier --write "docs/**/*.md" ".roo/**/*.md" "*.md" > .tmp_lint_prettier.txt 2>&1`

Прочитай все `.tmp_*` файлы и собери сводку: что исправлено автофиксом, какие ошибки остались (требуют ручного вмешательства). Удали все временные файлы после анализа.

Если есть ошибки mypy или markdownlint, которые нельзя автофиксить — покажи их пользователю с указанием файла и строки.
