"""
Репозиторий врачей: CRUD-операции с таблицей doctors.
"""

from __future__ import annotations

from src.database.base_repo import BaseRepository
from src.database.types import DoctorEntry


class DoctorRepository(BaseRepository):
    """CRUD-операции с врачами (таблица doctors)."""

    async def get_clinic_doctors(self, clinic_id: str) -> dict[str, DoctorEntry]:
        """Возвращает словарь врачей клиники (ключ — doctor_id)."""
        cursor = await self._c.execute(
            "SELECT doctor_id, name, specialty FROM doctors WHERE clinic_id = ?",
            (clinic_id,),
        )
        rows = await cursor.fetchall()
        return {
            row["doctor_id"]: {"name": row["name"], "specialty": row["specialty"]}
            for row in rows
        }

    async def get_clinic_specialties(self, clinic_id: str) -> list[dict[str, str]]:
        """Возвращает список уникальных специальностей для клиники.

        Возвращает список словарей с ключами ``specialty`` (полное название)
        и ``specialty_id`` (пустая строка, т.к. ID не хранится в БД).
        """
        cursor = await self._c.execute(
            "SELECT DISTINCT specialty FROM doctors "
            "WHERE clinic_id = ? AND specialty != '' "
            "ORDER BY specialty",
            (clinic_id,),
        )
        rows = await cursor.fetchall()
        return [{"specialty": row["specialty"], "specialty_id": ""} for row in rows]

    async def upsert_doctor(
        self, clinic_id: str, doctor_id: str, name: str, specialty: str
    ) -> None:
        """Добавляет или обновляет запись врача."""
        await self._c.execute(
            """INSERT OR REPLACE INTO doctors
            (clinic_id, doctor_id, name, specialty)
            VALUES (?, ?, ?, ?)""",
            (clinic_id, doctor_id, name, specialty),
        )
        await self._c.commit()

    async def search_doctors_by_name(self, query: str, limit: int = 20) -> list[dict]:
        """Поиск врачей по подстроке в имени (глобально, по всем клиникам).

        Фильтрация выполняется в Python, поскольку SQLite LOWER() не работает
        для кириллицы без ICU-расширения. Загружаются все врачи (≈665 записей),
        затем фильтруются регистронезависимо через str.lower().
        """
        cursor = await self._c.execute(
            "SELECT d.clinic_id, d.doctor_id, d.name, d.specialty, "
            "c.name as clinic_name "
            "FROM doctors d "
            "LEFT JOIN clinics c ON d.clinic_id = c.clinic_id "
            "ORDER BY d.name"
        )
        rows = await cursor.fetchall()
        all_doctors = [dict(row) for row in rows]

        query_lower = query.lower()
        result = [d for d in all_doctors if query_lower in d["name"].lower()]
        return result[:limit]
