"""Поиск по данным дашборда: пользователи, пациенты, клиники (DASH-9).

Врачей ищет существующий ``DoctorsRepository.search_doctors_by_name``;
здесь собраны запросы по остальным сущностям. Подстрока экранируется,
чтобы ``%`` и ``_`` в запросе администратора не превращались в шаблон.
"""

from __future__ import annotations

from src.database.base_repo import BaseRepository

# Сколько строк отдаёт каждый раздел поиска.
SEARCH_LIMIT = 20


def _escape_like(value: str) -> str:
    """Экранирует спецсимволы LIKE (``%``, ``_``, ``\\``)."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _like_patterns(query: str) -> list[str]:
    """Шаблоны LIKE для поиска без учёта регистра.

    LIKE в SQLite регистронезависим только для латиницы, поэтому для
    кириллицы (ФИО, названия клиник) добавляем варианты регистра запроса:
    «иванов», «Иванов», «ИВАНОВ».
    """
    base = _escape_like(query)
    variants = {base, base.lower(), base.upper(), base.capitalize()}
    return [f"%{variant}%" for variant in sorted(variants)]


def _match_clause(
    fields: tuple[str, ...], patterns: list[str]
) -> tuple[str, list[str]]:
    """Собирает WHERE-условие LIKE для набора полей и шаблонов.

    Returns:
        SQL-фрагмент и список параметров к нему.
    """
    parts = [f"{field} LIKE ? ESCAPE '\\'" for field in fields for _ in patterns]
    return " OR ".join(parts), list(patterns) * len(fields)


class SearchRepository(BaseRepository):
    """Поиск пользователей, пациентов и клиник по подстроке."""

    async def search_users(self, query: str, limit: int = SEARCH_LIMIT) -> list[str]:
        """Идентификаторы пользователей, содержащие подстроку."""
        patterns = _like_patterns(query)
        clause, params = _match_clause(("uid",), patterns)
        cursor = await self._c.execute(
            "SELECT DISTINCT uid FROM ("
            "  SELECT uid FROM user_patients"
            "  UNION SELECT uid FROM user_monitoring"
            f") WHERE {clause} ORDER BY uid LIMIT ?",
            (*params, limit),
        )
        rows = await cursor.fetchall()
        return [str(row["uid"]) for row in rows]

    async def search_patients(
        self, query: str, limit: int = SEARCH_LIMIT
    ) -> list[dict[str, str]]:
        """Пациенты, у которых совпало ФИО, псевдоним или p_id."""
        patterns = _like_patterns(query)
        clause, params = _match_clause(("fio", "p_id", "COALESCE(alias, '')"), patterns)
        cursor = await self._c.execute(
            "SELECT uid, p_id, fio, COALESCE(alias, '') AS alias "
            f"FROM user_patients WHERE {clause} ORDER BY fio LIMIT ?",
            (*params, limit),
        )
        rows = await cursor.fetchall()
        return [
            {
                "uid": str(row["uid"]),
                "p_id": str(row["p_id"]),
                "fio": str(row["fio"]),
                "alias": str(row["alias"]),
            }
            for row in rows
        ]

    async def search_clinics(
        self, query: str, limit: int = SEARCH_LIMIT
    ) -> list[dict[str, str]]:
        """Клиники, у которых совпало название или город."""
        patterns = _like_patterns(query)
        clause, params = _match_clause(("name", "COALESCE(city, '')"), patterns)
        cursor = await self._c.execute(
            "SELECT clinic_id, name, COALESCE(city, '') AS city, type "
            f"FROM clinics WHERE {clause} ORDER BY name LIMIT ?",
            (*params, limit),
        )
        rows = await cursor.fetchall()
        return [
            {
                "clinic_id": str(row["clinic_id"]),
                "name": str(row["name"]),
                "city": str(row["city"]),
                "type": str(row["type"]),
            }
            for row in rows
        ]
