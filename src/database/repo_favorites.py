"""Репозиторий избранных клиник аккаунта (P4-FAV).

Избранное привязано к аккаунту (``uid``), а не к пациенту: набор «своих»
клиник один на аккаунт. Таблица ``favorite_clinics`` создаётся миграцией v15.
"""

import time

from src.database.base_repo import BaseRepository


class FavoriteRepository(BaseRepository):
    """Хранение избранных клиник: список, добавление, удаление."""

    async def list_clinic_ids(self, uid: str) -> list[str]:
        """Возвращает id избранных клиник аккаунта.

        Порядок — от недавно добавленных к старым, чтобы свежий выбор был
        первым в списке; при равных метках — по возрастанию id для
        предсказуемости.

        Args:
            uid: идентификатор аккаунта (Telegram user id).

        Returns:
            Список ``clinic_id`` (может быть пустым).
        """
        cursor = await self._c.execute(
            "SELECT clinic_id FROM favorite_clinics WHERE uid = ? "
            "ORDER BY created_at DESC, clinic_id ASC",
            (uid,),
        )
        rows = await cursor.fetchall()
        return [str(row["clinic_id"]) for row in rows]

    async def add(self, uid: str, clinic_id: str) -> bool:
        """Добавляет клинику в избранное аккаунта.

        Идемпотентно: повторный вызов для уже избранной клиники состояние не
        меняет (первичный ключ ``(uid, clinic_id)``).

        Args:
            uid: идентификатор аккаунта.
            clinic_id: идентификатор клиники в справочнике.

        Returns:
            ``True``, если запись добавлена; ``False``, если уже была.
        """
        cursor = await self._c.execute(
            "INSERT OR IGNORE INTO favorite_clinics (uid, clinic_id, created_at) "
            "VALUES (?, ?, ?)",
            (uid, clinic_id, time.time()),
        )
        await self._c.commit()
        inserted = cursor.rowcount > 0
        await cursor.close()
        return inserted

    async def remove(self, uid: str, clinic_id: str) -> bool:
        """Убирает клинику из избранного аккаунта.

        Идемпотентно: удаление отсутствующей записи ошибкой не считается.

        Args:
            uid: идентификатор аккаунта.
            clinic_id: идентификатор клиники в справочнике.

        Returns:
            ``True``, если запись была удалена; ``False``, если её не было.
        """
        cursor = await self._c.execute(
            "DELETE FROM favorite_clinics WHERE uid = ? AND clinic_id = ?",
            (uid, clinic_id),
        )
        await self._c.commit()
        removed = cursor.rowcount > 0
        await cursor.close()
        return removed

    async def is_favorite(self, uid: str, clinic_id: str) -> bool:
        """Проверяет, отмечена ли клиника избранной у аккаунта.

        Args:
            uid: идентификатор аккаунта.
            clinic_id: идентификатор клиники.

        Returns:
            ``True``, если клиника в избранном.
        """
        cursor = await self._c.execute(
            "SELECT 1 FROM favorite_clinics WHERE uid = ? AND clinic_id = ? LIMIT 1",
            (uid, clinic_id),
        )
        row = await cursor.fetchone()
        await cursor.close()
        return row is not None
