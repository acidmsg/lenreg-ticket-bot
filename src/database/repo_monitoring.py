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
        """Возвращает словарь мониторинга пользователя (включая поля фильтра)."""
        cursor = await self._c.execute(
            "SELECT p_id, d_id, name, clinic_id, specialty, date, "
            "date_from, date_to, time_from, time_to, specific_dates "
            "FROM user_monitoring WHERE uid = ?",
            (uid,),
        )
        rows = await cursor.fetchall()
        result: dict[str, dict[str, MonitoringEntry]] = {}
        for row in rows:
            p_id = row["p_id"]
            if p_id not in result:
                result[p_id] = {}
            entry: MonitoringEntry = {
                "name": row["name"],
                "clinic_id": row["clinic_id"],
                "specialty": row["specialty"],
                "date": row["date"],
                "date_from": row["date_from"] or "",
                "date_to": row["date_to"] or "",
                "time_from": row["time_from"] or "",
                "time_to": row["time_to"] or "",
                "specific_dates": row["specific_dates"] or "[]",
            }
            result[p_id][row["d_id"]] = entry
        return result

    async def update_monitoring_filter(
        self,
        uid: str,
        p_id: str,
        d_id: str,
        filter_data: dict[str, str],
    ) -> None:
        """Обновляет поля фильтра отслеживания для указанной строки мониторинга.

        Args:
            uid: ID пользователя Telegram.
            p_id: ID пациента.
            d_id: ID врача.
            filter_data: Поля фильтра (``date_from``, ``date_to``, ``time_from``,
                ``time_to``, ``specific_dates``). Отсутствующие ключи сбрасываются.

        Raises:
            ValueError: Если запись мониторинга не найдена.
        """
        specific_dates = filter_data.get("specific_dates", "") or "[]"
        cursor = await self._c.execute(
            "UPDATE user_monitoring "
            "SET date_from = ?, date_to = ?, time_from = ?, time_to = ?, "
            "specific_dates = ? "
            "WHERE uid = ? AND p_id = ? AND d_id = ?",
            (
                filter_data.get("date_from", ""),
                filter_data.get("date_to", ""),
                filter_data.get("time_from", ""),
                filter_data.get("time_to", ""),
                specific_dates,
                uid,
                p_id,
                d_id,
            ),
        )
        await self._c.commit()
        if cursor.rowcount == 0:
            raise ValueError(
                f"Мониторинг не найден: uid={uid}, p_id={p_id}, d_id={d_id}"
            )

    async def add_monitoring_entry(
        self,
        uid: str,
        p_id: str,
        d_id: str,
        name: str,
        clinic_id: str,
        specialty: str,
        date: str = "",
    ) -> None:
        """Добавляет или обновляет запись мониторинга."""
        await self._c.execute(
            """INSERT OR REPLACE INTO user_monitoring
               (uid, p_id, d_id, name, clinic_id, specialty, date)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (uid, p_id, d_id, name, clinic_id, specialty, date),
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

    async def delete_patient(self, uid: str, p_id: str) -> int:
        """Удаляет пациента и все связанные данные в одной транзакции.

        Удаляет записи из user_patients, user_monitoring и user_last_messages.

        Returns:
            Сколько записей пациента удалено (0, если его не было).
        """
        await self._c.execute("BEGIN")
        try:
            cursor = await self._c.execute(
                "DELETE FROM user_patients WHERE uid = ? AND p_id = ?",
                (uid, p_id),
            )
            monitoring_cursor = await self._c.execute(
                "DELETE FROM user_monitoring WHERE uid = ? AND p_id = ?",
                (uid, p_id),
            )
            messages_cursor = await self._c.execute(
                "DELETE FROM user_last_messages WHERE uid = ? AND p_id = ?",
                (uid, p_id),
            )
            await self._c.execute("COMMIT")
            # Возвращаем сумму всех удалённых записей: пациент мог существовать
            # только в мониторинге, без строки в user_patients.
            return (
                int(cursor.rowcount or 0)
                + int(monitoring_cursor.rowcount or 0)
                + int(messages_cursor.rowcount or 0)
            )
        except Exception:
            await self._c.execute("ROLLBACK")
            raise

    async def delete_doctor(self, uid: str, d_id: str) -> int:
        """Удаляет врача из мониторинга пользователя по всем пациентам.

        Returns:
            Сколько цепочек пациент-врач удалено.
        """
        cursor = await self._c.execute(
            "DELETE FROM user_monitoring WHERE uid = ? AND d_id = ?", (uid, d_id)
        )
        await self._c.commit()
        return int(cursor.rowcount or 0)
