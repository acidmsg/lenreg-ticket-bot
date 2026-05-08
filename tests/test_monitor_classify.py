"""
Тесты для _classify_slot_change из services/monitor.py.
"""

from services.monitor import _classify_slot_change


class TestClassifySlotChange:
    """Тесты для _classify_slot_change."""

    def test_no_slots_was_none(self):
        """Номерков нет, раньше было None — не уведомлять."""
        result = _classify_slot_change([], None)
        assert result is None

    def test_no_slots_was_none_str(self):
        """Номерков нет, раньше было "NONE" — не уведомлять (уже было пусто)."""
        result = _classify_slot_change([], "NONE")
        assert result is None

    def test_no_slots_was_list(self):
        """Номерки исчезли — уведомить с header."""
        result = _classify_slot_change([], ["2026-05-10 в 10:00"])
        assert result is not None
        header, display_slots = result
        assert "Номерков в данный момент нет" in header
        assert display_slots is None

    def test_slots_appeared_from_none(self):
        """Появились номерки после None."""
        slots = ["2026-05-10 в 10:00"]
        result = _classify_slot_change(slots, None)
        assert result is not None
        header, display_slots = result
        assert "Появились свободные номерки" in header
        assert display_slots == slots

    def test_slots_appeared_from_empty(self):
        """Появились номерки после "NONE"."""
        slots = ["2026-05-10 в 10:00"]
        result = _classify_slot_change(slots, "NONE")
        assert result is not None
        header, _ = result
        assert "Появились свободные номерки" in header

    def test_new_slots_added(self):
        """Появились новые номерки в дополнение к существующим."""
        old_slots = ["2026-05-10 в 10:00"]
        new_slots = ["2026-05-10 в 10:00", "2026-05-10 в 11:00"]
        result = _classify_slot_change(new_slots, old_slots)
        assert result is not None
        header, display_slots = result
        assert "Появились НОВЫЕ номерки" in header
        assert display_slots is not None
        # Новый слот должен быть помечен [NEW]
        assert "[NEW] 2026-05-10 в 11:00" in display_slots
        assert "2026-05-10 в 10:00" in display_slots

    def test_slots_unchanged(self):
        """Номерки не изменились — не уведомлять."""
        slots = ["2026-05-10 в 10:00"]
        result = _classify_slot_change(slots, slots)
        assert result is None

    def test_slots_slightly_decreased_not_notify(self):
        """Небольшое уменьшение (ниже порога) — не уведомлять."""
        old_slots = [f"slot_{i}" for i in range(10)]
        new_slots = [f"slot_{i}" for i in range(9)]  # 10% decrease
        result = _classify_slot_change(new_slots, old_slots)
        assert result is None

    def test_slots_decreased_below_absolute_threshold(self, monkeypatch):
        """Уменьшение ниже абсолютного порога — уведомить."""
        import config

        monkeypatch.setattr(config.settings, "SLOT_THRESHOLD_ABSOLUTE", 5)

        old_slots = [f"slot_{i}" for i in range(10)]
        new_slots = [f"slot_{i}" for i in range(4)]  # стало 4, меньше 5
        result = _classify_slot_change(new_slots, old_slots)
        assert result is not None
        header, display_slots = result
        assert "уменьшилось до 4" in header
        assert display_slots == new_slots

    def test_slots_decreased_by_percentage(self, monkeypatch):
        """Уменьшение на >= 25% — уведомить."""
        import config

        monkeypatch.setattr(config.settings, "SLOT_THRESHOLD_ABSOLUTE", 5)
        monkeypatch.setattr(config.settings, "SLOT_THRESHOLD_PERCENTAGE", 0.25)

        old_slots = [f"slot_{i}" for i in range(10)]
        new_slots = [f"slot_{i}" for i in range(7)]  # 30% decrease > 25%
        result = _classify_slot_change(new_slots, old_slots)
        assert result is not None
        header, display_slots = result
        assert "уменьшилось до 7" in header
        assert display_slots == new_slots

    def test_slots_decreased_below_percentage_threshold(self):
        """Уменьшение менее 25% — не уведомлять."""
        old_slots = [f"slot_{i}" for i in range(10)]
        new_slots = [f"slot_{i}" for i in range(8)]  # 20% decrease < 25%
        result = _classify_slot_change(new_slots, old_slots)
        assert result is None

    def test_multiple_new_slots(self):
        """Несколько новых слотов — все помечаются [NEW]."""
        old_slots = ["2026-05-10 в 10:00"]
        new_slots = ["2026-05-10 в 10:00", "2026-05-11 в 09:00", "2026-05-11 в 10:00"]
        result = _classify_slot_change(new_slots, old_slots)
        assert result is not None
        _, display_slots = result
        assert display_slots is not None
        new_count = sum(1 for s in display_slots if "[NEW]" in s)
        assert new_count == 2
