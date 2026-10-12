"""
Общие хелперы роутера Mini App API (``/api/user``).

Модуль не объявляет эндпоинтов: здесь живут хелперы доступа к контексту
запроса, сериализаторы и построители ответов об ошибках, переиспользуемые
доменными модулями-роутерами ``user_*``.
"""

import datetime
from typing import Any, cast

from fastapi import Request
from fastapi.responses import JSONResponse

from src.database.manager import DatabaseManager
from src.utils.helpers import format_error_message


def _get_telegram_id(request: Request) -> str:
    """Извлекает telegram_id из состояния запроса и приводит к строке."""
    return str(request.state.telegram_id)


def _get_db(request: Request) -> DatabaseManager:
    """Возвращает DatabaseManager из app.state."""
    return cast(DatabaseManager, request.app.state.db)


def _get_api(request: Request):
    """Возвращает ZdravClient из app.state.

    На момент написания ZdravClient ещё не зарегистрирован в app.state —
    будет добавлен на этапе регистрации роутера в ``app.py``.
    """

    api = getattr(request.app.state, "zdrav_client", None)
    if api is None:
        raise RuntimeError(
            "ZdravClient не найден в app.state.zdrav_client. "
            "Добавьте его при регистрации роутера в app.py."
        )
    return api


def _normalize_bday_display(value: Any) -> str:
    """Приводит дату рождения к формату отображения ``ДД.ММ.ГГГГ``.

    В хранилище встречаются обе формы: ``ДД.ММ.ГГГГ`` и ISO ``ГГГГ-ММ-ДД``
    (старые записи и часть путей добавления сохраняли ISO). Мини-апп ждёт
    ``ДД.ММ.ГГГГ`` и валидирует поле, поэтому нормализуем на выдаче.
    Нераспознанное значение возвращается как есть, чтобы не терять данные.
    """
    text = str(value or "").strip()
    if not text:
        return ""
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            parsed = datetime.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
        return parsed.strftime("%d.%m.%Y")
    return text


def _serialize_patients(patients: dict[str, Any]) -> list[dict[str, Any]]:
    """Сериализует словарь пациентов в список словарей для JSON-ответа."""
    result: list[dict[str, Any]] = []
    for p_id, p_info in patients.items():
        entry: dict[str, Any] = {
            "patient_id": p_id,
            "fio": p_info.get("fio", ""),
            "bday": _normalize_bday_display(p_info.get("bday", "")),
        }
        if "alias" in p_info:
            entry["alias"] = p_info["alias"]
        if "confirmed_clinics" in p_info:
            entry["confirmed_clinics"] = p_info["confirmed_clinics"]
        result.append(entry)
    return result


def _monitoring_id_to_parts(monitoring_id: str) -> tuple[str, str]:
    """Разбирает monitoring_id вида '{p_id}_{d_id}' на компоненты."""
    parts = monitoring_id.split("_", 1)
    if len(parts) != 2:
        raise ValueError(
            f"Неверный формат monitoring_id: {monitoring_id}. "
            "Ожидается формат '{patient_id}_{doctor_id}'."
        )
    return parts[0], parts[1]


def _build_service_error_response(status_code: int, error_code: str) -> JSONResponse:
    """Структурированный ответ о недоступности внешнего API zdrav.lenreg.ru.

    Args:
        status_code: HTTP-статус (502 — API недоступен, 504 — превышен бюджет).
        error_code: Код ошибки из словаря ``format_error_message()``
            (``api_unavailable`` / ``api_timeout``).

    Returns:
        JSONResponse с полями ``error`` (код) и ``detail`` (текст для клиента).
    """
    return JSONResponse(
        status_code=status_code,
        content={"error": error_code, "detail": format_error_message(error_code)},
    )
