"""
Репозиторий мониторинга: user_monitoring, delete_patient с транзакцией.
"""

from __future__ import annotations

from src.database.base_repo import BaseRepository
from src.database.types import MonitoringEntry


class MonitoringRepository(BaseRepository):
    """CRUD-операции с мониторингом врачей (таблица user_monitoring)."""

    async def get_user_monitoring(
        self, uid: str
    ) -> dict[str, dict[str, MonitoringEntry]]:
        """Возвращает словарь мониторинга пользователя."""
        cursor = await self._c.execute(
            "SELECT p_id, d_id, name, clinic_id, specialty "
            "FROM user_monitoring WHERE uid = ?",
            (uid,),
        )
        rows = await cursor.fetchall()
        result: dict[str, dict[str, MonitoringEntry]] = {}
        for row in rows:
            p_id = row["p_id"]
            if p_id not in result:
                result[p_id] = {}
            result[p_id][row["d_id"]] = {
                "name": row["name"],
                "clinic_id": row["clinic_id"],
                "specialty": row["specialty"],
            }
        return result

    async def add_monitoring_entry(
        self,
        uid: str,
        p_id: str,
        d_id: str,
        name: str,
        clinic_id: str,
        specialty: str,
    ) -> None:
        """Добавляет или обновляет запись мониторинга."""
        await self._c.execute(
            """INSERT OR REPLACE INTO user_monitoring
               (uid, p_id, d_id, name, clinic_id, specialty)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (uid, p_id, d_id, name, clinic_id, specialty),
        )
        await self._c.commit()

    async def remove_monitoring_entry(self, uid: str, p_id: str, d_id: str) -> None:
        """Удаляет запись мониторинга."""
        await self._c.execute(
            "DELETE FROM user_monitoring WHERE uid = ? AND p_id = ? AND d_id = ?",
            (uid, p_id, d_id),
        )
        await self._c.commit()

    async def clear_all_monitoring(self, uid: str) -> None:
        """Удаляет все записи мониторинга пользователя."""
        await self._c.execute(
            "DELETE FROM user_monitoring WHERE uid = ?",
            (uid,),
        )
        await self._c.commit()

    async def delete_patient(self, uid: str, p_id: str) -> None:
        """Удаляет пациента и все связанные данные в одной транзакции.

        Удаляет записи из user_patients, user_monitoring и user_last_messages.
        """
        await self._c.execute("BEGIN")
        try:
            await self._c.execute(
                "DELETE FROM user_patients WHERE uid = ? AND p_id = ?",
                (uid, p_id),
            )
            await self._c.execute(
                "DELETE FROM user_monitoring WHERE uid = ? AND p_id = ?",
                (uid, p_id),
            )
            await self._c.execute(
                "DELETE FROM user_last_messages WHERE uid = ? AND p_id = ?",
                (uid, p_id),
            )
            await self._c.execute("COMMIT")
        except Exception:
            await self._c.execute("ROLLBACK")
            raise
