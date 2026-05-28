---
description: "Очистка: удаление .tmp_*, *.tmp, __pycache__/, .pytest_cache/"
---

Выполни очистку проекта от временных и кэш-файлов. Удали следующие файлы и директории:

- Все файлы `.tmp_*` и `*.tmp` в корне проекта
- Все директории `__pycache__/` рекурсивно в `src/` и `tests/`
- Директорию `.pytest_cache/`
- Директорию `.ruff_cache/` (опционально, если есть)

Используй PowerShell команды:

```powershell
Remove-Item -Path ".tmp_*" -Force -ErrorAction SilentlyContinue
Remove-Item -Path "*.tmp" -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path "src", "tests" -Directory -Recurse -Filter "__pycache__" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path ".pytest_cache" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path ".ruff_cache" -Recurse -Force -ErrorAction SilentlyContinue
```

Покажи что было удалено (список файлов/директорий).
