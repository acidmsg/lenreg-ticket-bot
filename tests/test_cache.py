"""
Тесты для utils/cache.py.
"""

import json
import os

import pytest


class TestCache:
    """Набор тестов для функций кэширования."""

    async def test_swap_cache_key_first_time(self, temp_cache_path):
        """swap_cache_key возвращает None при первом сохранении."""
        from utils.cache import swap_cache_key

        old = await swap_cache_key("fresh_key", "value")
        assert old is None

    async def test_swap_cache_key_returns_old(self, temp_cache_path):
        """swap_cache_key возвращает старое значение."""
        from utils.cache import swap_cache_key

        await swap_cache_key("k", "old_value")
        old = await swap_cache_key("k", "new_value")
        assert old == "old_value"

    async def test_delete_cache_keys_by_prefix(self, temp_cache_path):
        """delete_cache_keys_by_prefix удаляет ключи по префиксу."""
        from utils.cache import delete_cache_keys_by_prefix, swap_cache_key

        await swap_cache_key("a_1", "x")
        await swap_cache_key("a_2", "y")
        await swap_cache_key("b_1", "z")

        deleted = await delete_cache_keys_by_prefix("a_")
        assert deleted == 2

    async def test_delete_cache_keys_by_prefix_empty(self, temp_cache_path):
        """delete_cache_keys_by_prefix не падает при пустом файле."""
        from utils.cache import delete_cache_keys_by_prefix

        deleted = await delete_cache_keys_by_prefix("nonexistent")
        assert deleted == 0

    async def test_atomicity_temp_file_cleaned(self, temp_cache_path):
        """Временный .tmp файл не остаётся после операций."""
        from utils.cache import swap_cache_key

        await swap_cache_key("atomic", "test")
        temp_path = temp_cache_path + ".tmp"
        assert not os.path.exists(temp_path)

    async def test_multiple_keys(self, temp_cache_path):
        """Несколько ключей корректно сохраняются."""
        from utils.cache import swap_cache_key

        await swap_cache_key("a", 1)
        await swap_cache_key("b", 2)
        await swap_cache_key("c", 3)

        # Проверяем через swap (чтение + запись того же значения)
        old_a = await swap_cache_key("a", 1)
        old_b = await swap_cache_key("b", 2)
        old_c = await swap_cache_key("c", 3)
        assert old_a == 1
        assert old_b == 2
        assert old_c == 3

    async def test_store_list_value(self, temp_cache_path):
        """Кэш корректно хранит списки."""
        from utils.cache import swap_cache_key

        slots = ["2026-05-10 в 10:00", "2026-05-10 в 11:00"]
        old = await swap_cache_key("slots", slots)
        assert old is None

        old2 = await swap_cache_key("slots", slots)
        assert old2 == slots
        assert isinstance(old2, list)
