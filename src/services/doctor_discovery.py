import asyncio
import random
import time
import weakref
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from aiolimiter import AsyncLimiter
from loguru import logger

from src.api.models import CheckSlotsResult, DateInfo, SpecialityItem
from src.api.zdrav_client import ZdravClient
from src.config import settings
from src.database.database import Database
from src.services.metrics import prometheus_metrics
from src.utils.helpers import format_slot_date

# ── Управление плановым сканированием ─────────────────────────────────

_force_scan_events: weakref.WeakKeyDictionary[
    asyncio.AbstractEventLoop, asyncio.Event
] = weakref.WeakKeyDictionary()
"""Per-loop реестр событий принудительного сканирования.

Примитив не создаётся на уровне модуля (правило 2
[`event-loop-ownership.md`](../../specs/design/event-loop-ownership.md:530)):
``asyncio.Event`` появляется лениво в ``_force_scan_event_for()`` — образец
``RedisClient._instances`` ([`redis.py:45`](../../src/utils/redis.py:45)). Ключ —
сам loop, а не ``id(loop)``: идентификаторы переиспользуются после сборки мусора
и вернули бы событие уже закрытого loop'а. Реестр — ``WeakKeyDictionary``: обычный
``dict`` удерживал бы сильную ссылку на loop и не давал ему собраться.
"""

_force_scan_loop: asyncio.AbstractEventLoop | None = None
"""Event loop, в котором работает цикл discovery — владелец события force-скана."""


def _force_scan_event_for(loop: asyncio.AbstractEventLoop) -> asyncio.Event:
    """Возвращает ``asyncio.Event`` указанного loop'а.

    Событие создаётся при первом обращении. Running loop не требуется: событие
    запрашивается и для владельца из ``trigger_force_scan()``, вызванного из
    потока веб-роутера.
    """
    event = _force_scan_events.get(loop)
    if event is None:
        event = asyncio.Event()
        _force_scan_events[loop] = event
    return event


def _get_force_scan_event() -> asyncio.Event:
    """``asyncio.Event`` текущего running loop'а — рабочее событие цикла discovery."""
    return _force_scan_event_for(asyncio.get_running_loop())


def _bind_force_scan_loop() -> None:
    """Запоминает текущий event loop как владельца события force-скана.

    Вызывается при старте цикла discovery, чтобы ``trigger_force_scan()`` из
    другого потока (веб-роутер uvicorn) знал, в какой loop планировать ``set()``
    и какое событие этому loop'у принадлежит.
    """
    global _force_scan_loop
    loop = asyncio.get_running_loop()
    # Событие создаётся до публикации loop'а: иначе ``trigger_force_scan()`` из
    # другого потока успел бы создать второе событие тому же loop'у, и сигнал
    # force-скана потерялся бы.
    _force_scan_event_for(loop)
    _force_scan_loop = loop


def trigger_force_scan() -> bool:
    """Потокобезопасно устанавливает флаг принудительного сканирования врачей.

    Вызывается из веб-роутера, то есть из потока uvicorn, поэтому прямой
    ``Event.set()`` недопустим: событие принадлежит loop'у фоновой задачи
    discovery, а ``set()`` из чужого потока завершает Future чужого loop'а
    (``RuntimeError: Non-thread-safe operation invoked ...``). Если владелец
    известен и работает — установка планируется через
    ``AbstractEventLoop.call_soon_threadsafe()``; при вызове из того же loop'а
    (в том числе после перехода на единый loop) — выполняется напрямую.

    Returns:
        True если флаг установлен; False если цикл discovery ещё не запущен
        (запрос кнопки до старта задачи игнорируется без исключения).
    """
    loop = _force_scan_loop
    if loop is None or not loop.is_running():
        logger.warning(
            "Принудительное сканирование врачей запрошено до запуска цикла discovery"
        )
        return False

    event = _force_scan_event_for(loop)

    try:
        current_loop: asyncio.AbstractEventLoop | None = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if current_loop is loop:
        event.set()
    else:
        loop.call_soon_threadsafe(event.set)

    logger.info("Принудительное сканирование врачей запрошено через API")
    return True


# ── Управление точечным обновлением реестра по требованию ────────────

CLINIC_REFRESH_INTERVAL_SECONDS = 15.0
"""Период опроса очереди точечных обновлений реестра (T2), в секундах.

Задача ``_clinic_refresh_iteration`` просыпается раз в этот интервал и
разбирает накопившиеся запросы ``trigger_clinic_scan()``. Итерации без
запросов — дешёвая проверка пустой очереди.
"""


@dataclass
class ClinicSyncStats:
    """Накопитель статистики обхода клиник за цикл discovery.

    ``sync_clinic_registry()`` возвращает только признак успеха, поэтому
    счётчики новых и обработанных врачей вызывающий получает через этот
    объект (метрики T7).
    """

    new_doctors: int = 0
    total_doctors: int = 0


class _ClinicScanState:
    """Очередь точечных обновлений реестра для одного event loop'а.

    ``pending`` — клиники, ожидающие обхода; ``in_progress`` — клиники,
    обход которых уже идёт. Повторный ``trigger_clinic_scan()`` по клинике
    из ``in_progress`` не создаёт второй параллельный проход.
    """

    __slots__ = ("in_progress", "pending")

    def __init__(self) -> None:
        self.pending: set[str] = set()
        self.in_progress: set[str] = set()


