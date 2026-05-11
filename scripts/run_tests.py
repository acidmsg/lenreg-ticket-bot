"""Скрипт для запуска тестов с корректным выводом (обход бага кодировки pwsh)."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"

# Собираем аргументы: все, что передано скрипту
args = [str(PYTHON), "-m", "pytest", "tests/"] + (
    sys.argv[1:] if len(sys.argv) > 1 else ["-v", "--tb=short"]
)

result = subprocess.run(
    args,
    capture_output=True,
    text=True,
    timeout=120,
    cwd=str(ROOT),
)

# Пишем полный вывод в файл для детального анализа
output = result.stdout + "\n" + result.stderr
log_path = ROOT / ".pytest_output.txt"
log_path.write_text(output, encoding="utf-8")

# Выводим итог
print(result.stdout)
if result.stderr:
    print(result.stderr, file=sys.stderr)

print(f"\nПолный вывод сохранён в: {log_path}")
sys.exit(result.returncode)
