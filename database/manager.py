"""
DatabaseManager — адаптер поверх Database (SQLite).
Сохраняет обратную совместимость с существующими хендлерами и сервисами.
"""

import copy
import json
import logging
from typing import Any, Dict

from database.database import Database

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Обёртка над Database с API, совместимым со старым JSON-менеджером."""

    def __init__(self, db: Database):
        self._db = db
        # data — прокси-свойство для обратной совместимости с monitor.py / healthcheck.py
        self._data_cache: Dict[str, Any] = {}

    @property
    def data(self) -> Dict[str, Any]:
        """Возвращает deepcopy кэша (защита от случайной мутации)."""
        return copy.deepcopy(self._data_cache)

    async def refresh_cache(self):
        """Перечитать всех пользователей из SQLite в кэш data."""
        self._data_cache = {}
        uids = await self._db.get_all_user_ids()
        for uid in uids:
            user = await self._db.get_user(uid)
            if user is not None:
                self._data_cache[uid] = user

    # ── Пользователи ────────────────────────────────────────

    def get_user_data(self, uid: str) -> Dict[str, Any]:
        """
        Синхронный метод для обратной совместимости.
        Возвращает данные из кэша, создаёт запись по умолчанию если нет.
        """
        uid = str(uid)
        if uid not in self._data_cache:
            # Создаём структуру по умолчанию
            self._data_cache[uid] = {
                "patients": {},
                "monitoring": {},
                "last_messages": {},
                "last_notification_id": None,
            }
        elif "last_messages" not in self._data_cache[uid]:
            self._data_cache[uid]["last_messages"] = {}
        return self._data_cache[uid]

    async def _ensure_user_in_db(self, uid: str):
        """Гарантирует, что пользователь есть в SQLite."""
        user = await self._db.get_user(str(uid))
        if user is None:
            await self._db.ensure_user(str(uid))

    async def update_user(self, uid: str, update_dict: Dict[str, Any]):
        """Обновить данные пользователя (сохраняет в SQLite и обновляет кэш)."""
        uid = str(uid)
        await self._ensure_user_in_db(uid)
        # Перечитываем пользователя из SQLite в кэш
        user = await self._db.get_user(uid)
        if user:
            self._data_cache[uid] = user
        user_data = self.get_user_data(uid)
        user_data.update(update_dict)
        # Единая транзакция: все поля пишутся атомарно
        c = self._db._conn
        if c is None:
            raise RuntimeError("Database connection not initialized")
        await c.execute("BEGIN")
        try:
            await c.execute(
                "UPDATE users SET patients = ? WHERE uid = ?",
                (json.dumps(user_data.get("patients", {}), ensure_ascii=False), uid),
            )
            await c.execute(
                "UPDATE users SET monitoring = ? WHERE uid = ?",
                (json.dumps(user_data.get("monitoring", {}), ensure_ascii=False), uid),
            )
            await c.execute(
                "UPDATE users SET last_messages = ? WHERE uid = ?",
                (
                    json.dumps(user_data.get("last_messages", {}), ensure_ascii=False),
                    uid,
                ),
            )
            if "last_notification_id" in update_dict:
                await c.execute(
                    "UPDATE users SET last_notification_id = ? WHERE uid = ?",
                    (update_dict["last_notification_id"], uid),
                )
            # Произвольные поля сохраняем в extra
            known_fields = {
                "patients",
                "monitoring",
                "last_messages",
                "last_notification_id",
            }
            extra_fields = {
                k: v for k, v in update_dict.items() if k not in known_fields
            }
            if extra_fields:
                await self._db.update_extra(uid, extra_fields)
            await c.commit()
        except Exception:
            await c.rollback()
            raise
        # Обновляем кэш после записи
        updated_user = await self._db.get_user(uid)
        if updated_user:
            self._data_cache[uid] = updated_user

    async def set_last_message_id(
        self, uid: str, p_id: str, d_id: str, message_id: int
    ):
        uid = str(uid)
        user_data = self.get_user_data(uid)
        key = f"{p_id}_{d_id}"
        user_data["last_messages"][key] = message_id
        await self._db.update_user_field(
            uid, "last_messages", user_data["last_messages"]
        )

    def get_last_message_id(self, uid: str, p_id: str, d_id: str) -> int | None:
        uid = str(uid)
        user_data = self.get_user_data(uid)
        key = f"{p_id}_{d_id}"
        return user_data["last_messages"].get(key)

    async def add_patient(self, uid: str, p_id: str, p_info: Dict[str, Any]):
        uid = str(uid)
        user_data = self.get_user_data(uid)
        p_info["confirmed_clinics"] = p_info.get("confirmed_clinics", [])
        user_data["patients"][p_id] = p_info
        await self._db.update_user_field(uid, "patients", user_data["patients"])

    async def add_confirmed_clinic(self, uid: str, p_id: str, clinic_id: int):
        uid = str(uid)
        user_data = self.get_user_data(uid)
        if p_id in user_data["patients"]:
            if "confirmed_clinics" not in user_data["patients"][p_id]:
                user_data["patients"][p_id]["confirmed_clinics"] = []

            if clinic_id not in user_data["patients"][p_id]["confirmed_clinics"]:
                user_data["patients"][p_id]["confirmed_clinics"].append(clinic_id)
                await self._db.update_user_field(uid, "patients", user_data["patients"])

    async def toggle_monitoring(
        self, uid: str, p_id: str, d_id: str, d_name: str, clinic_id: str, d_spec: str
    ):
        uid = str(uid)
        user_data = self.get_user_data(uid)
        if p_id not in user_data["monitoring"]:
            user_data["monitoring"][p_id] = {}

        if d_id in user_data["monitoring"][p_id]:
            del user_data["monitoring"][p_id][d_id]
        else:
            user_data["monitoring"][p_id][d_id] = {
                "name": d_name,
                "clinic_id": clinic_id,
                "specialty": d_spec,
            }
        await self._db.update_user_field(uid, "monitoring", user_data["monitoring"])

    async def stop_all_monitoring(self, uid: str):
        uid = str(uid)
        if uid in self._data_cache:
            self._data_cache[uid]["monitoring"] = {}
            await self._db.update_user_field(uid, "monitoring", {})

    async def delete_patient(self, uid: str, p_id: str):
        uid = str(uid)
        user_data = self.get_user_data(uid)
        if p_id in user_data["patients"]:
            del user_data["patients"][p_id]
        if p_id in user_data["monitoring"]:
            del user_data["monitoring"][p_id]
        await self._db.update_user_field(uid, "patients", user_data["patients"])
        await self._db.update_user_field(uid, "monitoring", user_data["monitoring"])

    # ── Врачи (делегирование в Database) ────────────────────

    async def get_doctors_for_clinic(self, clinic_id: str) -> dict:
        """Возвращает {doctor_id: {name, specialty}} для указанной клиники."""
        return await self._db.get_clinic_doctors(str(clinic_id))

    async def merge_doctors(self, clinic_id: str, doctors: list):
        return await self._db.merge_doctors(str(clinic_id), doctors)

    # ── Управление подключением ─────────────────────────────

    async def load(self, run_migration: bool = False):
        """Инициализация: подключение к SQLite и загрузка кэша."""
        await self._db.connect()
        if run_migration:
            from config import settings

            await self._db.migrate_from_json(
                settings.USERS_JSON_PATH,
                settings.DOCTORS_JSON_PATH,
            )
        await self.refresh_cache()

    async def save(self):
        """Синхронизировать кэш с SQLite (вызывается при изменении данных)."""
        # Данные уже сохраняются в каждом методе, этот метод оставлен для совместимости
        pass
