"""
Tests for services/monitor.py — full cycle monitor_loop + _send_notification
with mocked API, Bot, and DatabaseManager.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from aiogram.exceptions import TelegramAPIError
from src.services.monitor import _send_notification, monitor_loop

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_mock_bot():
    """Creates a mock aiogram Bot."""
    bot = MagicMock()
    bot.send_message = AsyncMock()
    bot.delete_message = AsyncMock()
    return bot


def _make_mock_api():
    """Creates a mock ZdravClient."""
    api = MagicMock()
    api.check_slots = AsyncMock()
    return api


def _make_mock_db():
    """Creates a mock DatabaseManager with configurable .data property."""
    db = MagicMock()
    db.get_last_message_id = AsyncMock(return_value=None)
    db.set_last_message_id = AsyncMock()
    return db


def _make_user_data(
    uid="123",
    p_id="p1",
    d_id="d1",
    d_name="Иванов Иван Иванович",
    d_spec="Терапия",
    clinic_id="272",
    p_fio="Петров Пётр Петрович",
    p_alias=None,
):
    """Builds a user data dict mimicking DatabaseManager.data structure."""
    p_info = {"fio": p_fio, "bday": "1990-01-01"}
    if p_alias:
        p_info["alias"] = p_alias
    if clinic_id:
        p_info["clinic_id"] = clinic_id

    return {
        uid: {
            "patients": {p_id: p_info},
            "monitoring": {
                p_id: {
                    d_id: {
                        "name": d_name,
                        "specialty": d_spec,
                        "clinic_id": clinic_id,
                    }
                }
            },
            "last_messages": {},
        }
    }


# ── _send_notification ───────────────────────────────────────────────────────


class TestSendNotification:
    """Tests for _send_notification function."""

    async def test_sends_new_message_no_previous(self):
        """Sends a new message when there is no previous message_id."""
        bot = _make_mock_bot()
        db = _make_mock_db()
        db.get_last_message_id.return_value = None

        sent_msg = MagicMock()
        sent_msg.message_id = 555
        bot.send_message.return_value = sent_msg

        await _send_notification(bot, "123", "Hello!", db, "p1", "d1")

        bot.delete_message.assert_not_called()
        # uid преобразуется в int при вызове _send_or_update_message
        bot.send_message.assert_called_once_with(
            123, "Hello!", parse_mode="Markdown", reply_markup=None
        )
        db.set_last_message_id.assert_called_once_with("123", "p1", "d1", 555)

    async def test_deletes_previous_message_and_sends_new(self):
        """Deletes previous message before sending a new one."""
        bot = _make_mock_bot()
        db = _make_mock_db()
        db.get_last_message_id.return_value = 100

        sent_msg = MagicMock()
        sent_msg.message_id = 200
        bot.send_message.return_value = sent_msg

        await _send_notification(bot, "123", "Updated!", db, "p1", "d1")

        bot.delete_message.assert_called_once_with(123, 100)
        bot.send_message.assert_called_once_with(
            123, "Updated!", parse_mode="Markdown", reply_markup=None
        )
        db.set_last_message_id.assert_called_once_with("123", "p1", "d1", 200)

    async def test_handles_delete_message_exception_gracefully(self):
        """If delete_message raises, send_message still proceeds."""
        bot = _make_mock_bot()
        bot.delete_message.side_effect = TelegramAPIError(
            method=MagicMock(), message="Message not found"
        )
        db = _make_mock_db()
        db.get_last_message_id.return_value = 999

        sent_msg = MagicMock()
        sent_msg.message_id = 300
        bot.send_message.return_value = sent_msg

        # Should not raise
        await _send_notification(bot, "123", "Msg", db, "p1", "d1")

        bot.delete_message.assert_called_once_with(123, 999)
        bot.send_message.assert_called_once_with(
            123, "Msg", parse_mode="Markdown", reply_markup=None
        )

    async def test_handles_send_message_exception_gracefully(self):
        """If send_message raises, no crash and no set_last_message_id."""
        bot = _make_mock_bot()
        bot.send_message.side_effect = Exception("Telegram API error")
        db = _make_mock_db()
        db.get_last_message_id.return_value = None

        # Should not raise
        await _send_notification(bot, "123", "Msg", db, "p1", "d1")

        bot.send_message.assert_called_once()
        db.set_last_message_id.assert_not_called()


# ── monitor_loop ─────────────────────────────────────────────────────────────


class TestMonitorLoop:
    """Tests for monitor_loop with mocked external dependencies.

    monitor_loop catches CancelledError internally and breaks out of the
    infinite loop, returning normally. Tests mock asyncio.sleep to raise
    CancelledError after a specific number of calls, which monitor_loop
    handles internally.
    """

    @staticmethod
    def _setup_monitor_mocks(
        monkeypatch,
        user_data,
        check_slots_return,
        swap_cache_return=None,
        sleep_raises_on_call=2,
    ):
        """Sets up all mocks needed for monitor_loop.

        Returns (bot, api, db, swap_mock, safe_set_mock, notify_mock).

        sleep_raises_on_call: which call to asyncio.sleep raises CancelledError
        (caught internally by monitor_loop to break the infinite loop).
        Default 2 = after first per-doctor sleep + outer jitter sleep.
        """
        bot = _make_mock_bot()
        sent_msg = MagicMock()
        sent_msg.message_id = 42
        bot.send_message.return_value = sent_msg

        api = _make_mock_api()
        api.check_slots.return_value = check_slots_return

        db = _make_mock_db()
        # Make .data a property-like attribute on the mock instance
        type(db).data = property(lambda self: user_data)

        # Mock asyncio.sleep: raise CancelledError on specific call
        sleep_count = [0]

        async def mock_sleep(seconds):
            sleep_count[0] += 1
            if sleep_count[0] >= sleep_raises_on_call:
                raise asyncio.CancelledError()

        monkeypatch.setattr(asyncio, "sleep", mock_sleep)

        # Mock random.uniform to return tiny values for speed
        monkeypatch.setattr("random.uniform", lambda a, b: 0.01)

        # Mock swap_cache_key
        swap_mock = AsyncMock(return_value=swap_cache_return)
        monkeypatch.setattr("src.services.monitor.swap_cache_key", swap_mock)

        # Mock _safe_set (imported at module top in src.services.monitor)
        safe_set_mock = AsyncMock()
        monkeypatch.setattr("src.services.monitor._safe_set", safe_set_mock)

        # Mock _send_notification (same module) to avoid real bot calls
        notify_mock = AsyncMock()
        monkeypatch.setattr("src.services.monitor._send_notification", notify_mock)

        return bot, api, db, swap_mock, safe_set_mock, notify_mock

    # ── Basic flow ───────────────────────────────────────────────────────

    async def test_monitors_single_doctor_slots_appeared(self, monkeypatch):
        """Slots appear from None → notification sent."""
        user_data = _make_user_data()
        bot, api, db, swap_mock, safe_set_mock, notify_mock = self._setup_monitor_mocks(
            monkeypatch,
            user_data,
            check_slots_return=["2026-05-15 в 10:00"],
            swap_cache_return=None,
        )

        await monitor_loop(bot, api, db, initial_sync=False)

        # Verify _safe_set was called at start
        safe_set_mock.assert_called_with("monitor_loop_alive", True)

        # Verify API was called
        api.check_slots.assert_called_once_with(
            "d1", "p1", "272", limiter=api.limiter_monitor
        )

        # Verify swap_cache_key was called
        swap_mock.assert_called_once()
        args = swap_mock.call_args[0]
        assert args[0] == "123_p1_d1"
        assert args[1] == ["2026-05-15 в 10:00"]

        # Verify notification was sent
        notify_mock.assert_called_once()
        call_args = notify_mock.call_args[0]
        assert call_args[0] is bot
        assert call_args[1] == "123"
        assert "Появились свободные номерки" in call_args[2]
        assert call_args[3] is db
        assert call_args[4] == "p1"
        assert call_args[5] == "d1"

    async def test_monitors_doctor_slots_disappeared(self, monkeypatch):
        """Slots disappear (was a list, now empty) → notification sent."""
        user_data = _make_user_data()
        bot, api, db, swap_mock, safe_set_mock, notify_mock = self._setup_monitor_mocks(
            monkeypatch,
            user_data,
            check_slots_return=[],
            swap_cache_return=["2026-05-15 в 10:00"],
            sleep_raises_on_call=6,
        )

        await monitor_loop(bot, api, db)

        swap_mock.assert_called_once()
        args = swap_mock.call_args[0]
        assert args[0] == "123_p1_d1"
        assert args[1] == "NONE"

        notify_mock.assert_called_once()
        call_args = notify_mock.call_args[0]
        assert "Номерков в данный момент нет" in call_args[2]

    async def test_monitors_doctor_no_change(self, monkeypatch):
        """Slots unchanged → no notification sent."""
        user_data = _make_user_data()
        bot, api, db, swap_mock, safe_set_mock, notify_mock = self._setup_monitor_mocks(
            monkeypatch,
            user_data,
            check_slots_return=["2026-05-15 в 10:00"],
            swap_cache_return=["2026-05-15 в 10:00"],
        )

        await monitor_loop(bot, api, db)

        swap_mock.assert_called_once()
        notify_mock.assert_not_called()

    async def test_monitors_doctor_first_discovery(self, monkeypatch):
        """First discovery (old=None, slots present) → notification sent."""
        user_data = _make_user_data()
        bot, api, db, swap_mock, safe_set_mock, notify_mock = self._setup_monitor_mocks(
            monkeypatch,
            user_data,
            check_slots_return=["2026-05-15 в 10:00"],
            swap_cache_return=None,
        )

        await monitor_loop(bot, api, db, initial_sync=False)
        notify_mock.assert_called_once()

    async def test_monitors_doctor_first_discovery_empty_no_notification(
        self, monkeypatch
    ):
        """First discovery (old=None, slots empty) → no notification."""
        user_data = _make_user_data()
        bot, api, db, swap_mock, safe_set_mock, notify_mock = self._setup_monitor_mocks(
            monkeypatch,
            user_data,
            check_slots_return=[],
            swap_cache_return=None,
        )

        await monitor_loop(bot, api, db)
        notify_mock.assert_not_called()

    async def test_monitors_doctor_already_empty_no_duplicate(self, monkeypatch):
        """Already NONE, still empty → no notification (suppress duplicate)."""
        user_data = _make_user_data()
        bot, api, db, swap_mock, safe_set_mock, notify_mock = self._setup_monitor_mocks(
            monkeypatch,
            user_data,
            check_slots_return=[],
            swap_cache_return="NONE",
        )

        await monitor_loop(bot, api, db)
        notify_mock.assert_not_called()

    # ── Empty slots protection (3 retries) ───────────────────────────────

    async def test_empty_slots_require_3_consecutive_empty(self, monkeypatch):
        """Empty slots acted upon only after 3 consecutive empty responses."""
        user_data = _make_user_data()
        # sleep_raises_on_call=6: per-doc sleep (3×) + jitter (3×) → raise on 6th
        bot, api, db, swap_mock, safe_set_mock, notify_mock = self._setup_monitor_mocks(
            monkeypatch,
            user_data,
            check_slots_return=[],
            swap_cache_return=["2026-05-10 в 10:00"],
            sleep_raises_on_call=6,
        )

        await monitor_loop(bot, api, db)

        # API called 3 times (first 2 retries skipped, 3rd succeeds)
        assert api.check_slots.call_count == 3
        # swap_cache_key only called on 3rd empty (protection passed)
        swap_mock.assert_called_once()
        notify_mock.assert_called_once()

    # ── API error (returns None) ─────────────────────────────────────────

    async def test_api_error_skips_doctor(self, monkeypatch):
        """When API returns None, doctor is skipped (no notification)."""
        user_data = _make_user_data()
        bot, api, db, swap_mock, safe_set_mock, notify_mock = self._setup_monitor_mocks(
            monkeypatch,
            user_data,
            check_slots_return=None,
            swap_cache_return=None,
        )

        await monitor_loop(bot, api, db)

        api.check_slots.assert_called_once()
        swap_mock.assert_not_called()
        notify_mock.assert_not_called()

    # ── CancelledError handling ──────────────────────────────────────────

    async def test_cancelled_error_breaks_loop(self, monkeypatch):
        """CancelledError is caught internally and loop exits cleanly."""
        user_data = _make_user_data()
        bot, api, db, swap_mock, safe_set_mock, notify_mock = self._setup_monitor_mocks(
            monkeypatch,
            user_data,
            check_slots_return=["2026-05-15 в 10:00"],
            swap_cache_return=None,
        )

        await monitor_loop(bot, api, db, initial_sync=False)
        notify_mock.assert_called_once()

    # ── Multiple doctors ─────────────────────────────────────────────────

    async def test_multiple_doctors_all_checked(self, monkeypatch):
        """All monitored doctors across patients are checked."""
        user_data = {
            "u1": {
                "patients": {
                    "p1": {"fio": "Пациент 1", "clinic_id": "272"},
                    "p2": {"fio": "Пациент 2", "clinic_id": "271"},
                },
                "monitoring": {
                    "p1": {
                        "d1": {
                            "name": "Врач 1",
                            "specialty": "Терапия",
                            "clinic_id": "272",
                        },
                        "d2": {
                            "name": "Врач 2",
                            "specialty": "Хирургия",
                            "clinic_id": "272",
                        },
                    },
                    "p2": {
                        "d3": {
                            "name": "Врач 3",
                            "specialty": "Педиатрия",
                            "clinic_id": "271",
                        },
                    },
                },
                "last_messages": {},
            }
        }

        # sleep_raises_on_call=5: 3 per-doctor + 1 jitter = 4, raise on 5th
        bot, api, db, swap_mock, safe_set_mock, notify_mock = self._setup_monitor_mocks(
            monkeypatch,
            user_data,
            check_slots_return=["2026-05-15 в 10:00"],
            swap_cache_return=None,
            sleep_raises_on_call=5,
        )

        await monitor_loop(bot, api, db, initial_sync=False)

        assert api.check_slots.call_count == 3
        assert notify_mock.call_count == 3

    # ── Legacy string doctor info ────────────────────────────────────────

    async def test_legacy_string_doctor_info(self, monkeypatch):
        """Doctor info stored as plain string (not dict) still works."""
        user_data = {
            "u1": {
                "patients": {"p1": {"fio": "Пациент", "clinic_id": "272"}},
                "monitoring": {"p1": {"d1": "Иванов Иван Иванович"}},
                "last_messages": {},
            }
        }

        bot, api, db, swap_mock, safe_set_mock, notify_mock = self._setup_monitor_mocks(
            monkeypatch,
            user_data,
            check_slots_return=["2026-05-15 в 10:00"],
            swap_cache_return=None,
        )

        await monitor_loop(bot, api, db, initial_sync=False)

        api.check_slots.assert_called_once()
        notify_mock.assert_called_once()

    # ── Patient alias fallback ───────────────────────────────────────────

    async def test_patient_alias_used_in_notification(self, monkeypatch):
        """Patient alias is preferred over fio in notification text."""
        user_data = _make_user_data(p_alias="Петя")
        bot, api, db, swap_mock, safe_set_mock, notify_mock = self._setup_monitor_mocks(
            monkeypatch,
            user_data,
            check_slots_return=["2026-05-15 в 10:00"],
            swap_cache_return=None,
        )

        await monitor_loop(bot, api, db, initial_sync=False)

        call_args = notify_mock.call_args[0]
        assert "Петя" in call_args[2]
        assert "Петров Пётр Петрович" not in call_args[2]

    # ── Generic exception in loop body ───────────────────────────────────

    async def test_generic_exception_continues_loop(self, monkeypatch):
        """A generic exception inside the loop body doesn't crash the loop."""
        user_data = _make_user_data()

        bot = _make_mock_bot()

        # check_slots raises RuntimeError on first call, succeeds on second
        api = _make_mock_api()
        api.check_slots = AsyncMock(
            side_effect=[
                RuntimeError("Simulated crash"),
                ["2026-05-15 в 10:00"],
            ]
        )

        db = _make_mock_db()
        type(db).data = property(lambda self: user_data)

        # sleep_raises_on_call=4: iter1 per-doctor (1) + exception sleep60 (2)
        # + iter2 per-doctor (3) + jitter (4 → CancelledError breaks loop)
        sleep_count = [0]

        async def mock_sleep(seconds):
            sleep_count[0] += 1
            if sleep_count[0] >= 4:
                raise asyncio.CancelledError()

        monkeypatch.setattr(asyncio, "sleep", mock_sleep)
        monkeypatch.setattr("random.uniform", lambda a, b: 0.01)
        swap_mock = AsyncMock(return_value=None)
        monkeypatch.setattr("src.services.monitor.swap_cache_key", swap_mock)
        safe_set_mock = AsyncMock()
        monkeypatch.setattr("src.services.healthcheck._safe_set", safe_set_mock)
        notify_mock = AsyncMock()
        monkeypatch.setattr("src.services.monitor._send_notification", notify_mock)

        # Should complete without raising
        await monitor_loop(bot, api, db)

        # Survived exception and continued to 2nd iteration
        assert api.check_slots.call_count >= 2
        assert notify_mock.call_count >= 1

    # ── New slots with [NEW] marking ─────────────────────────────────────

    async def test_new_slots_marked_in_notification(self, monkeypatch):
        """When new slots appear alongside old ones, [NEW] appears in text."""
        old_slots = ["2026-05-10 в 10:00"]
        new_slots = ["2026-05-10 в 10:00", "2026-05-11 в 11:00"]

        user_data = _make_user_data()
        bot, api, db, swap_mock, safe_set_mock, notify_mock = self._setup_monitor_mocks(
            monkeypatch,
            user_data,
            check_slots_return=new_slots,
            swap_cache_return=old_slots,
        )

        await monitor_loop(bot, api, db, initial_sync=False)

        notify_mock.assert_called_once()
        call_args = notify_mock.call_args[0]
        assert "🆕" in call_args[2]
        assert "11:00" in call_args[2]

    # ── Initial sync suppression ──────────────────────────────────────────

    async def test_initial_sync_suppresses_notifications(self, monkeypatch):
        """При initial_sync=True уведомления не отправляются, кэш заполняется."""
        user_data = _make_user_data()
        bot, api, db, swap_mock, safe_set_mock, notify_mock = self._setup_monitor_mocks(
            monkeypatch,
            user_data,
            check_slots_return=["2026-05-15 в 10:00"],
            swap_cache_return=None,
        )

        # initial_sync=True по умолчанию — первый цикл без уведомлений
        await monitor_loop(bot, api, db)

        # Кэш должен быть заполнен
        swap_mock.assert_called_once()
        # Уведомление НЕ должно быть отправлено
        notify_mock.assert_not_called()
