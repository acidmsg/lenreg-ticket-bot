"""Скрипт для запуска тестов с корректным выводом.
Использует -X utf8 (PEP 540) для принудительного UTF-8 режима,
обходит баг кодировки cp1251 в pwsh на Windows.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"

# -X utf8 включает Python UTF-8 Mode (PEP 540): sys.stdout.encoding = utf-8
args = [str(PYTHON), "-X", "utf8", "-m", "pytest", "tests/"] + (
    sys.argv[1:] if len(sys.argv) > 1 else ["-v", "--tb=short"]
)

result = subprocess.run(
    args,
    capture_output=False,  # прямой вывод в терминал — работает с -X utf8
    timeout=120,
    cwd=str(ROOT),
)

sys.exit(result.returncode)
