"""
Применяет эвристику detect_clinic_city ко всем клиникам в БД,
когда city ещё не проставлен (или пуст).
"""

import re
import sqlite3

DB_PATH = "data/bot.db"


def detect_clinic_city(name: str) -> str:
    if not name:
        return "Прочее"
    lower = name.lower()
    settlements = [
        ("кудрово", "Кудрово"),
        ("мурино", "Мурино"),
        ("девяткино", "Девяткино"),
        ("бугры", "Бугры"),
        ("кузьмолово", "Кузьмолово"),
        ("токсово", "Токсово"),
        ("сертолово", "Сертолово"),
        ("всеволожск", "Всеволожск"),
        ("всеволож", "Всеволожск"),
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
    for keyword, city in settlements:
        if keyword in lower:
            return city
    lpu_match = re.search(r'"([^"]+)"', name)
    lpu = lpu_match.group(1).lower() if lpu_match else lower
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


conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

cur.execute("SELECT clinic_id, name, COALESCE(city, '') as city FROM clinics")
rows = cur.fetchall()

updated = 0
for c_id, name, curr_city in rows:
    if city:
        continue
    new_city = detect_clinic_city(name)
    cur.execute("UPDATE clinics SET city = ? WHERE clinic_id = ?", (new_city, c_id))
    updated += 1
    print(f"  {c_id}: '{new_city}' <- {name[:50]}")

conn.commit()
    if curr_city:
        continue  # уже есть
    new_city = detect_clinic_city(name)
    cur.execute("UPDATE clinics SET city = ? WHERE clinic_id = ?", (new_city, c_id))
    updated += 1
    print(f"  {c_id}: '{new_city}' <- {name[:50]}")

conn.commit()
print(f"\nИтого обновлено: {updated}")
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