_clinic_scan_states: weakref.WeakKeyDictionary[
    asyncio.AbstractEventLoop, _ClinicScanState
] = weakref.WeakKeyDictionary()
"""Per-loop реестр очередей точечного обновления.

Образец — ``_force_scan_events``: состояние не создаётся на уровне модуля
(правило 2 [`event-loop-ownership.md`](../../specs/design/event-loop-ownership.md:530)),
а появляется лениво; ключ — сам loop, а не ``id(loop)``; ``WeakKeyDictionary``
не удерживает loop сильной ссылкой.
"""

_clinic_scan_loop: asyncio.AbstractEventLoop | None = None
"""Event loop фоновой задачи обновления реестра — владелец очереди."""


def _queue_state_for(
    registry: weakref.WeakKeyDictionary, loop: asyncio.AbstractEventLoop
) -> _ClinicScanState:
    """Возвращает очередь указанного loop'а из реестра, создавая её лениво."""
    state = registry.get(loop)
    if state is None:
        state = _ClinicScanState()
        registry[loop] = state
    return state


def _clinic_scan_state_for(loop: asyncio.AbstractEventLoop) -> _ClinicScanState:
    """Возвращает очередь реестра указанного loop'а, создавая её при обращении."""
    return _queue_state_for(_clinic_scan_states, loop)


def _enqueue_queue_item(state: _ClinicScanState, item: str, label: str) -> None:
    """Ставит элемент в очередь (выполняется в loop'е-владельце).

    Элемент, обход которого уже идёт, повторно не ставится — это защита от
    параллельных проходов по одному элементу. Общий код очередей реестра (T2)
    и талонов (T3).
    """
    if item in state.in_progress:
        logger.debug("{} {} уже обходится — повторный запрос пропущен", label, item)
        return
    state.pending.add(item)


def _enqueue_clinic_scan(state: _ClinicScanState, clinic_id: str) -> None:
    """Ставит клинику в очередь реестра (выполняется в loop'е-владельце)."""
    _enqueue_queue_item(state, clinic_id, "Клиника")


def _enqueue_in_owner_loop(
    registry: weakref.WeakKeyDictionary,
    owner_loop: asyncio.AbstractEventLoop,
    item: str,
    label: str,
) -> None:
    """Потокобезопасно ставит элемент в очередь, привязанную к ``owner_loop``.

    Общий механизм точечных обновлений T2 (реестр) и T3 (талоны). Прямая
    мутация set из чужого потока не потокобезопасна, поэтому пополнение из
    другого потока планируется через ``call_soon_threadsafe()``; вызов из
    loop'а-владельца выполняется напрямую.
    """
    state = _queue_state_for(registry, owner_loop)

    try:
        current_loop: asyncio.AbstractEventLoop | None = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if current_loop is owner_loop:
        _enqueue_queue_item(state, item, label)
    else:
        owner_loop.call_soon_threadsafe(_enqueue_queue_item, state, item, label)


def _bind_clinic_scan_loop() -> None:
    """Запоминает running loop как владельца очереди точечных обновлений."""
    global _clinic_scan_loop
    loop = asyncio.get_running_loop()
    # Очередь создаётся до публикации loop'а: иначе ``trigger_clinic_scan()``
    # из другого потока успел бы создать второй state тому же loop'у.
    _clinic_scan_state_for(loop)
    _clinic_scan_loop = loop


def trigger_clinic_scan(clinic_id: str) -> bool:
    """Потокобезопасно ставит клинику в очередь точечного обновления реестра.

    Вызывается из веб-роутера (поток uvicorn), когда пользователь заходит в
    клинику с просроченным реестром. Портальные запросы здесь не выполняются:
    сигнал только ставит клинику в очередь, а обход делает фоновая задача
    ``_clinic_refresh_iteration`` (тем же кодом, что плановый цикл).

    Пополнение очереди планируется через
    ``AbstractEventLoop.call_soon_threadsafe()``: прямая мутация set из чужого
    потока не потокобезопасна. Вызов из loop'а-владельца выполняется напрямую.

    Returns:
        True если запрос поставлен в очередь; False если фоновая задача ещё
        не запущена (запрос до старта игнорируется без исключения).
    """
    loop = _clinic_scan_loop
    if loop is None or not loop.is_running():
        logger.warning(
            "Обновление реестра клиники {} запрошено до запуска фонового цикла",
            clinic_id,
        )
        return False

    cid = str(clinic_id)
    _enqueue_in_owner_loop(_clinic_scan_states, loop, cid, "Клиника")

    logger.info("Запрошено точечное обновление реестра клиники {} по требованию", cid)
    return True


# ── Кэш талонов: точечное обновление по требованию (T3–T4) ─────────────

CLINIC_SLOTS_REFRESH_INTERVAL_SECONDS = 15.0
"""Период опроса очереди обновления талонов (T3), в секундах.

Задача ``_clinic_slots_refresh_iteration`` просыпается раз в этот интервал и
разбирает накопленные запросы ``trigger_clinic_slots_scan()``. Итерации без
запросов — дешёвая проверка пустой очереди.
"""


class _ClinicSlotsState:
    """Очередь обновления талонов для одного event loop'а (T3–T4).

    ``pending`` — клиники и запрошенные для них ``doctor_id``; ``bootstrap`` —
    клиники, которым нужен полный batch-обход (конкретные врачи не заданы);
    ``in_progress`` — клиники с идущим обходом. Требования T4: сигнал несёт
    конкретных врачей, а сигналы по одной клинике сливаются в объединение, не
    теряя ни одного ``doctor_id`` и не плодя дубли.
    """

    __slots__ = ("bootstrap", "in_progress", "pending")

    def __init__(self) -> None:
        self.pending: dict[str, set[str]] = {}
        self.bootstrap: set[str] = set()
        self.in_progress: set[str] = set()


