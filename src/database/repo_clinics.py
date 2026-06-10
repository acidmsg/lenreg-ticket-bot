"""
Репозиторий клиник: CRUD-операции с таблицей clinics.
"""

from __future__ import annotations

import re

from loguru import logger

from src.database.base_repo import BaseRepository
from src.database.types import ClinicInfo
from src.i18n import _data


def detect_clinic_type(name: str) -> str:
    """
    Определяет тип клиники по её названию.

    Порядок проверки:
    1. 'стоматолог' → 'all' (в стоматологии есть и взрослые, и дети).
       Даже если в названии есть "детск" — стоматология всегда all.
    2. 'детск' → 'child' (детская, детский и т.п.)
    3. Иначе → 'adult'
    """
    if not name:
        return "adult"
    lower = name.lower()
    if re.search(r"стоматолог", lower):
        return "all"
    if re.search(r"детск", lower):
        return "child"
    return "adult"


def detect_clinic_city(name: str) -> str:
    """
    Определяет город/район по полному названию клиники.

    Приоритет: сначала ищем конкретный населённый пункт,
    потом определяем по ЛПУ (часть в кавычках).
    """
    if not name:
        return _data("city-fallback-other")

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

    return _data("city-fallback-other")


class ClinicRepository(BaseRepository):
    """CRUD-операции с клиниками (таблица clinics)."""

    async def upsert_clinic(self, clinic_id: str, name: str) -> None:
        """
        Обновляет только название клиники. Не затирает type/is_active/city.
        Если клиники нет — вставляет с типом и городом, определёнными по названию.
        """
        clinic_type = detect_clinic_type(name)
        city = detect_clinic_city(name)
        await self._c.execute(
            "INSERT INTO clinics (clinic_id, name, type, is_active, city) "
            "VALUES (?, ?, ?, 1, ?) "
            "ON CONFLICT(clinic_id) DO UPDATE SET name = excluded.name",
            (clinic_id, name, clinic_type, city),
        )
        await self._c.commit()

    async def get_all_clinic_ids(self) -> list[str]:
        """Возвращает все clinic_id из таблицы clinics."""
        cursor = await self._c.execute("SELECT clinic_id FROM clinics")
        rows = await cursor.fetchall()
        return [row["clinic_id"] for row in rows]

    async def get_clinic_name(self, clinic_id: str) -> str | None:
        """Возвращает название клиники по ID или None."""
        cursor = await self._c.execute(
            "SELECT name FROM clinics WHERE clinic_id = ?", (clinic_id,)
        )
        row = await cursor.fetchone()
        return row["name"] if row else None

    async def get_all_clinic_names(self) -> dict[str, str]:
        """Возвращает словарь {clinic_id: name} для всех клиник."""
        cursor = await self._c.execute("SELECT clinic_id, name FROM clinics")
        rows = await cursor.fetchall()
        return {row["clinic_id"]: row["name"] for row in rows}

    async def get_clinic_type(self, clinic_id: str) -> str | None:
        """Возвращает тип клиники (adult/child/all)."""
        cursor = await self._c.execute(
            "SELECT type FROM clinics WHERE clinic_id = ?", (clinic_id,)
        )
        row = await cursor.fetchone()
        return row["type"] if row else None

    async def get_clinic_discovery_patients(self, clinic_id: str) -> tuple[str, str]:
        """
        Возвращает per-клиника discovery пациентов (adult, child).
        Если для клиники не заданы свои пациенты — возвращает ('', '').
        """
        try:
            c = self._db_conn.conn
            if c is None:
                return ("", "")
            cursor = await c.execute(
                "SELECT discovery_patient_adult, discovery_patient_child "
                "FROM clinics WHERE clinic_id = ?",
                (clinic_id,),
            )
            row = await cursor.fetchone()
            if row:
                return (
                    row["discovery_patient_adult"] or "",
                    row["discovery_patient_child"] or "",
                )
        except Exception:
            logger.debug(
                "Ошибка при get_clinic_discovery_patients clinic_id={}",
                clinic_id,
                exc_info=True,
            )
        return ("", "")

    async def get_active_clinics(self) -> list[ClinicInfo]:
        """Возвращает список активных клиник с полными данными (включая city)."""
        cursor = await self._c.execute(
            "SELECT clinic_id, name, type, is_active, city "
            "FROM clinics WHERE is_active = 1"
        )
        rows = await cursor.fetchall()
        return [
            {
                "clinic_id": row["clinic_id"],
                "name": row["name"],
                "type": row["type"],
                "is_active": row["is_active"],
                "city": row["city"] or "",
            }
            for row in rows
        ]

    async def get_distinct_cities(self) -> list[str]:
        """Возвращает отсортированный список уникальных городов активных клиник."""
        cursor = await self._c.execute(
            "SELECT DISTINCT city FROM clinics "
            "WHERE is_active = 1 AND city != '' ORDER BY city"
        )
        rows = await cursor.fetchall()
        return [row["city"] for row in rows]

    async def get_active_clinic_ids(self) -> list[str]:
        """Возвращает список clinic_id активных клиник (is_active = 1)."""
        cursor = await self._c.execute(
            "SELECT clinic_id FROM clinics WHERE is_active = 1"
        )
        rows = await cursor.fetchall()
        return [row["clinic_id"] for row in rows]

    async def get_clinic_doctor_count(self, clinic_id: str) -> int:
        """Возвращает количество врачей в клинике."""
        try:
            c = self._db_conn.conn
            if c is None:
                return 0
            cursor = await c.execute(
                "SELECT COUNT(*) as cnt FROM doctors WHERE clinic_id = ?",
                (clinic_id,),
            )
            row = await cursor.fetchone()
            return row["cnt"] if row else 0
        except Exception:
            logger.debug(
                "Ошибка при get_clinic_doctor_count clinic_id={}",
                clinic_id,
                exc_info=True,
            )
            return 0
