"""Однократный скрипт: исправляет типы fallback-клиник в существующей БД."""

import sqlite3
import sys

DB_PATH = "data/bot.db"

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# 272 = Стоматологическая (все возрасты)
cur.execute("UPDATE clinics SET type = ? WHERE clinic_id = ?", ("all", "272"))
# 271 = Взрослая
cur.execute("UPDATE clinics SET type = ? WHERE clinic_id = ?", ("adult", "271"))
# 161 = Детская
cur.execute("UPDATE clinics SET type = ? WHERE clinic_id = ?", ("child", "161"))

conn.commit()

cur.execute(
    "SELECT clinic_id, name, type FROM clinics WHERE clinic_id IN (?, ?, ?)",
    ("272", "271", "161"),
)
print("После исправления:")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]} ({row[2]})")

conn.close()