_slots_scan_states: weakref.WeakKeyDictionary[
    asyncio.AbstractEventLoop, _ClinicSlotsState
] = weakref.WeakKeyDictionary()
"""Per-loop реестр очередей обновления талонов (T3–T4).

Образец — ``_clinic_scan_states``: состояние создаётся лениво, ключ — сам
loop, ``WeakKeyDictionary`` не удерживает loop сильной ссылкой.
"""

_slots_scan_loop: asyncio.AbstractEventLoop | None = None
"""Event loop фоновой задачи обновления талонов — владелец очереди."""


def _slots_scan_state_for(loop: asyncio.AbstractEventLoop) -> _ClinicSlotsState:
    """Возвращает очередь талонов указанного loop'а, создавая её при обращении."""
    state = _slots_scan_states.get(loop)
    if state is None:
        state = _ClinicSlotsState()
        _slots_scan_states[loop] = state
    return state


def _enqueue_slots_item(
    state: _ClinicSlotsState, clinic_id: str, doctor_ids: Iterable[str] | None
) -> None:
    """Ставит клинику/врачей в очередь талонов (в loop'е-владельце).

    Сигналы по одной клинике сливаются: точечные списки объединяются без
    дублей, а полный batch (без ``doctor_ids``) поглощает точечные запросы и
    остаётся единственным — он покрывает всех врачей клиники. Клиника с идущим
    обходом повторно не ставится.
    """
    if clinic_id in state.in_progress:
        logger.debug("Клиника {} уже обходится — повторный запрос пропущен", clinic_id)
        return

    ids = {str(d) for d in (doctor_ids or ()) if str(d)}
    if not ids:
        state.bootstrap.add(clinic_id)
        state.pending.pop(clinic_id, None)
        return
    if clinic_id in state.bootstrap:
        # Полный обход уже запрошен — точечный список избыточен.
        return
    state.pending.setdefault(clinic_id, set()).update(ids)


def _enqueue_slots_in_owner_loop(
    owner_loop: asyncio.AbstractEventLoop,
    clinic_id: str,
    doctor_ids: Iterable[str] | None,
) -> None:
    """Потокобезопасно ставит врачей в очередь талонов loop'а-владельца.

    Прямая мутация множеств из чужого потока не потокобезопасна, поэтому
    пополнение из другого потока планируется через ``call_soon_threadsafe()``;
    вызов из loop'а-владельца выполняется напрямую.
    """
    state = _slots_scan_state_for(owner_loop)

    try:
        current_loop: asyncio.AbstractEventLoop | None = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if current_loop is owner_loop:
        _enqueue_slots_item(state, clinic_id, doctor_ids)
    else:
        owner_loop.call_soon_threadsafe(
            _enqueue_slots_item, state, clinic_id, list(doctor_ids or ())
        )


def _bind_slots_scan_loop() -> None:
    """Запоминает running loop как владельца очереди обновления талонов."""
    global _slots_scan_loop
    loop = asyncio.get_running_loop()
    # Очередь создаётся до публикации loop'а: иначе ``trigger_clinic_slots_scan()``
    # из другого потока успел бы создать второй state тому же loop'у.
    _slots_scan_state_for(loop)
    _slots_scan_loop = loop


def trigger_clinic_slots_scan(
    clinic_id: str, doctor_ids: Iterable[str] | None = None
) -> bool:
    """Потокобезопасно ставит талоны в очередь обновления (T3–T4).

    Вызывается из веб-роутера (поток uvicorn), когда пользователь открывает
    экран «Выберите врача» с просроченным или пустым кэшем талонов. Портал
    здесь не опрашивается: сигнал только ставит работу в очередь, а обход
    делает фоновая задача ``_clinic_slots_refresh_iteration``.

    ``doctor_ids`` задаёт точечный список врачей: по каждому будет один вызов
    ``check_slots``. Без ``doctor_ids`` запрашивается полный batch клиники
    (bootstrap). Пустой список равнозначен отсутствию: точечно обновлять
    некого.

    Пополнение очереди планируется через ``AbstractEventLoop.call_soon_threadsafe()``:
    прямая мутация множеств из чужого потока не потокобезопасна. Вызов из
    loop'а-владельца выполняется напрямую. Дедупликация по clinic_id — через
    множество ``in_progress`` (как у обновления реестра).

    Returns:
        True если запрос поставлен в очередь; False если фоновая задача ещё
        не запущена (запрос до старта игнорируется без исключения).
    """
    loop = _slots_scan_loop
    if loop is None or not loop.is_running():
        logger.warning(
            "Обновление талонов клиники {} запрошено до запуска фонового цикла",
            clinic_id,
        )
        return False

    cid = str(clinic_id)
    _enqueue_slots_in_owner_loop(loop, cid, doctor_ids)

    count = len({str(d) for d in (doctor_ids or ()) if str(d)})
    if count:
        logger.info(
            "Запрошено точечное обновление талонов клиники {} по {} врачам",
            cid,
            count,
        )
    else:
        logger.info(
            "Запрошено фоновое обновление талонов клиники {} по требованию", cid
        )
    return True


