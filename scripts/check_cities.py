"""Проверяет, есть ли клиники без города."""

import sqlite3

conn = sqlite3.connect("data/bot.db")
c = conn.cursor()
c.execute("SELECT count(*) FROM clinics WHERE city IS NULL OR city = ''")
print("Empty cities:", c.fetchone()[0])
c.execute("SELECT clinic_id, name FROM clinics WHERE city IS NULL OR city = ''")
for r in c.fetchall():
    print(f"  {r[0]}: {r[1][:60]}")
c.execute("SELECT count(*) FROM clinics")
print("Total clinics:", c.fetchone()[0])
conn.close()
