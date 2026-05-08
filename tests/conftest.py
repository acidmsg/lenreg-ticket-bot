"""
Фикстуры и моки для тестирования (SQLite версия).
"""

import os

import pytest
import pytest_asyncio

from database.database import Database
from database.doctor_manager import DoctorManager
from database.manager import DatabaseManager
from utils.cache import spam_cache

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
    # Закрываем все соединения перед удалением
    import gc

    gc.collect()
    for ext in ("", "-wal", "-shm"):
        full = path + ext
        for _ in range(3):
            try:
                if os.path.exists(full):
                    os.remove(full)
                break
            except PermissionError:
                import time

                time.sleep(0.1)


@pytest_asyncio.fixture
async def database(temp_db_path):
    """Database с временным SQLite-файлом."""
    db = Database(temp_db_path)
    await db.connect()
    yield db
    await db.close()


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
    monkeypatch.setattr("utils.cache.settings.CACHE_PATH", path)
    yield path
    if os.path.exists(path):
        os.remove(path)


# ── Фикстура для очистки spam_cache ───────────────────────────────────


@pytest.fixture(autouse=True)
def clear_spam_cache():
    """Очищает spam_cache перед каждым тестом."""
    spam_cache.clear()
    yield


# ── Очистка тестовых данных после сессии ──────────────────────────────


def pytest_sessionfinish(session, exitstatus):
    """Удаляет тестовые данные после завершения сессии."""
    if os.path.exists(TEST_DATA_DIR):
        import shutil

        shutil.rmtree(TEST_DATA_DIR, ignore_errors=True)
