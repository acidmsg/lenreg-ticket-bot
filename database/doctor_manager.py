import json
import aiofiles
import os
import asyncio
from typing import Dict, Any

class DoctorManager:
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

    async def merge_doctors(self, clinic_id: str, doctors: list):
        if clinic_id not in self.data:
            self.data[clinic_id] = {"name": "Unknown", "doctors": {}}

        # Merge logic
        for doc in doctors:
            doc_id = str(doc.get("IdDoc"))
            doc_name = doc.get("Name")
            specialty = doc.get("SpesialityName", "")

            if doc_name and doc_id:
                # Сохраняем расширенную информацию
                self.data[clinic_id]["doctors"][doc_id] = {
                    "name": doc_name,
                    "specialty": specialty
                }

        await self.save()