async def clinic_registry_is_stale(database: Database, clinic_id: str) -> bool:
    """True, если реестр врачей клиники старше эффективного TTL.

    Срок — ``doctor_scan_ttl_hours`` из config плюс джиттер ±10% (единый
    источник — ``_registry_ttl_seconds()``). Бэкофф клиник без врачей (T6)
    здесь намеренно не учитывается: пользователь открыл именно эту клинику,
    и её обход уместен. Клиника без метки синхронизации считается
    просроченной. При ошибке чтения настроек возвращает False — лишний обход
    не запускаем.
    """
    try:
        ttl_hours = int(await database.config.get_config("doctor_scan_ttl_hours", "12"))
        synced_at, _ = await database.get_clinic_sync_state(str(clinic_id))
    except Exception as e:
        logger.opt(exception=True).warning(
            "Не удалось определить свежесть реестра clinic_id={}: {}", clinic_id, e
        )
        return False
    return time.time() - synced_at >= _registry_ttl_seconds(ttl_hours)


async def refresh_clinic_if_stale(database: Database, clinic_id: str) -> bool:
    """Ставит в фон обход клиники, если её реестр просрочен (T2).

    Единая точка «зашёл в клинику» и для Mini App, и для бота: список врачей
    отдаётся из БД сразу, а портальный обход — только сигналом в фоновую задачу.

    Returns:
        True — обход поставлен в очередь; False — реестр свежий или очередь
        недоступна.
    """
    if not await clinic_registry_is_stale(database, clinic_id):
        return False
    return trigger_clinic_scan(clinic_id)


async def clinic_slots_are_stale(
    database: Database, clinic_id: str, doctor_ids: Iterable[str] | None = None
) -> bool:
    """True, если кэш талонов клиники просрочен или пуст (T3–T4).

    Без ``doctor_ids`` свежесть — ``max(updated_at)`` всей клиники. С ними
    свежесть считается по этим врачам: самыйстарый (или отсутствующий) врач
    делает набор просроченным. Так точечное обновление одной специальности
    не «омолаживает» клинику целиком и другая специальность обновится сразу.
    Клиника без записей талонов считается просроченной. При ошибке чтения
    настроек/БД возвращает False — лишний обход не запускаем.
    """
    try:
        ttl_minutes = int(
            await database.config.get_config(
                "slot_cache_ttl_minutes", str(settings.SLOT_CACHE_TTL_MINUTES)
            )
        )
        slots = await database.get_clinic_slots(str(clinic_id))
    except Exception as e:
        logger.opt(exception=True).warning(
            "Не удалось определить свежесть талонов clinic_id={}: {}", clinic_id, e
        )
        return False
    if not slots:
        return True

    now = time.time()
    ttl_seconds = ttl_minutes * 60
    if doctor_ids is not None:
        wanted = {str(doctor_id) for doctor_id in doctor_ids}
        if not wanted:
            return True
        updated_by_doctor = {
            row["doctor_id"]: float(row.get("updated_at") or 0) for row in slots
        }
        # Врач без записи (0.0) делает набор просроченным — его надо добрать.
        oldest = min(updated_by_doctor.get(doctor_id, 0.0) for doctor_id in wanted)
        return now - oldest >= ttl_seconds

    newest = max(float(row.get("updated_at") or 0) for row in slots)
    return now - newest >= ttl_seconds


async def refresh_clinic_slots_if_stale(
    database: Database, clinic_id: str, doctor_ids: Iterable[str] | None = None
) -> bool:
    """Ставит в фон обновление талонов, если кэш просрочен или пуст (T3–T4).

    Единая точка «открыт экран выбора врача»: список врачей и талоны отдаются
    из БД сразу, а портальный обход уходит в фоновую задачу. Цикл
    мониторинга слотов (``src/services/monitor.py``) не затрагивается.

    ``doctor_ids`` — видимые на экране врачи: при непустом кэше обновляются
    точечно только они (K вызовов ``check_slots``). Без списка запрашивается
    полный batch клиники — он же остаётся путём холодного кэша.

    Returns:
        True — обновление поставлено в очередь; False — кэш свежий или
        очередь недоступна.
    """
    if not await clinic_slots_are_stale(database, clinic_id, doctor_ids=doctor_ids):
        return False
    return trigger_clinic_slots_scan(clinic_id, doctor_ids=doctor_ids)


async def fetch_specialties(
    api: ZdravClient,
    patient_id: str,
    clinic_id: str,
    limiter: AsyncLimiter | None = None,
) -> list[SpecialityItem] | None:
    """Получает список специальностей (ID и имя) для данной клиники и пациента.

    Returns:
        Пустой список — портал ответил успешно, но специальностей нет;
        ``None`` — отказ API (таймаут/сеть/ошибочный статус). Отличие важно
        вызывающему: обход клиники с ``None`` не считается успешным.
    """
    try:
        response = await api.fetch_speciality_list(
            patient_id, clinic_id, limiter=limiter
        )
        # None — отказ API (таймаут/сеть/ошибочный статус); это не «пустой список»
        if response is None:
            logger.warning(
                "API недоступен при получении специальностей для clinic_id={}",
                clinic_id,
            )
            return None
        # Конвертируем сырые dict-ы в SpecialityItem для атрибутного доступа
        return [
            SpecialityItem(**item)
            for item in response
            if item.get("IdSpesiality") and item.get("NameSpesiality")
        ]
    except Exception as e:
        logger.opt(exception=True).error(
            f"Ошибка получения специальностей для {clinic_id}: {e}"
        )
        return None


async def _get_clinic_type_from_db(database: "Database", clinic_id: str) -> str:
    """Получает тип клиники из БД. Если не найден — возвращает 'adult'."""
    try:
        clinic_type = await database.get_clinic_type(str(clinic_id))
        if clinic_type:
            return clinic_type
    except Exception:
        logger.debug("Не удалось получить тип клиники clinic_id={} из БД", clinic_id)
    return "adult"


