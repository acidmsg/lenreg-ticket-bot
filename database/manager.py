import json
import aiofiles
import os
import asyncio
from typing import Dict, Any, Optional

class DatabaseManager:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.data: Dict[str, Any] = {}
        self._lock = asyncio.Lock()

    async def load(self):
        if os.path.exists(self.file_path):
            async with aiofiles.open(self.file_path, mode='r', encoding='utf-8') as f:
                content = await f.read()
                if content:
                    self.data = json.loads(content)
        else:
            self.data = {}

    async def save(self):
        async with self._lock:
            async with aiofiles.open(self.file_path, mode='w', encoding='utf-8') as f:
                await f.write(json.dumps(self.data, ensure_ascii=False, indent=4))

    def get_user_data(self, uid: str) -> Dict[str, Any]:
        uid = str(uid)
        if uid not in self.data:
            self.data[uid] = {"patients": {}, "monitoring": {}, "last_messages": {}}
        elif "last_messages" not in self.data[uid]:
            self.data[uid]["last_messages"] = {}
        return self.data[uid]

    async def update_user(self, uid: str, update_dict: Dict[str, Any]):
        uid = str(uid)
        user_data = self.get_user_data(uid)
        user_data.update(update_dict)
        await self.save()

    async def set_last_message_id(self, uid: str, p_id: str, d_id: str, message_id: int):
        uid = str(uid)
        user_data = self.get_user_data(uid)
        key = f"{p_id}_{d_id}"
        user_data["last_messages"][key] = message_id
        await self.save()

    def get_last_message_id(self, uid: str, p_id: str, d_id: str) -> Optional[int]:
        uid = str(uid)
        user_data = self.get_user_data(uid)
        key = f"{p_id}_{d_id}"
        return user_data["last_messages"].get(key)

    async def add_patient(self, uid: str, p_id: str, p_info: Dict[str, Any]):
        uid = str(uid)
        user_data = self.get_user_data(uid)
        p_info["confirmed_clinics"] = p_info.get("confirmed_clinics", [])
        user_data["patients"][p_id] = p_info
        await self.save()

    async def add_confirmed_clinic(self, uid: str, p_id: str, clinic_id: int):
        uid = str(uid)
        user_data = self.get_user_data(uid)
        if p_id in user_data["patients"]:
            if "confirmed_clinics" not in user_data["patients"][p_id]:
                user_data["patients"][p_id]["confirmed_clinics"] = []

            if clinic_id not in user_data["patients"][p_id]["confirmed_clinics"]:
                user_data["patients"][p_id]["confirmed_clinics"].append(clinic_id)
                await self.save()

    async def toggle_monitoring(self, uid: str, p_id: str, d_id: str, d_name: str, clinic_id: str, d_spec: str):
        uid = str(uid)
        user_data = self.get_user_data(uid)
        if p_id not in user_data["monitoring"]:
            user_data["monitoring"][p_id] = {}

        if d_id in user_data["monitoring"][p_id]:
            del user_data["monitoring"][p_id][d_id]
        else:
            user_data["monitoring"][p_id][d_id] = {"name": d_name, "clinic_id": clinic_id, "specialty": d_spec}
        await self.save()

    async def stop_all_monitoring(self, uid: str):
        uid = str(uid)
        if uid in self.data:
            self.data[uid]["monitoring"] = {}
            await self.save()

    async def delete_patient(self, uid: str, p_id: str):
        uid = str(uid)
        user_data = self.get_user_data(uid)
        if p_id in user_data["patients"]:
            del user_data["patients"][p_id]
        if p_id in user_data["monitoring"]:
            del user_data["monitoring"][p_id]
        await self.save()
