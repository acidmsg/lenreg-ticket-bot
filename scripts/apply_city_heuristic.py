"""
Применяет эвристику detect_clinic_city ко всем клиникам в БД,
когда city ещё не проставлен (или пуст).
"""

import sqlite3
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import settings
from database.database import detect_clinic_city

conn = sqlite3.connect(settings.SQLITE_DB_PATH)
cur = conn.cursor()

cur.execute("SELECT clinic_id, name, COALESCE(city, '') as city FROM clinics")
rows = cur.fetchall()

updated = 0
for c_id, name, curr_city in rows:
    if curr_city:
        continue  # уже есть
    new_city = detect_clinic_city(name)
    cur.execute("UPDATE clinics SET city = ? WHERE clinic_id = ?", (new_city, c_id))
    updated += 1
    print(f"  {c_id}: '{new_city}' <- {name[:50]}")

conn.commit()
print(f"\nИтого обновлено: {updated}")

# Проверка
cur.execute("SELECT city, COUNT(*) FROM clinics GROUP BY city ORDER BY city")
print("\n=== Города ===")
for city, cnt in cur.fetchall():
    print(f"  {city or '(пусто)'}: {cnt}")

conn.close()
