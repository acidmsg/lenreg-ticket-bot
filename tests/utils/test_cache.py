"""
Тесты для src/utils/cache.py (Redis-версия).

Использует fakeredis (autouse-фикстура в conftest.py) для эмуляции Redis.
Файловые операции заменены на Redis-команды.
"""


class TestSpamCache:
    """Тесты spam-защиты (Redis SET NX EX)."""

    async def test_is_spam_first_time(self):
        """Первое обращение — не спам."""
        from src.utils.cache import is_spam

        result = await is_spam("user_1")
        assert result is False

    async def test_is_spam_second_time(self):
        """Повторное обращение в пределах TTL — спам."""
        from src.utils.cache import is_spam

        await is_spam("user_2")
        result = await is_spam("user_2")
        assert result is True

    async def test_is_spam_different_users(self):
        """Разные пользователи не блокируют друг друга."""
        from src.utils.cache import is_spam

        r1 = await is_spam("user_a")
        r2 = await is_spam("user_b")
        assert r1 is False
        assert r2 is False

    async def test_is_spam_expires(self, fake_redis):
        """Spam-ключ истекает после TTL."""
        from src.utils.cache import is_spam

        await is_spam("user_exp")
        # Искусственно удаляем ключ (эмуляция истечения TTL)
        await fake_redis.delete("spam:user_exp")
        result = await is_spam("user_exp")
        assert result is False


class TestSwapCacheKey:
    """Тесты swap_cache_key (Redis GETSET)."""

    async def test_swap_cache_key_first_time(self):
        """swap_cache_key возвращает None при первом сохранении."""
        from src.utils.cache import swap_cache_key

        old = await swap_cache_key("fresh_key", "value")
        assert old is None

    async def test_swap_cache_key_returns_old(self):
        """swap_cache_key возвращает старое значение."""
        from src.utils.cache import swap_cache_key

        await swap_cache_key("k", "old_value")
        old = await swap_cache_key("k", "new_value")
        assert old == "old_value"

    async def test_swap_cache_key_returns_current_same_value(self):
        """swap_cache_key с тем же значением возвращает его же."""
        from src.utils.cache import swap_cache_key

        await swap_cache_key("same", [1, 2, 3])
        old = await swap_cache_key("same", [1, 2, 3])
        assert old == [1, 2, 3]

    async def test_multiple_keys(self):
        """Несколько ключей корректно сохраняются."""
        from src.utils.cache import swap_cache_key

        await swap_cache_key("a", 1)
        await swap_cache_key("b", 2)
        await swap_cache_key("c", 3)

        old_a = await swap_cache_key("a", 1)
        old_b = await swap_cache_key("b", 2)
        old_c = await swap_cache_key("c", 3)
        assert old_a == 1
        assert old_b == 2
        assert old_c == 3

    async def test_store_list_value(self):
        """Кэш корректно хранит списки (сериализация JSON)."""
        from src.utils.cache import swap_cache_key

        slots = ["2026-05-10 в 10:00", "2026-05-10 в 11:00"]
        old = await swap_cache_key("slots", slots)
        assert old is None

        old2 = await swap_cache_key("slots", slots)
        assert old2 == slots
        assert isinstance(old2, list)

    async def test_store_none_value(self):
        """Кэш корректно хранит None (JSON null)."""
        from src.utils.cache import swap_cache_key

        old = await swap_cache_key("none_key", None)
        assert old is None

        old2 = await swap_cache_key("none_key", None)
        assert old2 is None

    async def test_store_dict_value(self):
        """Кэш корректно хранит словари."""
        from src.utils.cache import swap_cache_key

        data = {"name": "test", "count": 42}
        old = await swap_cache_key("dict_key", data)
        assert old is None

        old2 = await swap_cache_key("dict_key", data)
        assert old2 == data


class TestDeleteCacheKeysByPrefix:
    """Тесты delete_cache_keys_by_prefix (Redis SCAN + DEL)."""

    async def test_delete_by_prefix(self):
        """Удаляет ключи по префиксу."""
        from src.utils.cache import delete_cache_keys_by_prefix, swap_cache_key

        await swap_cache_key("a_1", "x")
        await swap_cache_key("a_2", "y")
        await swap_cache_key("b_1", "z")

        deleted = await delete_cache_keys_by_prefix("a_")
        assert deleted == 2

    async def test_delete_by_prefix_empty(self):
        """Не падает при отсутствии ключей."""
        from src.utils.cache import delete_cache_keys_by_prefix

        deleted = await delete_cache_keys_by_prefix("nonexistent_")
        assert deleted == 0

    async def test_delete_by_prefix_partial(self):
        """Удаляет только ключи с точным совпадением префикса."""
        from src.utils.cache import delete_cache_keys_by_prefix, swap_cache_key

        await swap_cache_key("ab_1", "x")
        await swap_cache_key("abc_1", "y")
        await swap_cache_key("ab_2", "z")

        deleted = await delete_cache_keys_by_prefix("ab_")
        # ab_1 и ab_2 должны удалиться, abc_1 — нет (префикс ab_, а ключ abc_1)
        assert deleted == 2

    async def test_delete_by_prefix_verification(self, fake_redis):
        """После удаления ключи действительно отсутствуют."""
        from src.utils.cache import delete_cache_keys_by_prefix, swap_cache_key

        await swap_cache_key("del_a", "x")
        await swap_cache_key("del_b", "y")

        await delete_cache_keys_by_prefix("del_")

        exists_a = await fake_redis.exists("mon:del_a")
        exists_b = await fake_redis.exists("mon:del_b")
        assert exists_a == 0
        assert exists_b == 0
