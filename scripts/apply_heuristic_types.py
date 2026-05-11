"""
Применяет эвристику detect_clinic_type ко всем клиникам в БД.
Запускать однократно после добавления эвристики.
"""

import re
import sqlite3

DB_PATH = "data/bot.db"


def detect_clinic_type(name: str) -> str:
    if not name:
        return "adult"
    lower = name.lower()
    if re.search(r"стоматолог", lower):
        return "all"
    if re.search(r"детск", lower):
        return "child"
    return "adult"


conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

cur.execute("SELECT clinic_id, name, type FROM clinics")
rows = cur.fetchall()

updated = 0
for c_id, name, curr_type in rows:
    new_type = detect_clinic_type(name)
    if curr_type != new_type:
        cur.execute("UPDATE clinics SET type = ? WHERE clinic_id = ?", (new_type, c_id))
        updated += 1
        print(f"  {c_id}: {curr_type} -> {new_type}  ({name[:60]})")

conn.commit()

# Проверка
print("\n=== Итоговые типы ===")
cur.execute(
    "SELECT clinic_id, name, type FROM clinics WHERE clinic_id IN (?, ?, ?, ?, ?)",
    ("272", "271", "161", "83", "70"),
)
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1][:40]}... ({r[2]})")

print(f"\nИтого обновлено: {updated}")
conn.close()
