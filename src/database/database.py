"""
Фасад Database — делегирует все операции в специализированные репозитории.

Сохраняет полную обратную совместимость: все публичные методы, доступные ранее
напрямую в классе Database, продолжают работать с теми же сигнатурами.
"""

from __future__ import annotations

import aiosqlite
from loguru import logger

from src.database.connection import DatabaseConnection
from src.database.repo_clinics import (
    ClinicRepository,
    detect_clinic_city,  # реэкспорт
    detect_clinic_type,  # реэкспорт
)
from src.database.repo_config import ConfigRepository
from src.database.repo_doctors import DoctorRepository
from src.database.repo_logs import LogRepository
from src.database.repo_monitoring import MonitoringRepository
from src.database.repo_users import UserRepository
from src.database.types import (
    ClinicInfo,
    DoctorEntry,
    LastMessageEntry,
    MonitoringEntry,
    MonitoringLogEntry,
    PatientInfo,
    UserData,
)

__all__ = [
    "Database",
    "detect_clinic_city",
    "detect_clinic_type",
]


class Database:
    """Фасад, делегирующий операции в репозитории.

    Публичные атрибуты-репозитории (users, doctors, clinics, monitoring,
    config, logs) доступны для прямого использования, но для обратной
    совместимости все публичные методы продублированы как прокси.
    """

    def __init__(self, db_path: str):
        self._conn = DatabaseConnection(db_path)
        self.users = UserRepository(self._conn)
        self.doctors = DoctorRepository(self._conn)
        self.clinics = ClinicRepository(self._conn)
        self.monitoring = MonitoringRepository(self._conn)
        self.config = ConfigRepository(self._conn)
        self.logs = LogRepository(self._conn)

    @property
    def conn(self) -> aiosqlite.Connection | None:
        """Активное соединение с БД или None (для обратной совместимости)."""
        return self._conn.conn

    @property
    def db_path(self) -> str:
        """Путь к файлу БД."""
        return self._conn.db_path

    # ── Управление соединением ──────────────────────────────

    async def connect(self) -> None:
        """Открыть соединение и создать таблицы (делегирует в DatabaseConnection)."""
        await self._conn.connect()

    async def close(self) -> None:
        """Закрыть соединение (делегирует в DatabaseConnection)."""
        await self._conn.close()

    # ── Пользователи ────────────────────────────────────────

    async def get_user(self, uid: str) -> UserData | None:
        """Возвращает все данные пользователя: пациенты, мониторинг, last_messages."""
        return await self.users.get_user(uid)

    async def get_all_user_ids(self) -> list[str]:
        """Возвращает все уникальные uid из таблиц пользователей."""
        return await self.users.get_all_user_ids()

    async def get_user_patients(self, uid: str) -> dict[str, PatientInfo]:
        """Возвращает словарь пациентов пользователя."""
        return await self.users.get_user_patients(uid)

    async def add_patient(
        self,
        uid: str,
        p_id: str,
        fio: str,
        birthday: str,
        alias: str | None,
        confirmed_clinics: list | None = None,
    ) -> None:
        """Добавляет или обновляет запись пациента."""
        return await self.users.add_patient(
            uid, p_id, fio, birthday, alias, confirmed_clinics
        )

    async def update_patient_confirmed_clinics(
        self, uid: str, p_id: str, confirmed_clinics: list
    ) -> None:
        """Обновляет список подтверждённых клиник пациента."""
        return await self.users.update_patient_confirmed_clinics(
            uid, p_id, confirmed_clinics
        )

    async def set_last_message(
        self, uid: str, p_id: str, d_id: str, msg_id: int, ts: float = 0
    ) -> None:
        """Сохраняет ID последнего сообщения."""
        return await self.users.set_last_message(uid, p_id, d_id, msg_id, ts)

    async def get_last_message(
        self, uid: str, p_id: str, d_id: str
    ) -> LastMessageEntry | None:
        """Возвращает запись о последнем сообщении или None."""
        return await self.users.get_last_message(uid, p_id, d_id)

    # ── Мониторинг ──────────────────────────────────────────

    async def get_user_monitoring(
        self, uid: str
    ) -> dict[str, dict[str, MonitoringEntry]]:
        """Возвращает словарь мониторинга пользователя."""
        return await self.monitoring.get_user_monitoring(uid)

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
        return await self.monitoring.add_monitoring_entry(
            uid, p_id, d_id, name, clinic_id, specialty, date
        )

    async def remove_monitoring_entry(self, uid: str, p_id: str, d_id: str) -> None:
        """Удаляет запись мониторинга."""
        return await self.monitoring.remove_monitoring_entry(uid, p_id, d_id)

    async def clear_all_monitoring(self, uid: str) -> None:
        """Удаляет все записи мониторинга пользователя."""
        return await self.monitoring.clear_all_monitoring(uid)

    async def delete_patient(self, uid: str, p_id: str) -> None:
        """Удаляет пациента и все связанные данные в одной транзакции."""
        return await self.monitoring.delete_patient(uid, p_id)

    # ── Врачи ───────────────────────────────────────────────

    async def get_clinic_doctors(self, clinic_id: str) -> dict[str, DoctorEntry]:
        """Возвращает словарь врачей клиники (ключ — doctor_id)."""
        return await self.doctors.get_clinic_doctors(clinic_id)

    async def get_clinic_specialties(self, clinic_id: str) -> list[dict[str, str]]:
        """Возвращает список уникальных специальностей для клиники."""
        return await self.doctors.get_clinic_specialties(clinic_id)

    async def upsert_doctor(
        self, clinic_id: str, doctor_id: str, name: str, specialty: str
    ) -> None:
        """Добавляет или обновляет запись врача."""
        return await self.doctors.upsert_doctor(clinic_id, doctor_id, name, specialty)

    async def merge_doctors(self, clinic_id: str, doctors: list[dict]) -> int:
        """Сохраняет список врачей в БД для указанной клиники.

        Создаёт запись клиники (если нет) и upsert-ит каждого врача.
        Возвращает количество **новых** врачей (ранее отсутствовавших в БД).
        """
        existing_name = await self.clinics.get_clinic_name(str(clinic_id))
        if existing_name is None:
            await self.clinics.upsert_clinic(str(clinic_id), "Unknown")

        # Получаем существующие doctor_id для этой клиники
        existing_doctors = await self.doctors.get_clinic_doctors(clinic_id)
        existing_ids: set[str] = set(existing_doctors.keys())

        new_count = 0
        for doc in doctors:
            raw_id = doc.get("IdDoc")
            if not raw_id:
                continue
            doc_id = str(raw_id)
            doc_name = doc.get("Name")
            if not doc_name:
                continue
            specialty = doc.get("SpesialityName", "")
            await self.doctors.upsert_doctor(clinic_id, doc_id, doc_name, specialty)
            if doc_id not in existing_ids:
                new_count += 1
                existing_ids.add(doc_id)  # учитываем при повторных doc_id в пакете

        return new_count

    async def search_doctors_by_name(self, query: str, limit: int = 20) -> list[dict]:
        """Поиск врачей по подстроке в имени (глобально)."""
        return await self.doctors.search_doctors_by_name(query, limit)

    # ── Клиники ─────────────────────────────────────────────

    async def upsert_clinic(self, clinic_id: str, name: str) -> None:
        """Обновляет название клиники. Не затирает type/is_active/city."""
        return await self.clinics.upsert_clinic(clinic_id, name)

    async def get_all_clinic_ids(self) -> list[str]:
        """Возвращает все clinic_id из таблицы clinics."""
        return await self.clinics.get_all_clinic_ids()

    async def get_clinic_name(self, clinic_id: str) -> str | None:
        """Возвращает название клиники по ID или None."""
        return await self.clinics.get_clinic_name(clinic_id)

    async def get_all_clinic_names(self) -> dict[str, str]:
        """Возвращает словарь {clinic_id: name} для всех клиник."""
        return await self.clinics.get_all_clinic_names()

    async def get_clinic_type(self, clinic_id: str) -> str | None:
        """Возвращает тип клиники (adult/child/all)."""
        return await self.clinics.get_clinic_type(clinic_id)

    async def get_clinic_discovery_patients(self, clinic_id: str) -> tuple[str, str]:
        """Возвращает per-клиника discovery пациентов (adult, child)."""
        return await self.clinics.get_clinic_discovery_patients(clinic_id)

    async def get_active_clinics(self) -> list[ClinicInfo]:
        """Возвращает список активных клиник с полными данными."""
        return await self.clinics.get_active_clinics()

    async def get_distinct_cities(self) -> list[str]:
        """Возвращает отсортированный список уникальных городов активных клиник."""
        return await self.clinics.get_distinct_cities()

    async def get_active_clinic_ids(self) -> list[str]:
        """Возвращает список clinic_id активных клиник (is_active = 1)."""
        return await self.clinics.get_active_clinic_ids()

    async def get_clinic_doctor_count(self, clinic_id: str) -> int:
        """Возвращает количество врачей в клинике."""
        return await self.clinics.get_clinic_doctor_count(clinic_id)

    # ── Конфигурация ────────────────────────────────────────

    async def get_config(self, key: str, default: str = "") -> str:
        """Возвращает значение конфига по ключу."""
        return await self.config.get_config(key, default)

    async def set_config(self, key: str, value: str) -> None:
        """Устанавливает значение конфига."""
        return await self.config.set_config(key, value)

    async def get_all_config(self) -> dict[str, str]:
        """Возвращает все конфиги как dict."""
        return await self.config.get_all_config()

    async def seed_config_from_defaults(self) -> None:
        """Заполняет таблицу config дефолтными значениями из settings."""
        return await self.config.seed_config_from_defaults()

    # ── Логи мониторинга ────────────────────────────────────

    async def add_monitoring_log(
        self,
        uid: str,
        p_id: str,
        d_id: str,
        doctor_name: str,
        patient_name: str,
        specialty: str,
        clinic_name: str,
        slot_date: str,
        status: str,
        ts: float,
    ) -> None:
        """Добавляет запись в лог мониторинга."""
        return await self.logs.add_monitoring_log(
            uid,
            p_id,
            d_id,
            doctor_name,
            patient_name,
            specialty,
            clinic_name,
            slot_date,
            status,
            ts,
        )

    async def get_user_monitoring_logs(
        self, uid: str, limit: int = 5000, offset: int = 0
    ) -> list[MonitoringLogEntry]:
        """Возвращает логи мониторинга для пользователя."""
        return await self.logs.get_user_monitoring_logs(uid, limit, offset)

    async def get_user_monitoring_logs_count(self, uid: str) -> int:
        """Возвращает количество записей лога для пользователя."""
        return await self.logs.get_user_monitoring_logs_count(uid)

    async def get_all_monitoring_logs(
        self,
        limit: int = 50,
        offset: int = 0,
        uid: str | None = None,
        status: str | None = None,
    ) -> list[MonitoringLogEntry]:
        """Возвращает логи мониторинга с пагинацией и фильтрацией."""
        return await self.logs.get_all_monitoring_logs(limit, offset, uid, status)

    async def get_all_monitoring_logs_count(
        self, uid: str | None = None, status: str | None = None
    ) -> int:
        """Возвращает количество записей лога мониторинга (с фильтрами)."""
        return await self.logs.get_all_monitoring_logs_count(uid, status)

    # ── Статистика (агрегация) ──────────────────────────────

    async def get_total_stats(self) -> dict:
        """Агрегированная статистика для главной страницы дашборда."""
        c = self._conn.conn
        if c is None:
            raise RuntimeError("Database connection not initialized")
        cursor = await c.execute("""
            SELECT
              (SELECT COUNT(DISTINCT uid) FROM (
                SELECT uid FROM user_patients
                UNION
                SELECT uid FROM user_monitoring
              )) as total_users,
              (SELECT COUNT(*) FROM user_patients) as total_patients,
              (SELECT COUNT(*) FROM user_monitoring) as total_monitored_doctors
        """)
        row = await cursor.fetchone()
        return {
            "total_users": row["total_users"] if row else 0,
            "total_patients": row["total_patients"] if row else 0,
            "total_monitored_doctors": row["total_monitored_doctors"] if row else 0,
        }

    # ── Specialty Aliases ───────────────────────────────────

    async def get_all_specialty_aliases(self) -> dict[str, str]:
        """Возвращает все псевдонимы специальностей."""
        c = self._conn.conn
        if c is None:
            raise RuntimeError("Database connection not initialized")
        cursor = await c.execute("SELECT full_name, short_name FROM specialty_aliases")
        rows = await cursor.fetchall()
        return {row["full_name"]: row["short_name"] for row in rows}

    async def upsert_specialty_alias(self, full_name: str, short_name: str) -> None:
        """Добавляет или обновляет псевдоним специальности."""
        c = self._conn.conn
        if c is None:
            raise RuntimeError("Database connection not initialized")
        await c.execute(
            "INSERT OR REPLACE INTO specialty_aliases "
            "(full_name, short_name) VALUES (?, ?)",
            (full_name, short_name),
        )
        await c.commit()

    async def seed_specialty_aliases_from_fallback(self) -> None:
        """
        Заполняет таблицу specialty_aliases из SPECIALTY_ALIASES, если она пуста.
        """
        c = self._conn.conn
        if c is None:
            return
        try:
            cursor = await c.execute("SELECT COUNT(*) as cnt FROM specialty_aliases")
            row = await cursor.fetchone()
            if row and row["cnt"] > 0:
                return  # уже есть данные

            from src.utils.helpers import SPECIALTY_ALIASES

            for full_name, short_name in SPECIALTY_ALIASES.items():
                await self.upsert_specialty_alias(full_name, short_name)
            logger.info(
                "Таблица specialty_aliases заполнена из SPECIALTY_ALIASES (%s записей)",
                len(SPECIALTY_ALIASES),
            )
        except Exception as e:
            logger.error(
                "Не удалось заполнить specialty_aliases из fallback: {}",
                e,
                exc_info=True,
            )

    async def seed_clinics_and_doctors_from_file(
        self, json_path: str = "data/seed/clinics_doctors.json", force: bool = False
    ) -> tuple[int, int]:
        """
        Загружает клиники и врачей из JSON-файла, если таблица clinics пуста.

        При ``force=True`` выполняет INSERT OR IGNORE даже при непустой таблице.
        Возвращает (clinics_added, doctors_added).
        """
        c = self._conn.conn
        if c is None:
            return (0, 0)
        try:
            from src.database.seed import seed_clinics_and_doctors_from_json

            return await seed_clinics_and_doctors_from_json(c, json_path, force=force)
        except Exception as e:
            logger.error(
                "Не удалось загрузить seed-данные из {}: {}",
                json_path,
                e,
                exc_info=True,
            )
            return (0, 0)
