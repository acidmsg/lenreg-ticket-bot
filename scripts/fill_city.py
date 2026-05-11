"""Проставляет city для всех клиник по эвристике."""

import re
import sqlite3

SETTLEMENTS = [
    ("кудрово", "Кудрово"),
    ("мурино", "Мурино"),
    ("девяткино", "Девяткино"),
    ("бугры", "Бугры"),
    ("кузьмолово", "Кузьмолово"),
    ("токсово", "Токсово"),
    ("сертолово", "Сертолово"),
    ("павлово", "Павлово"),
    ("разметелево", "Разметелево"),
    ("рахья", "Рахья"),
    ("романовка", "Романовка"),
    ("щеглово", "Щеглово"),
    ("заневский", "Заневский"),
    ("дубровка", "Дубровка"),
    ("кальтино", "Кальтино"),
    ("краснозвездин", "Краснозвездинское"),
    ("морозов", "им. Морозова"),
    ("гарболово", "Гарболово"),
    ("рапполово", "Рапполово"),
    ("вартемяги", "Вартемяги"),
    ("куйвози", "Куйвози"),
    ("лесколово", "Лесколово"),
    ("стеклянный", "Стеклянный"),
    ("пери", "Пери"),
    ("лесное", "Лесное"),
    ("юкки", "Юкки"),
    ("хиттолово", "Хиттолово"),
    ("ненимяки", "Ненимяки"),
    ("лехтуси", "Лехтуси"),
    ("васкелово", "Васкелово"),
    ("лаврики", "Лаврики"),
    ("воейково", "Воейково"),
    ("каменка", "Каменка"),
    ("грибное", "Грибное"),
    ("ваганово", "Ваганово"),
    ("новая пустошь", "Новая Пустошь"),
    ("углово", "Углово"),
    ("старая", "Старая"),
    ("ясная", "Ясная"),
]


def detect_city(name):
    if not name:
        return "Прочее"
    low = name.lower()
    for kw, city in SETTLEMENTS:
        if kw in low:
            return city
    m = re.search(r'"([^"]+)"', name)
    lpu = m.group(1).lower() if m else low
    if "всеволож" in lpu:
        return "Всеволожск"
    if "сертолов" in lpu:
        return "Сертолово"
    if "токсов" in lpu:
        return "Токсово"
    if "лонд" in lpu.replace(" ", ""):
        return "Наркология (ЛОНД)"
    if "лоцпз" in lpu.replace(" ", ""):
        return "Психиатрия (ЛОЦПЗ)"
    if "медицентр" in lpu:
        return "Медицентр"
    return "Прочее"


conn = sqlite3.connect("data/bot.db")
cur = conn.cursor()

cur.execute("SELECT clinic_id, name FROM clinics")
rows = cur.fetchall()

for cid, name in rows:
    city = detect_city(name)
    cur.execute("UPDATE clinics SET city = ? WHERE clinic_id = ?", (city, cid))

conn.commit()

cur.execute("SELECT city, COUNT(*) FROM clinics GROUP BY city ORDER BY city")
print("Города:")
for city, cnt in cur.fetchall():
    print(f"  {city}: {cnt}")

conn.close()
