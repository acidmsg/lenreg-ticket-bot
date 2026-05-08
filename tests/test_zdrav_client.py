"""
Тесты для ZdravClient с мокированным HTTP-клиентом.
"""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio


@pytest_asyncio.fixture
async def mock_zdrav_client():
    """
    ZdravClient с мокированным _get_client, возвращающим AsyncMock.
    """
    from api.zdrav_client import ZdravClient

    client = ZdravClient()
    mock_http = AsyncMock()
    # Подменяем _get_client, чтобы он возвращал наш мок
    client._get_client = AsyncMock(return_value=mock_http)
    return client


def _make_response(status_code: int = 200, json_data: dict | None = None):
    """Создаёт мок-ответ httpx."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json = MagicMock(return_value=json_data or {})
    return resp


class TestZdravClient:
    """Набор тестов для ZdravClient."""

    # ── fetch_patient_id ──────────────────────────────────────────────

    async def test_fetch_patient_id_success(self, mock_zdrav_client):
        """Успешный поиск пациента возвращает ID."""
        mock_http = await mock_zdrav_client._get_client()
        mock_http.post.return_value = _make_response(
            200, {"response": {"patient_id": "12345"}}
        )

        p_id, err = await mock_zdrav_client.fetch_patient_id(
            "Иванов Иван Иванович", date(1990, 1, 1), "272"
        )
        assert p_id == "12345"
        assert err is None

    async def test_fetch_patient_id_not_found(self, mock_zdrav_client):
        """Пациент не найден."""
        mock_http = await mock_zdrav_client._get_client()
        mock_http.post.return_value = _make_response(
            200, {"response": {"patient_id": None}}
        )

        p_id, err = await mock_zdrav_client.fetch_patient_id(
            "Неизвестный Неизвестный Неизвестный", date(2000, 1, 1), "272"
        )
        assert p_id is None
        assert "не найден" in (err or "")

    async def test_fetch_patient_id_403(self, mock_zdrav_client):
        """Ошибка 403 — защита от ботов."""
        mock_http = await mock_zdrav_client._get_client()
        mock_http.post.return_value = _make_response(403)

        p_id, err = await mock_zdrav_client.fetch_patient_id(
            "Иванов Иван Иванович", date(1990, 1, 1), "272"
        )
        assert p_id is None
        assert "защита от ботов" in (err or "")

    async def test_fetch_patient_id_invalid_fio(self, mock_zdrav_client):
        """Неверный формат ФИО — 2 слова."""
        p_id, err = await mock_zdrav_client.fetch_patient_id(
            "Иванов Иван", date(1990, 1, 1), "272"
        )
        assert p_id is None
        assert "3 слова" in (err or "")

    async def test_fetch_patient_id_server_error(self, mock_zdrav_client):
        """Ошибка 500 — портал недоступен."""
        mock_http = await mock_zdrav_client._get_client()
        mock_http.post.return_value = _make_response(500)

        p_id, err = await mock_zdrav_client.fetch_patient_id(
            "Иванов Иван Иванович", date(1990, 1, 1), "272"
        )
        assert p_id is None
        assert "недоступен" in (err or "")

    # ── check_affiliation ─────────────────────────────────────────────

    async def test_check_affiliation_success(self, mock_zdrav_client):
        """Проверка прикрепления — успех."""
        mock_http = await mock_zdrav_client._get_client()
        mock_http.post.return_value = _make_response(200, {"success": True})

        result = await mock_zdrav_client.check_affiliation("123", "272")
        assert result is True

    async def test_check_affiliation_failure(self, mock_zdrav_client):
        """Проверка прикрепления — отказ."""
        mock_http = await mock_zdrav_client._get_client()
        mock_http.post.return_value = _make_response(200, {"success": False})

        result = await mock_zdrav_client.check_affiliation("123", "272")
        assert result is False

    async def test_check_affiliation_error(self, mock_zdrav_client):
        """Проверка прикрепления — ошибка сети."""
        mock_http = await mock_zdrav_client._get_client()
        mock_http.post.side_effect = Exception("Network error")

        result = await mock_zdrav_client.check_affiliation("123", "272")
        assert result is False

    # ── fetch_speciality_list ─────────────────────────────────────────

    async def test_fetch_speciality_list_success(self, mock_zdrav_client):
        """Список специальностей успешно получен."""
        mock_http = await mock_zdrav_client._get_client()
        mock_http.post.return_value = _make_response(
            200,
            {
                "success": True,
                "response": [
                    {"IdSpesiality": "1", "NameSpesiality": "Хирургия"},
                    {"IdSpesiality": "2", "NameSpesiality": "Терапия"},
                ],
            },
        )

        result = await mock_zdrav_client.fetch_speciality_list("123", "272")
        assert len(result) == 2
        assert result[0]["NameSpesiality"] == "Хирургия"

    async def test_fetch_speciality_list_failure(self, mock_zdrav_client):
        """Ошибка API — пустой список."""
        mock_http = await mock_zdrav_client._get_client()
        mock_http.post.return_value = _make_response(200, {"success": False})

        result = await mock_zdrav_client.fetch_speciality_list("123", "272")
        assert result == []

    # ── check_slots ───────────────────────────────────────────────────

    async def test_check_slots_success(self, mock_zdrav_client):
        """Проверка слотов — есть свободные."""
        mock_http = await mock_zdrav_client._get_client()
        mock_http.post.return_value = _make_response(
            200,
            {
                "response": {
                    "2026-05-10": [
                        {"date_start": {"time": "10:00"}},
                        {"date_start": {"time": "11:00"}},
                    ]
                }
            },
        )

        slots = await mock_zdrav_client.check_slots("d1", "p1", "272")
        assert slots is not None
        assert len(slots) == 2
        assert "2026-05-10 в 10:00" in slots

    async def test_check_slots_empty(self, mock_zdrav_client):
        """Проверка слотов — нет свободных (пустой ответ)."""
        mock_http = await mock_zdrav_client._get_client()
        mock_http.post.return_value = _make_response(200, {"response": {}})

        slots = await mock_zdrav_client.check_slots("d1", "p1", "272")
        assert slots == []

    async def test_check_slots_403(self, mock_zdrav_client):
        """Проверка слотов — заблокировано."""
        mock_http = await mock_zdrav_client._get_client()
        mock_http.post.return_value = _make_response(403)

        slots = await mock_zdrav_client.check_slots("d1", "p1", "272")
        assert slots is None

    async def test_check_slots_retry_on_500(self, mock_zdrav_client):
        """Проверка слотов — 3 попытки при 500 ошибке."""
        mock_http = await mock_zdrav_client._get_client()
        mock_http.post.return_value = _make_response(500)

        slots = await mock_zdrav_client.check_slots("d1", "p1", "272")
        assert slots is None
        # Должно быть 3 попытки
        assert mock_http.post.call_count == 3

    async def test_check_slots_retry_then_success(self, mock_zdrav_client):
        """После 2 ошибок 500, 3-я попытка успешна."""
        mock_http = await mock_zdrav_client._get_client()
        mock_http.post.side_effect = [
            _make_response(500),
            _make_response(500),
            _make_response(
                200, {"response": {"2026-05-10": [{"date_start": {"time": "10:00"}}]}}
            ),
        ]

        slots = await mock_zdrav_client.check_slots("d1", "p1", "272")
        assert slots is not None
        assert len(slots) == 1

    # ── fetch_all_doctors ─────────────────────────────────────────────

    async def test_fetch_all_doctors_success(self, mock_zdrav_client):
        """Список врачей успешно получен."""
        mock_http = await mock_zdrav_client._get_client()
        mock_http.post.return_value = _make_response(
            200,
            {
                "success": True,
                "response": [
                    {"IdDoc": "d1", "Name": "Иванов И.И."},
                    {"IdDoc": "d2", "Name": "Петров П.П."},
                ],
            },
        )

        doctors = await mock_zdrav_client.fetch_all_doctors("spec1", "p1", "272")
        assert len(doctors) == 2
        assert doctors[0]["Name"] == "Иванов И.И."

    async def test_fetch_all_doctors_failure(self, mock_zdrav_client):
        """Ошибка API — пустой список."""
        mock_http = await mock_zdrav_client._get_client()
        mock_http.post.return_value = _make_response(200, {"success": False})

        doctors = await mock_zdrav_client.fetch_all_doctors("spec1", "p1", "272")
        assert doctors == []

    # ── User-Agent ротация ───────────────────────────────────────────

    async def test_user_agent_rotation(self, mock_zdrav_client):
        """User-Agent выбирается из списка."""
        ua_headers = mock_zdrav_client._get_headers()
        assert "User-Agent" in ua_headers
        assert ua_headers["User-Agent"].startswith("Mozilla/5.0")