def _registry_ttl_seconds(ttl_hours: int) -> float:
    """Эффективный срок годности реестра врачей: TTL плюс джиттер ±10%.

    Разброс не даёт всем клиникам протухать в один момент — обходы размазаны
    по времени.
    """
    return ttl_hours * 3600 * random.uniform(0.9, 1.1)


def _post_specialty_pause_seconds() -> float:
    """Случайная пауза между вызовами API (0.5–1.0 с).

    TD-SVC-003: вместо фиксированной паузы 0.7 с — разброс, чтобы не бить по
    API ровным ритмом.
    """
    return random.uniform(0.5, 1.0)


async def sync_clinic_registry(
    api: ZdravClient,
    database: Database,
    clinic_id: str,
    *,
    patient_id_adult: str,
    patient_id_child: str,
    limiter: AsyncLimiter | None = None,
    stats: ClinicSyncStats | None = None,
) -> bool:
    """Обходит реестр одной клиники и сохраняет врачей в БД.

    Единый код обхода для планового цикла (``_discovery_iteration``) и
    точечного обновления по требованию (``_clinic_refresh_iteration``):
    получение специальностей → врачи → merge. Метка свежести
    (``mark_clinic_synced``) ставится только после полностью пройденного
    обхода; ``None`` от ``fetch_specialties`` — отказ API, метку не ставим.

    Args:
        api: Клиент портала.
        database: БД (таблицы clinics/doctors).
        clinic_id: ID клиники.
        patient_id_adult: Глобальный discovery-пациент (взрослые).
        patient_id_child: Глобальный discovery-пациент (дети).
        limiter: Ограничитель темпа (обычно ``api.limiter_discovery``);
            ``None`` — лимитер по умолчанию клиента.
        stats: Накопитель новых/обработанных врачей для метрик T7.

    Returns:
        True если обход клиники прошёл полностью; False при отказе API.
    """
    cid = str(clinic_id)
    # Получаем тип клиники (из БД)
    clinic_type = await _get_clinic_type_from_db(database, cid)

    # Сначала проверяем per-клиника discovery пациентов из БД
    (
        clinic_patient_adult,
        clinic_patient_child,
    ) = await database.get_clinic_discovery_patients(cid)

    # Определяем, какие patient_id использовать для данной клиники
    # Приоритет: per-клиника из БД > глобальные из settings
    if clinic_type == "child":
        patient_ids = [clinic_patient_child or patient_id_child]
    elif clinic_type == "all":
        patient_ids = [
            clinic_patient_adult or patient_id_adult,
            clinic_patient_child or patient_id_child,
        ]
    else:
        patient_ids = [clinic_patient_adult or patient_id_adult]

    total_doctors = 0
    for current_patient_id in patient_ids:
        specialties_data = await fetch_specialties(
            api, current_patient_id, cid, limiter=limiter
        )
        if specialties_data is None:
            # Отказ API — обход клиники неполный: метку свежести не ставим,
            # чтобы не выключать клинику из опроса на весь TTL.
            logger.warning(
                "Клиника {}: реестр не синхронизирован (отказ API), "
                "метка свежести не выставлена",
                cid,
            )
            return False

        for specialty_info in specialties_data:
            spec_id = specialty_info.specialty_id
            spec_name = specialty_info.specialty_name

            doctors = await api.fetch_all_doctors(
                specialty_id=spec_id,
                patient_id=current_patient_id,
                clinic_id=cid,
                limiter=limiter,
            )
            if doctors:
                for doc in doctors:
                    doc["SpesialityName"] = spec_name
                # TD-SVC-002: частичное сохранение после каждой спец-ти
                new_count = await database.merge_doctors(cid, doctors)
                total_doctors += len(doctors)
                if stats is not None:
                    stats.new_doctors += new_count
                    stats.total_doctors += len(doctors)
                logger.info(
                    "Обновлены врачи для {} / specialty {} (id={}): {} зап",
                    cid,
                    spec_name,
                    spec_id,
                    len(doctors),
                )
            # TD-SVC-003: разброс паузы вместо фиксированной 0.7 с
            await asyncio.sleep(_post_specialty_pause_seconds())

    # Метка ставится только после успешного обхода клиники
    await database.mark_clinic_synced(cid, total_doctors)
    if total_doctors > 0:
        logger.info(
            "Цикл завершён для {}: обработано {} записей",
            cid,
            total_doctors,
        )
    return True


async def _clinic_refresh_iteration(
    api: ZdravClient,
    database: Database,
    *,
    patient_id_adult: str,
    patient_id_child: str,
) -> None:
    """Одна итерация фонового обновления реестра по требованию (T2).

    Разбирает накопленную ``trigger_clinic_scan()`` очередь клиник и обходит
    их тем же кодом, что плановый цикл (``sync_clinic_registry``), игнорируя
    TTL. Клиника, обход которой уже идёт, повторно не запускается.

    Менеджер владеет sleep, retry и обработкой CancelledError.
    """
    _bind_clinic_scan_loop()
    state = _clinic_scan_state_for(asyncio.get_running_loop())
    if not state.pending:
        return

    pending = list(state.pending)
    state.pending.clear()

    for clinic_id in pending:
        if clinic_id in state.in_progress:
            continue
        state.in_progress.add(clinic_id)
        try:
            await sync_clinic_registry(
                api,
                database,
                clinic_id,
                patient_id_adult=patient_id_adult,
                patient_id_child=patient_id_child,
                limiter=api.limiter_discovery,
            )
        except Exception as e:
            # Сбой одной клиники не должен терять остальные запросы очереди
            logger.opt(exception=True).warning(
                "Не удалось обновить реестр клиники {} по требованию: {}",
                clinic_id,
                e,
            )
        finally:
            state.in_progress.discard(clinic_id)


