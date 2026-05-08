"""
Тесты для utils/cache.py.
"""

import json
import os

import pytest


class TestCache:
    """Набор тестов для функций кэширования."""

    async def test_load_empty_when_no_file(self, temp_cache_path):
        """load_monitoring_cache возвращает {} при отсутствии файла."""
        from utils.cache import load_monitoring_cache

        data = await load_monitoring_cache()
        assert data == {}

    async def test_save_and_load(self, temp_cache_path):
        """save_monitoring_cache + load_monitoring_cache работают согласованно."""
        from utils.cache import load_monitoring_cache, save_monitoring_cache

        test_data = {"key1": "value1", "key2": ["a", "b"]}
        await save_monitoring_cache(test_data)
        loaded = await load_monitoring_cache()
        assert loaded == test_data

    async def test_update_cache_key(self, temp_cache_path):
        """update_cache_key обновляет одно значение."""
        from utils.cache import read_cache_key, update_cache_key

        await update_cache_key("test_key", "test_value")
        val = await read_cache_key("test_key")
        assert val == "test_value"

    async def test_update_cache_key_overwrites(self, temp_cache_path):
        """update_cache_key перезаписывает существующий ключ."""
        from utils.cache import read_cache_key, update_cache_key

        await update_cache_key("mykey", "old")
        await update_cache_key("mykey", "new")
        val = await read_cache_key("mykey")
        assert val == "new"

    async def test_read_cache_key_nonexistent(self, temp_cache_path):
        """read_cache_key возвращает None для отсутствующего ключа."""
        from utils.cache import read_cache_key

        val = await read_cache_key("nonexistent")
        assert val is None

    async def test_swap_cache_key_returns_old(self, temp_cache_path):
        """swap_cache_key возвращает старое значение."""
        from utils.cache import swap_cache_key, update_cache_key

        await update_cache_key("k", "old_value")
        old = await swap_cache_key("k", "new_value")
        assert old == "old_value"

    async def test_swap_cache_key_first_time(self, temp_cache_path):
        """swap_cache_key возвращает None при первом сохранении."""
        from utils.cache import swap_cache_key

        old = await swap_cache_key("fresh_key", "value")
        assert old is None

    async def test_delete_cache_key(self, temp_cache_path):
        """delete_cache_key удаляет ключ."""
        from utils.cache import delete_cache_key, read_cache_key, update_cache_key

        await update_cache_key("todelete", "value")
        await delete_cache_key("todelete")
        val = await read_cache_key("todelete")
        assert val is None

    async def test_delete_cache_key_nonexistent(self, temp_cache_path):
        """delete_cache_key не падает при удалении отсутствующего ключа."""
        from utils.cache import delete_cache_key

        # Не должно быть исключения
        await delete_cache_key("nonexistent")

    async def test_atomicity_temp_file_cleaned(self, temp_cache_path):
        """Временный .tmp файл не остаётся после операций."""
        from utils.cache import update_cache_key

        await update_cache_key("atomic", "test")
        temp_path = temp_cache_path + ".tmp"
        assert not os.path.exists(temp_path)

    async def test_multiple_keys(self, temp_cache_path):
        """Несколько ключей корректно сохраняются и читаются."""
        from utils.cache import load_monitoring_cache, read_cache_key, update_cache_key

        await update_cache_key("a", 1)
        await update_cache_key("b", 2)
        await update_cache_key("c", 3)
        assert await read_cache_key("a") == 1
        assert await read_cache_key("b") == 2
        assert await read_cache_key("c") == 3
        cache = await load_monitoring_cache()
        assert len(cache) == 3

    async def test_store_list_value(self, temp_cache_path):
        """Кэш корректно хранит списки."""
        from utils.cache import read_cache_key, update_cache_key

        slots = ["2026-05-10 в 10:00", "2026-05-10 в 11:00"]
        await update_cache_key("slots", slots)
        val = await read_cache_key("slots")
        assert val == slots
        assert isinstance(val, list)
