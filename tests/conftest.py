"""
Фикстуры и моки для тестирования (SQLite + fakeredis версия).
"""

import asyncio
import gc
import os

import pytest
import pytest_asyncio
from src.database.database import Database
from src.database.doctor_manager import DoctorManager
from src.database.manager import DatabaseManager

# ── Вспомогательные пути ──────────────────────────────────────────────
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
TEST_DATA_DIR = os.path.join(TEST_DIR, "test_data")


# ── Фикстуры для базы данных ──────────────────────────────────────────


@pytest_asyncio.fixture
async def temp_db_path(request):
    """Временный путь для SQLite-файла БД."""
    os.makedirs(TEST_DATA_DIR, exist_ok=True)
    path = os.path.join(TEST_DATA_DIR, f"test_bot_{request.node.name}.db")
    yield path
    # Принудительная сборка мусора + WAL уже очищен в Database.close()
    gc.collect()
    for ext in ("", "-wal", "-shm"):
        full = path + ext
        for _ in range(5):  # увеличено до 5 попыток
            try:
                if os.path.exists(full):  # noqa: ASYNC240
                    os.remove(full)  # noqa: ASYNC240
                break
            except PermissionError:
                await asyncio.sleep(0.2)  # увеличена задержка


@pytest_asyncio.fixture
async def database(temp_db_path):
    """Database с временным SQLite-файлом."""
    db = Database(temp_db_path)
    await db.connect()
    yield db
    await db.close()
    gc.collect()


@pytest_asyncio.fixture
async def db_manager(database):
    """DatabaseManager с временным SQLite."""
    mgr = DatabaseManager(database)
    await mgr.load()
    return mgr


@pytest_asyncio.fixture
async def doctor_manager(database):
    """DoctorManager с временным SQLite."""
    mgr = DoctorManager(database)
    await mgr.load()
    return mgr


# ── Фикстуры для Redis (fakeredis) ────────────────────────────────────


@pytest_asyncio.fixture(autouse=True)
async def fake_redis(monkeypatch):
    """
    Подменяет RedisClient на fakeredis для всех тестов.

    Использует fakeredis.aioredis.FakeRedis для полной эмуляции
    Redis без необходимости запуска реального сервера.
    """
    import fakeredis.aioredis

    fake_redis_instance = fakeredis.aioredis.FakeRedis(decode_responses=True)

    # Подменяем get_redis на возврат мок-объекта
    class FakeRedisClient:
        def __init__(self):
            self.client = fake_redis_instance

        async def get(self, key):
            return await self.client.get(key)

        async def set(self, key, value, ex=None):
            return await self.client.set(key, value, ex=ex)

        async def delete(self, *keys):
            return await self.client.delete(*keys)

        async def exists(self, *keys):
            return await self.client.exists(*keys)

        async def keys(self, pattern):
            return await self.client.keys(pattern)

        async def pipeline(self):
            return self.client.pipeline()

        async def health_check(self):
            return True

        async def close(self):
            await self.client.aclose()

    async def mock_get_redis():
        return FakeRedisClient()

    async def mock_get_instance():
        return FakeRedisClient()

    monkeypatch.setattr("src.utils.cache.get_redis", mock_get_redis)
    monkeypatch.setattr("src.utils.redis.get_redis", mock_get_redis)
    monkeypatch.setattr("src.utils.redis.RedisClient.get_instance", mock_get_instance)

    # Очищаем fakeredis перед каждым тестом
    await fake_redis_instance.flushall()
    yield fake_redis_instance
    await fake_redis_instance.flushall()
    await fake_redis_instance.aclose()


# ── Фикстура для очистки spam_cache (устарела, оставлена для совместимости) ──


@pytest.fixture(autouse=True)
def clear_spam_cache():
    """Spam-защита теперь на Redis, очищается через fake_redis фикстуру (autouse)."""
    yield


# ── tracemalloc: диагностика утечек памяти ──────────────────────────────

_MEMORY_PROFILE_ENABLED = os.environ.get("PYTEST_MEMORY_PROFILE", "0") == "1"

if _MEMORY_PROFILE_ENABLED:
    import tracemalloc

    tracemalloc.start()

    @pytest.hookimpl(tryfirst=True)
    def pytest_runtest_setup(item):
        item._mem_snapshot = tracemalloc.take_snapshot()

    @pytest.hookimpl(trylast=True)
    def pytest_runtest_teardown(item):
        snapshot_before = getattr(item, "_mem_snapshot", None)
        if snapshot_before is None:
            return
        snapshot_after = tracemalloc.take_snapshot()
        top_stats = snapshot_after.compare_to(snapshot_before, "lineno")
        # Показываем только аллокации > 100 KB на тест
        significant = [s for s in top_stats if s.size_diff > 102400]
        if significant:
            print(f"\n[MEM] {item.nodeid}:")
            for stat in significant[:5]:
                print(f"  +{stat.size_diff / 1024:.0f} KB: {stat}")


# ── Очистка тестовых данных после сессии ──────────────────────────────


def pytest_sessionfinish(session, exitstatus):
    """Удаляет тестовые данные после завершения сессии."""
    if os.path.exists(TEST_DATA_DIR):
        import shutil

        shutil.rmtree(TEST_DATA_DIR, ignore_errors=True)