async def _resolve_discovery_patient(
    database: Database,
    clinic_id: str,
    *,
    patient_id_adult: str,
    patient_id_child: str,
) -> str:
    """Определяет discovery-пациента клиники для обхода талонов.

    Приоритет: per-клиника из БД > глобальные из settings; детская клиника
    берёт child-пациента, остальные — adult. Пустая строка — пациента нет.
    """
    clinic_type = await _get_clinic_type_from_db(database, clinic_id)
    (
        clinic_patient_adult,
        clinic_patient_child,
    ) = await database.get_clinic_discovery_patients(str(clinic_id))

    if clinic_type == "child":
        return clinic_patient_child or patient_id_child
    return clinic_patient_adult or patient_id_adult


def _nearest_date_from_doctor(doc: dict[str, Any]) -> str:
    """Приводит ``NearestDate`` врача портала к формату «ДД.ММ.ГГГГ».

    Портальный список врачей отдаёт ``NearestDate`` объектом с полями
    ``day``/``month``/``year`` (модель ``DateInfo``). Приводим его тем же
    ``format_slot_date``, что и даты слотов, чтобы обе ветки обновления кэша
    писали дату в одном формате. Строка возвращается как есть.
    """
    value = doc.get("NearestDate")
    if not value:
        return ""
    if isinstance(value, dict):
        try:
            return format_slot_date(DateInfo.model_validate(value))
        except Exception:
            logger.debug("Не удалось разобрать NearestDate врача: {!r}", value)
            return ""
    return str(value)


def _slot_date_sort_key(date_start: DateInfo) -> str:
    """Ключ сортировки дат слотов: ISO, иначе собранная «ГГГГ-ММ-ДД»."""
    if date_start.iso:
        return date_start.iso
    return (
        f"{date_start.year.zfill(4)}-"
        f"{date_start.month.zfill(2)}-"
        f"{date_start.day.zfill(2)}"
    )


def _nearest_slot_date(result: CheckSlotsResult) -> str:
    """Возвращает ближайшую дату слотов врача в формате «ДД.ММ.ГГГГ».

    Дата — минимум по ``date_start``; собирается тем же ``format_slot_date``,
    что и даты портального списка врачей.
    """
    starts = [slot.date_start for slot in result.slots if slot.date_start]
    if not starts:
        return ""
    nearest = min(starts, key=_slot_date_sort_key)
    return format_slot_date(nearest)


async def sync_clinic_slots(
    api: ZdravClient,
    database: Database,
    clinic_id: str,
    *,
    patient_id_adult: str,
    patient_id_child: str,
    limiter: AsyncLimiter | None = None,
) -> int:
    """Полный batch-обход талонов одной клиники (bootstrap-путь, T3).

    ОДИН batch-запрос ``fetch_all_doctors_for_clinic`` на клинику. Пациент
    выбирается так же, как для реестра (см. ``_resolve_discovery_patient``).
    Портал отдаёт врачей клиники с CountFreeTicket и NearestDate; они и
    складываются в кэш перезаписью целиком.

    Полный обход вызывается только при холодном кэше клиники (или когда
    сигнал не назвал конкретных врачей): при непустом кэше точечное
    обновление дешевле — см. ``sync_doctor_slots``.

    Пауза отдаётся через переданный лимитер: фоновое обновление талонов идёт
    в общем темпе discovery (PERF-TEMPO, T5), а не в лимите пользовательских
    запросов — портальный вызов один на клинику.

    Пустой ответ (нет врачей либо отказ API) не затирает непустой кэш: экран
    выбора врача продолжит отдавать прежние талоны, а не обнулится на время
    сбоя портала.

    Returns:
        Сколько талонов записано (0 — кэш не тронут).
    """
    cid = str(clinic_id)
    patient_id = await _resolve_discovery_patient(
        database,
        cid,
        patient_id_adult=patient_id_adult,
        patient_id_child=patient_id_child,
    )

    if not patient_id:
        logger.warning(
            "Клиника {}: discovery-пациент не задан — талоны не обновляем", cid
        )
        return 0

    doctors = await api.fetch_all_doctors_for_clinic(
        patient_id=patient_id,
        clinic_id=cid,
        limiter=limiter or api.limiter,
    )

    rows: list[dict[str, Any]] = []
    for doc in doctors:
        doc_id = str(doc.get("IdDoc", "") or "")
        if not doc_id:
            continue
        rows.append(
            {
                "doctor_id": doc_id,
                "free_tickets": int(doc.get("CountFreeTicket", 0) or 0),
                "nearest_date": _nearest_date_from_doctor(doc),
            }
        )

    if not rows:
        logger.warning(
            "Клиника {}: портал не вернул талонов — кэш оставлен без изменений",
            cid,
        )
        return 0

    count = await database.replace_clinic_slots(cid, rows)
    logger.info("Талоны клиники {} обновлены: {} записей", cid, count)
    return count


