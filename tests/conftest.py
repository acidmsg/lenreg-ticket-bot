"""
Фикстуры и моки для тестирования (SQLite + fakeredis версия).
"""

import asyncio
import fnmatch
import gc
import os
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from aiogram.types import CallbackQuery, Chat, Message, User
from src.database.database import Database
from src.database.manager import DatabaseManager
from src.i18n import setup_i18n

# ── Вспомогательные пути ──────────────────────────────────────────────
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
TEST_DATA_DIR = os.path.join(TEST_DIR, "test_data")


# ── Инициализация i18n для тестов ────────────────────────────────────
@pytest.fixture(autouse=True)
def _init_i18n():
    """Инициализирует русский язык для gettext в тестах."""
    setup_i18n("ru")


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
                    os.remove(full)
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


# ── Фикстуры для Redis (fakeredis или in-memory mock) ─────────────────

try:
    import fakeredis.aioredis

    _FAKEREDIS_AVAILABLE = True
except ImportError:
    _FAKEREDIS_AVAILABLE = False


class SimpleInMemoryRedis:
    """
    Простой in-memory mock Redis на основе dict (без внешних зависимостей).

    Используется когда пакет fakeredis недоступен в глобальном Python.
    Поддерживает все операции, необходимые для тестов cache и monitor.
    """

    def __init__(self):
        self._data: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        """Возвращает значение по ключу или None."""
        return self._data.get(key)

    async def set(
        self, key: str, value: str, ex: int | None = None, nx: bool = False
    ) -> bool | None:
        """
        Устанавливает значение. При nx=True возвращает True если ключ создан,
        None если ключ уже существовал (аналог Redis SET NX).
        """
        if nx and key in self._data:
            return None
        self._data[key] = value
        return True

    async def getset(self, key: str, value: str) -> str | None:
        """Атомарно возвращает старое значение и устанавливает новое."""
        old = self._data.get(key)
        self._data[key] = value
        return old

    async def expire(self, key: str, ttl: int) -> int:
        """Возвращает 1 если ключ существует, 0 если нет."""
        return 1 if key in self._data else 0

    async def scan(
        self, cursor: int = 0, match: str | None = None, count: int | None = None
    ) -> tuple[int, list[str]]:
        """
        Эмулирует SCAN: возвращает все подходящие ключи за один проход.
        """
        if match is None:
            keys = list(self._data.keys())
        else:
            keys = [k for k in self._data if fnmatch.fnmatch(k, match)]
        return (0, keys)

    async def delete(self, *keys: str) -> int:
        """Удаляет ключи, возвращает количество удалённых."""
        deleted = 0
        for k in keys:
            if k in self._data:
                del self._data[k]
                deleted += 1
        return deleted

    async def exists(self, *keys: str) -> int:
        """Возвращает количество существующих ключей."""
        return sum(1 for k in keys if k in self._data)

    async def keys(self, pattern: str = "*") -> list[str]:
        """Возвращает ключи по glob-паттерну."""
        if pattern == "*":
            return list(self._data.keys())
        return [k for k in self._data if fnmatch.fnmatch(k, pattern)]

    def pipeline(self):
        """Возвращает pipeline-объект (упрощённый)."""
        return SimplePipeline(self)

    async def flushall(self) -> None:
        """Очищает все данные."""
        self._data.clear()

    async def aclose(self) -> None:
        """No-op для совместимости с fakeredis."""
        pass


class SimplePipeline:
    """Упрощённый pipeline: выполняет команды сразу, execute() возвращает результаты."""

    def __init__(self, redis_instance: SimpleInMemoryRedis):
        self._redis = redis_instance
        self._results: list = []

    async def execute(self) -> list:
        return self._results

    def __getattr__(self, name: str):
        """Пробрасывает вызовы на redis, собирая результаты."""

        async def wrapper(*args, **kwargs):
            method = getattr(self._redis, name, None)
            if method:
                result = await method(*args, **kwargs)
                self._results.append(result)
                return result
            raise AttributeError(
                f"'{type(self).__name__}' object has no attribute '{name}'"
            )

        return wrapper


