"""
DatabaseManager — адаптер поверх Database (SQLite).
"""

import asyncio
import copy
import logging
import time
from typing import Any, Dict

from src.database.database import Database

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Обёртка над Database."""

    def __init__(self, db: Database):
        self._db = db
        self._data_cache: Dict[str, Any] = {}
        self._lock = asyncio.Lock()

    @property
    def data(self) -> Dict[str, Any]:
        return copy.deepcopy(self._data_cache)

    async def refresh_cache(self):
        async with self._lock:
            self._data_cache = {}
            uids = await self._db.get_all_user_ids()
            for uid in uids:
                user = await self._db.get_user(uid)
                if user is not None:
                    self._data_cache[uid] = user

    # ── Пользователи ────────────────────────────────────────

    async def get_user_data(self, uid: str) -> Dict[str, Any]:
        """Потокобезопасное получение/создание данных пользователя в кэше."""
        async with self._lock:
            return self._get_user_data_nolock(uid)

    def _get_user_data_nolock(self, uid: str) -> Dict[str, Any]:
        """Внутренняя версия без захвата лока (вызывать только под self._lock)."""
        uid = str(uid)
        if uid not in self._data_cache:
            self._data_cache[uid] = {
                "patients": {},
                "monitoring": {},
                "last_messages": {},
            }
        elif "last_messages" not in self._data_cache[uid]:
            self._data_cache[uid]["last_messages"] = {}
        return self._data_cache[uid]

    async def _replace_patients(self, uid: str, patients: Dict[str, Any]):
        c = self._db._conn
        if c is None:
            raise RuntimeError("Database connection not initialized")
        await c.execute("DELETE FROM user_patients WHERE uid = ?", (uid,))
        for p_id, p_info in patients.items():
            await self._db.add_patient(
                uid=uid,
                p_id=p_id,
                fio=p_info.get("fio", ""),
                bday=p_info.get("bday", ""),
                alias=p_info.get("alias"),
                confirmed_clinics=p_info.get("confirmed_clinics", []),
            )

    async def _replace_monitoring(self, uid: str, monitoring: Dict[str, Any]):
        c = self._db._conn
        if c is None:
            raise RuntimeError("Database connection not initialized")
        await c.execute("DELETE FROM user_monitoring WHERE uid = ?", (uid,))
        for p_id, doctors in monitoring.items():
            for d_id, d_info in doctors.items():
                if isinstance(d_info, dict):
                    await self._db.add_monitoring_entry(
                        uid=uid,
                        p_id=p_id,
                        d_id=d_id,
                        name=d_info.get("name", ""),
                        clinic_id=d_info.get("clinic_id", ""),
                        specialty=d_info.get("specialty", ""),
                    )

    async def update_user(self, uid: str, update_dict: Dict[str, Any]):
        """Атомарное обновление данных пользователя (кэш + БД)."""
        uid = str(uid)
        async with self._lock:
            user = await self._db.get_user(uid)
            if user:
                self._data_cache[uid] = user
            user_data = self._get_user_data_nolock(uid)
            user_data.update(update_dict)
            c = self._db._conn
            if c is None:
                raise RuntimeError("Database connection not initialized")
            await c.execute("BEGIN")
            try:
                if "patients" in update_dict:
                    await self._replace_patients(uid, user_data.get("patients", {}))
                if "monitoring" in update_dict:
                    await self._replace_monitoring(uid, user_data.get("monitoring", {}))
                if "last_messages" in update_dict:
                    lm_data = update_dict["last_messages"]
                    await c.execute(
                        "DELETE FROM user_last_messages WHERE uid = ?",
                        (uid,),
                    )
                    for key, val in lm_data.items():
                        parts = key.split("_", 1)
                        if len(parts) == 2:
                            p_id, d_id = parts
                            msg_id = val.get("msg_id") if isinstance(val, dict) else val
                            ts = val.get("ts", 0) if isinstance(val, dict) else 0
                            if msg_id is not None:
                                await c.execute(
                                    "INSERT INTO user_last_messages (uid, p_id, d_id, msg_id, ts) VALUES (?, ?, ?, ?, ?)",
                                    (uid, p_id, d_id, int(msg_id), float(ts)),
                                )
                await c.commit()
            except Exception:
                await c.rollback()
                raise
            updated_user = await self._db.get_user(uid)
            if updated_user:
                self._data_cache[uid] = updated_user

    async def set_last_message_id(
        self, uid: str, p_id: str, d_id: str, message_id: int
    ):
        uid = str(uid)
        async with self._lock:
            user_data = self._get_user_data_nolock(uid)
            key = f"{p_id}_{d_id}"
            ts = time.time()
            user_data["last_messages"][key] = {"msg_id": message_id, "ts": ts}
            await self._db.set_last_message(uid, p_id, d_id, message_id, ts)

    async def get_last_message_id(self, uid: str, p_id: str, d_id: str) -> int | None:
        """Потокобезопасное получение ID последнего сообщения."""
        uid = str(uid)
        async with self._lock:
            user_data = self._get_user_data_nolock(uid)
            key = f"{p_id}_{d_id}"
            val = user_data["last_messages"].get(key)
            if isinstance(val, dict):
                return val.get("msg_id")
            if isinstance(val, int):
                return val
            return None

    async def add_patient(self, uid: str, p_id: str, p_info: Dict[str, Any]):
        uid = str(uid)
        async with self._lock:
            user_data = self._get_user_data_nolock(uid)
            p_info["confirmed_clinics"] = p_info.get("confirmed_clinics", [])
            user_data["patients"][p_id] = p_info
            await self._db.add_patient(
                uid=uid,
                p_id=p_id,
                fio=p_info.get("fio", ""),
                bday=p_info.get("bday", ""),
                alias=p_info.get("alias"),
                confirmed_clinics=p_info.get("confirmed_clinics", []),
            )
            updated = await self._db.get_user(uid)
            if updated:
                self._data_cache[uid] = updated

    async def add_confirmed_clinic(self, uid: str, p_id: str, clinic_id: int):
        uid = str(uid)
        async with self._lock:
            user_data = self._get_user_data_nolock(uid)
            if p_id in user_data["patients"]:
                if "confirmed_clinics" not in user_data["patients"][p_id]:
                    user_data["patients"][p_id]["confirmed_clinics"] = []

                if clinic_id not in user_data["patients"][p_id]["confirmed_clinics"]:
                    user_data["patients"][p_id]["confirmed_clinics"].append(clinic_id)
                    await self._db.update_patient_confirmed_clinics(
                        uid, p_id, user_data["patients"][p_id]["confirmed_clinics"]
                    )
                    updated = await self._db.get_user(uid)
                    if updated:
                        self._data_cache[uid] = updated

    async def toggle_monitoring(
        self, uid: str, p_id: str, d_id: str, d_name: str, clinic_id: str, d_spec: str
    ):
        uid = str(uid)
        async with self._lock:
            user_data = self._get_user_data_nolock(uid)
            if p_id not in user_data["monitoring"]:
                user_data["monitoring"][p_id] = {}

            if d_id in user_data["monitoring"][p_id]:
                del user_data["monitoring"][p_id][d_id]
                await self._db.remove_monitoring_entry(uid, p_id, d_id)
            else:
                user_data["monitoring"][p_id][d_id] = {
                    "name": d_name,
                    "clinic_id": clinic_id,
                    "specialty": d_spec,
                }
                await self._db.add_monitoring_entry(
                    uid=uid,
                    p_id=p_id,
                    d_id=d_id,
                    name=d_name,
                    clinic_id=clinic_id,
                    specialty=d_spec,
                )
            updated = await self._db.get_user(uid)
            if updated:
                self._data_cache[uid] = updated

    async def stop_all_monitoring(self, uid: str):
        uid = str(uid)
        async with self._lock:
            if uid in self._data_cache:
                self._data_cache[uid]["monitoring"] = {}
            await self._db.clear_all_monitoring(uid)

    async def delete_patient(self, uid: str, p_id: str):
        uid = str(uid)
        async with self._lock:
            user_data = self._get_user_data_nolock(uid)
            if p_id in user_data["patients"]:
                del user_data["patients"][p_id]
            if p_id in user_data["monitoring"]:
                del user_data["monitoring"][p_id]
            await self._db.delete_patient(uid, p_id)
            updated = await self._db.get_user(uid)
            if updated:
                self._data_cache[uid] = updated

    # ── Врачи ───────────────────────────────────────────────

    async def get_doctors_for_clinic(self, clinic_id: str) -> dict:
        return await self._db.get_clinic_doctors(str(clinic_id))

    async def merge_doctors(self, clinic_id: str, doctors: list):
        return await self._db.merge_doctors(str(clinic_id), doctors)

    async def get_clinic_name(self, clinic_id: str) -> str | None:
        return await self._db.get_clinic_name(str(clinic_id))

    async def get_all_clinic_names(self) -> dict[str, str]:
        return await self._db.get_all_clinic_names()

    # ── Управление подключением ─────────────────────────────

    async def load(self):
        await self._db.connect()
        await self.refresh_cache()
