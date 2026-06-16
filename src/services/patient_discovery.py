"""
Унифицированный поиск пациента по всем доступным клиникам.

Используется как в FSM-регистрации бота, так и в REST-роутере Mini App.
Формат даты на входе — ISO-строка ``YYYY-MM-DD``.
"""

from datetime import date as date_cls

from loguru import logger

from src.config import settings


async def find_patient_across_clinics(
    fio: str,
    date_str: str,
    api,
    db,
) -> tuple[str, str | None]:
    """Поиск пациента по ФИО и дате рождения во всех доступных клиниках.

    Последовательно перебирает:
    1. Клинику по умолчанию (``DEFAULT_CLINIC_ID``).
    2. Глобальный поиск (пустой ``clinic_id``).
    3. Все активные ``clinic_id`` из БД.

    Args:
        fio: ФИО пациента (три слова через пробел).
        date_str: Дата рождения в формате ISO ``YYYY-MM-DD``.
        api: Клиент API zdrav.lenreg.ru (:class:`ZdravClient`).
        db: Менеджер базы данных (:class:`DatabaseManager`).

    Returns:
        Кортеж ``(status, detail)``:
        - ``("found", p_id)`` — пациент найден, ``detail`` = ``patient_id``.
        - ``("not_found", message)`` — пациент не найден.
        - ``("error", message)`` — ошибка (неверная дата, сбой API).
    """
    # Валидация и парсинг ISO-даты
    try:
        bday_date = date_cls.fromisoformat(date_str)
    except (ValueError, TypeError):
        return ("error", f"Неверный формат даты: '{date_str}'. Ожидается YYYY-MM-DD.")

    # Формируем список clinic_id для последовательного перебора
    clinic_ids_to_try: list[str] = []

    # Этап 1: клиника по умолчанию
    clinic_ids_to_try.append(settings.DEFAULT_CLINIC_ID)

    # Этап 2: глобальный поиск (пустая строка)
    clinic_ids_to_try.append("")

    # Этап 3: все активные clinic_id из БД
    try:
        active_ids = await db._db.get_active_clinic_ids()
        for cid in active_ids:
            if cid not in clinic_ids_to_try:
                clinic_ids_to_try.append(cid)
    except Exception:
        logger.warning("Не удалось получить список активных clinic_id из БД")

    last_err: str | None = None

    for idx, clinic_id in enumerate(clinic_ids_to_try, start=1):
        try:
            p_id, err = await api.fetch_patient_id(fio, bday_date, clinic_id)
        except Exception:
            logger.exception(
                "Неожиданная ошибка при поиске пациента '%s' в clinic_id=%s",
                fio,
                clinic_id,
            )
            last_err = "api-timeout"
            continue

        if p_id is not None:
            logger.info(
                "Пациент '{}' найден: p_id={}, clinic_id={} (попытка {}/{})",
                fio,
                p_id,
                clinic_id,
                idx,
                len(clinic_ids_to_try),
            )
            return ("found", p_id)

        last_err = err

    return ("not_found", last_err or "Пациент не найден ни в одной клинике.")