@pytest_asyncio.fixture(autouse=True)
async def fake_redis(monkeypatch):
    """
    Подменяет RedisClient на fakeredis (или in-memory mock) для всех тестов.

    Использует fakeredis.aioredis.FakeRedis если пакет доступен,
    иначе — SimpleInMemoryRedis (dict-based) без внешних зависимостей.
    Патчит get_redis и get_instance всегда, независимо от бэкенда.
    """
    redis_instance: Any
    if _FAKEREDIS_AVAILABLE:
        redis_instance = fakeredis.aioredis.FakeRedis(decode_responses=True)
    else:
        redis_instance = SimpleInMemoryRedis()

    # Подменяем get_redis на возврат мок-объекта
    class FakeRedisClient:
        def __init__(self):
            self.client = redis_instance
            self.is_available = True

        async def get(self, key):
            return await self.client.get(key)

        async def set(self, key, value, ex=None, nx=False):
            return await self.client.set(key, value, ex=ex, nx=nx)

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

    # Очищаем хранилище перед каждым тестом
    await redis_instance.flushall()
    yield redis_instance
    await redis_instance.flushall()
    await redis_instance.aclose()


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


# ── Подавление логов loguru в тестах ──────────────────────────────────


@pytest.fixture(autouse=True)
def _silence_loguru() -> None:
    """Отключает вывод loguru в тестах, оставляя только ERROR."""
    from loguru import logger

    logger.remove()
    logger.add(lambda _: None, level="ERROR")


# ── Общие константы и фабрики для тестов обработчиков ─────────────────


TEST_USER_ID = 123456789


def _make_user(user_id: int = TEST_USER_ID) -> User:
    """Создаёт объект User для тестов."""
    return User(id=user_id, is_bot=False, first_name="Test")


def make_message(text: str | None, user_id: int = TEST_USER_ID) -> Message:
    """
    Создаёт объект Message с замоканными answer/edit_text.

    Модели aiogram — frozen (pydantic), поэтому методы присоединяются
    через object.__setattr__, обходящий валидацию pydantic.
    """
    msg = Message(
        message_id=1,
        date=datetime.now(),
        chat=Chat(id=user_id, type="private"),
        from_user=_make_user(user_id),
        text=text,
    )
    object.__setattr__(msg, "answer", AsyncMock())
    object.__setattr__(msg, "edit_text", AsyncMock())
    return msg


def make_callback(
    data: str,
    user_id: int = TEST_USER_ID,
    message: Message | None = None,
) -> CallbackQuery:
    """
    Создаёт CallbackQuery с замоканными answer и message.answer/edit_text.

    Модель frozen — используем object.__setattr__ для мок-методов.
    Если message не передан, создаётся тестовый Message.
    """
    if message is None:
        message = make_message("dummy", user_id)

    call = CallbackQuery(
        id="cb_test_001",
        from_user=_make_user(user_id),
        message=message,
        data=data,
        chat_instance="test",
    )
    object.__setattr__(call, "answer", AsyncMock())
    return call


def make_mock_api() -> AsyncMock:
    """Создаёт AsyncMock для ZdravClient с замоканным fetch_patient_id."""
    api = AsyncMock()
    api.fetch_patient_id = AsyncMock()
    return api


def make_mock_bot() -> AsyncMock:
    """Создаёт AsyncMock для Bot aiogram."""
    bot = AsyncMock()
    bot.send_message = AsyncMock()
    # send_photo возвращает объект с int message_id, иначе SQLite падает
    bot.send_photo = AsyncMock(return_value=AsyncMock(message_id=12345))
    bot.edit_message_text = AsyncMock()
    bot.delete_message = AsyncMock()
    return bot


async def seed_clinic(db_manager, clinic_id: str, name: str) -> None:
    """Сидирует одну активную клинику в тестовой БД."""
    await db_manager._db.upsert_clinic(clinic_id, name)


async def seed_doctors(db_manager, clinic_id: str, doctors: list[dict]) -> None:
    """Сидирует список врачей для клиники в тестовой БД."""
    for doc in doctors:
        await db_manager._db.upsert_doctor(
            clinic_id=clinic_id,
            doctor_id=doc["id"],
            name=doc["name"],
            specialty=doc.get("specialty", ""),
        )
