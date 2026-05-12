"""
Фикстуры и моки для тестирования (SQLite версия).
"""

import asyncio
import gc
import os

import pytest
import pytest_asyncio
from src.database.database import Database
from src.database.doctor_manager import DoctorManager
from src.database.manager import DatabaseManager
from src.utils.cache import spam_cache

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


@pytest_asyncio.fixture
async def temp_cache_path(monkeypatch):
    """Временный путь для кэша мониторинга + подмена settings.CACHE_PATH."""
    os.makedirs(TEST_DATA_DIR, exist_ok=True)
    path = os.path.join(TEST_DATA_DIR, "test_monitoring_cache.json")
    monkeypatch.setattr("src.utils.cache.settings.CACHE_PATH", path)
    yield path
    if os.path.exists(path):  # noqa: ASYNC240
        os.remove(path)  # noqa: ASYNC240


# ── Фикстура для очистки spam_cache ───────────────────────────────────


@pytest.fixture(autouse=True)
def clear_spam_cache():
    """Очищает spam_cache перед каждым тестом."""
    spam_cache.clear()
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
