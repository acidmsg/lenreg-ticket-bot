"""
DoctorManager — адаптер поверх Database (SQLite).
Сохраняет обратную совместимость с существующим кодом.
"""

from typing import Any, Dict

from src.database.database import Database


class DoctorManager:
    """Обёртка над Database для работы со справочником врачей."""

    def __init__(self, db: Database):
        self._db = db
        self.data: Dict[str, Any] = {}

    async def load(self):
        """Загрузить всех врачей из SQLite в кэш data (для обратной совместимости)."""
        self.data = {}
        clinic_ids = await self._db.get_all_clinic_ids()
        for cid in clinic_ids:
            clinic_name = await self._db.get_clinic_name(cid)
            doctors = await self._db.get_clinic_doctors(cid)
            self.data[cid] = {
                "name": clinic_name or "Unknown",
                "doctors": doctors,
            }

    async def merge_doctors(self, clinic_id: str, doctors: list):
        return await self._db.merge_doctors(str(clinic_id), doctors)