async def sync_doctor_slots(
    api: ZdravClient,
    database: Database,
    clinic_id: str,
    doctor_ids: Iterable[str],
    patient_id: str,
    limiter: AsyncLimiter | None = None,
) -> int:
    """Точечно обновляет талоны указанных врачей клиники (T4).

    По каждому врачу — ОДИН вызов ``check_slots`` (POST ``/appointment_list/``),
    затем частичный upsert: записи других врачей клиники сохраняются. Так
    обновление экрана «Выберите врача» стоит K вызовов портала (по числу
    видимых врачей), а не обхода специальностей всей клиники.

    Сбой по одному врачу (отказ API, исключение) не срывает остальных: в лог
    пишется предупреждение, запись пропускается, цикл продолжается.

    ``free_tickets`` здесь — число доступных слотов из ответа
    ``/appointment_list/``; полный обход клиники пишет ``CountFreeTicket`` из
    ``/doctor_list/`` (см. docstring ``SlotsRepository`` о допустимом
    расхождении счётчиков).

    Args:
        api: Клиент портала.
        database: БД (таблица ``clinic_slots``).
        clinic_id: ID клиники.
        doctor_ids: Врачи для точечного обновления.
        patient_id: Discovery-пациент клиники.
        limiter: Ограничитель темпа (в фоне — ``api.limiter_discovery``).

    Returns:
        Сколько талонов записано (0 — кэш не тронут).
    """
    cid = str(clinic_id)
    unique_ids = list(dict.fromkeys(str(d) for d in doctor_ids if str(d)))
    if not unique_ids:
        return 0

    rows: list[dict[str, Any]] = []
    for doc_id in unique_ids:
        try:
            result = await api.check_slots(
                doc_id, patient_id, cid, limiter=limiter or api.limiter
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            # Сбой одного врача не должен отменять обновление остальных
            logger.opt(exception=True).warning(
                "Клиника {}: не удалось получить талоны врача {}: {}",
                cid,
                doc_id,
                e,
            )
            continue
        if result is None:
            logger.warning(
                "Клиника {}: портал не вернул талоны врача {} — запись пропущена",
                cid,
                doc_id,
            )
            continue
        rows.append(
            {
                "doctor_id": doc_id,
                # Свободные талоны = слоты бронирования из appointment_list.
                "free_tickets": len(result.slots),
                "nearest_date": _nearest_slot_date(result),
            }
        )

    if not rows:
        logger.warning(
            "Клиника {}: талоны врачей не обновлены — кэш оставлен без изменений",
            cid,
        )
        return 0

    count = await database.upsert_clinic_slots(cid, rows)
    logger.info(
        "Талоны клиники {} обновлены точечно: {} из {} врачей",
        cid,
        count,
        len(unique_ids),
    )
    return count


async def _clinic_slots_refresh_iteration(
    api: ZdravClient,
    database: Database,
    *,
    patient_id_adult: str,
    patient_id_child: str,
) -> None:
    """Одна итерация фонового обновления талонов по требованию (T3–T4).

    Разбирает накопленную ``trigger_clinic_slots_scan()`` очередь. Врачи, чей
    ``doctor_id`` передан сигналом, обновляются точечно (по вызову
    ``check_slots`` на врача). Полный batch ``fetch_all_doctors_for_clinic``
    выполняется как bootstrap: когда сигнал не назвал врачей либо кэш клиники
    пуст. Клиника, обход которой уже идёт, повторно не запускается.

    Менеджер владеет sleep, retry и обработкой CancelledError.
    """
    _bind_slots_scan_loop()
    state = _slots_scan_state_for(asyncio.get_running_loop())
    if not state.pending and not state.bootstrap:
        return

    pending = dict(state.pending)
    bootstrap = set(state.bootstrap)
    state.pending.clear()
    state.bootstrap.clear()

    for clinic_id in bootstrap | set(pending):
        if clinic_id in state.in_progress:
            continue
        state.in_progress.add(clinic_id)
        try:
            cached = await database.get_clinic_slots(clinic_id)
            # Полный batch — только как bootstrap: кэша нет вообще либо
            # сигнал не назвал конкретных врачей. Непустой кэш обновляем
            # точечно — K вызовов вместо обхода всей клиники.
            if clinic_id in bootstrap or not cached:
                await sync_clinic_slots(
                    api,
                    database,
                    clinic_id,
                    patient_id_adult=patient_id_adult,
                    patient_id_child=patient_id_child,
                    limiter=api.limiter_discovery,
                )
                continue
            patient_id = await _resolve_discovery_patient(
                database,
                clinic_id,
                patient_id_adult=patient_id_adult,
                patient_id_child=patient_id_child,
            )
            if not patient_id:
                logger.warning(
                    "Клиника {}: discovery-пациент не задан — талоны не обновляем",
                    clinic_id,
                )
                continue
            await sync_doctor_slots(
                api,
                database,
                clinic_id,
                pending.get(clinic_id, set()),
                patient_id,
                limiter=api.limiter_discovery,
            )
        except Exception as e:
            # Сбой одной клиники не должен терять остальные запросы очереди
            logger.opt(exception=True).warning(
                "Не удалось обновить талоны клиники {} по требованию: {}",
                clinic_id,
                e,
            )
        finally:
            state.in_progress.discard(clinic_id)


async def _discovery_iteration(
    api: ZdravClient,
    database: Database,
    *,
    patient_id_adult: str,
    patient_id_child: str,
) -> None:
    """Одна итерация discovery врачей (для BackgroundTaskManager).

    Выполняет один полный цикл: итерирует все активные clinic_ids из БД,
    получает специальности и врачей для каждой клиники, сохраняет в БД.

    Менеджер владеет ``while True``, sleep, retry и обработкой CancelledError.

    Если плановое сканирование выключено (``doctor_scan_enabled != "1"``)
    и force-скан не запрошен — итерация завершается без действий (no-op).
    """
    _bind_force_scan_loop()
    force_scan_event = _get_force_scan_event()

    # Проверка: включено ли плановое сканирование и/или запрошен force-скан
    scan_enabled = await database.config.get_config("doctor_scan_enabled", "1")
    force_requested = force_scan_event.is_set()

    if scan_enabled != "1" and not force_requested:
        # Плановое сканирование выключено — ничего не делаем в этой итерации
        return

    force_scan_event.clear()

    if force_requested:
        logger.info("Принудительное сканирование врачей запущено")

    clinic_ids = await database.get_active_clinic_ids()
    if not clinic_ids:
        logger.warning("Нет активных клиник для discovery")
        return

    # TTL реестра врачей: клиники, синхронизированные свежее срока, пропускаются.
    # Клиники без врачей (PERF-BACKOFF, T6) обходятся реже — по бэкоффу.
    # Оба срока правятся без релиза через таблицу config.
    ttl_hours = int(await database.config.get_config("doctor_scan_ttl_hours", "12"))
    backoff_hours = int(
        await database.config.get_config(
            "empty_clinic_backoff_hours", str(settings.EMPTY_CLINIC_BACKOFF_HOURS)
        )
    )

    clinic_count = len(clinic_ids)
    started_at = time.perf_counter()

    # Сбрасываем счётчик новых врачей в начале каждого полного цикла
    prometheus_metrics._doctors_discovered.set(0)

    stats = ClinicSyncStats()

    for clinic_id in clinic_ids:
        cid = str(clinic_id)

        # Свежесть реестра: срок у каждой клиники свой из-за джиттера. Клиника,
        # последний обход которой не вернул врачей, обходится по бэкоффу реже —
        # пустые проходы не тратят портальные вызовы впустую. По построению
        # ``doctors_count == 0`` равносильно непустому ``empty_sync_streak``.
        # Force-скан игнорирует и TTL, и бэкофф.
        synced_at, doctors_count = await database.get_clinic_sync_state(cid)
        age_seconds = time.time() - synced_at
        empty_clinic = doctors_count == 0
        ttl_seconds = _registry_ttl_seconds(
            backoff_hours if empty_clinic else ttl_hours
        )
        if not force_requested and age_seconds < ttl_seconds:
            if empty_clinic:
                streak = await database.get_clinic_empty_streak(cid)
                logger.debug(
                    "Клиника {} пропущена: клиника без врачей, бэкофф {} ч "
                    "({} пустых синков, {:.1f}ч < {:.1f}ч)",
                    cid,
                    backoff_hours,
                    streak,
                    age_seconds / 3600,
                    ttl_seconds / 3600,
                )
            else:
                logger.debug(
                    "Клиника {} пропущена: реестр свежее TTL ({:.1f}ч < {:.1f}ч)",
                    cid,
                    age_seconds / 3600,
                    ttl_seconds / 3600,
                )
            continue

        # Обход клиники тем же кодом, что и точечное обновление по требованию
        await sync_clinic_registry(
            api,
            database,
            cid,
            patient_id_adult=patient_id_adult,
            patient_id_child=patient_id_child,
            limiter=api.limiter_discovery,
            stats=stats,
        )

    new_doctors_total = stats.new_doctors

    # Итоги полного цикла: длительность, метрики и лог
    duration = time.perf_counter() - started_at
    prometheus_metrics._doctors_discovered.set(new_doctors_total)
    prometheus_metrics.doctors_last_scan_timestamp.set(int(time.time()))
    logger.info(
        "Цикл discovery завершён: клиник {}, обновлено {}, "
        "новых {}, длительность {:.1f}с",
        clinic_count,
        stats.total_doctors,
        new_doctors_total,
        duration,
    )

    # Динамика справочника: сбой снимка/записи не должен срывать учёт цикла
    try:
        registry_total = await database.get_total_doctor_count()
        prometheus_metrics._doctors_total.set(registry_total)
        await database.record_discovery_stats(
            doctors_total=registry_total,
            doctors_added=new_doctors_total,
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            "Не удалось записать динамику discovery: {}", e
        )


# Счётчик последовательных ошибок для sync_clinic_names
# TD-SVC-004: после 3 сбоев подряд exc_info отключается, чтобы не засорять лог
_sync_consecutive_errors: int = 0


async def sync_clinic_names(api: ZdravClient, database: Database) -> None:
    """Получает список клиник из API и сохраняет названия в БД."""
    global _sync_consecutive_errors
    try:
        clinics_data = await api.fetch_clinic_list()
        if not clinics_data:
            logger.warning("Не удалось получить список клиник из API")
            _sync_consecutive_errors = 0
            return

        updated = 0
        for clinic in clinics_data:
            raw_id = clinic.get("IdLPU")
            if raw_id is None:
                continue
            clinic_id = str(raw_id)
            clinic_name = clinic.get("LpuName") or clinic.get("LPUShortName", "")
            if clinic_id and clinic_name:
                await database.upsert_clinic(clinic_id, clinic_name)
                updated += 1

        logger.info(
            f"Синхронизировано названий клиник: {updated} из {len(clinics_data)}"
        )
        _sync_consecutive_errors = 0
    except Exception as e:
        _sync_consecutive_errors += 1
        use_exc_info = _sync_consecutive_errors <= 3
        logger.opt(exception=use_exc_info).error(
            f"Ошибка синхронизации названий клиник: {e}",
        )
