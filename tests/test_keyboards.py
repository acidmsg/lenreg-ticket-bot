"""
Тесты для keyboards/inline.py — T4.
"""

import pytest
from aiogram.utils.keyboard import InlineKeyboardBuilder


def _extract_buttons(markup):
    """Извлекает список (text, callback_data) из InlineKeyboardMarkup."""
    buttons = []
    for row in markup.inline_keyboard:
        for btn in row:
            buttons.append((btn.text, btn.callback_data))
    return buttons


def _extract_rows(markup):
    """Извлекает список рядов, каждый ряд — список (text, callback_data)."""
    rows = []
    for row in markup.inline_keyboard:
        rows.append([(btn.text, btn.callback_data) for btn in row])
    return rows


# ── T4.4 get_registration_keyboard ────────────────────────────────────


class TestRegistrationKeyboard:
    """Тесты get_registration_keyboard."""

    def test_alias_step_has_skip_button(self):
        from keyboards.inline import get_registration_keyboard

        mk = get_registration_keyboard(step="alias")
        buttons = _extract_buttons(mk)
        assert ("Пропустить", "skip_alias") in buttons
        assert ("❌ Отмена регистрации", "cancel_registration") in buttons

    def test_fio_step_no_skip_button(self):
        from keyboards.inline import get_registration_keyboard

        mk = get_registration_keyboard(step="fio")
        buttons = _extract_buttons(mk)
        assert ("Пропустить", "skip_alias") not in buttons
        assert ("❌ Отмена регистрации", "cancel_registration") in buttons

    def test_bday_step_no_skip_button(self):
        from keyboards.inline import get_registration_keyboard

        mk = get_registration_keyboard(step="bday")
        buttons = _extract_buttons(mk)
        assert ("Пропустить", "skip_alias") not in buttons
        assert ("❌ Отмена регистрации", "cancel_registration") in buttons


# ── T4.2 get_confirm_deletion ─────────────────────────────────────────


class TestConfirmDeletion:
    """Тесты get_confirm_deletion."""

    def test_buttons_present(self):
        from keyboards.inline import get_confirm_deletion

        mk = get_confirm_deletion("patient_123")
        buttons = _extract_buttons(mk)
        assert ("✅ Да, удалить", "del_p_yes_patient_123") in buttons
        assert ("❌ Нет", "sel_p_patient_123") in buttons

    def test_returns_markup(self):
        from keyboards.inline import get_confirm_deletion

        mk = get_confirm_deletion("abc")
        # Две кнопки в одном ряду (adjust(2))
        rows = _extract_rows(mk)
        assert len(rows) == 1
        assert len(rows[0]) == 2


# ── T4.3 _short_clinic_label ──────────────────────────────────────────


class TestShortClinicLabel:
    """Тесты _short_clinic_label — вспомогательная функция."""

    def test_extracts_after_quote(self):
        from keyboards.inline import _short_clinic_label

        name = 'ГБУЗ "Городская поликлиника №1" Детское отделение'
        result = _short_clinic_label(name, 0)
        assert result == "Детское отделение"

    def test_extracts_after_quote_with_count(self):
        from keyboards.inline import _short_clinic_label

        name = 'ГБУЗ "Поликлиника №2" Взрослое отделение'
        result = _short_clinic_label(name, 3)
        assert result == "Взрослое отделение (3)"

    def test_no_quote_fallback_short(self):
        from keyboards.inline import _short_clinic_label

        name = "Короткое название"
        result = _short_clinic_label(name, 0)
        assert result == "Короткое название"

    def test_no_quote_fallback_long(self):
        from keyboards.inline import _short_clinic_label

        name = "Очень длинное название поликлиники которое превышает пятьдесят символов точно"
        result = _short_clinic_label(name, 0)
        assert result == name[:50] + "..."

    def test_empty_quote_content(self):
        from keyboards.inline import _short_clinic_label

        name = 'ГБУЗ ""'
        result = _short_clinic_label(name, 1)
        # После последней кавычки пусто — fallback на полное имя (короткое)
        assert result == 'ГБУЗ "" (1)'


# ── T4.1 get_patient_selection ────────────────────────────────────────


class TestPatientSelection:
    """Тесты get_patient_selection."""

    SAMPLE_PATIENTS = {
        "p1": {"alias": "Мама", "fio": "Иванова Анна Петровна"},
        "p2": {"alias": None, "fio": "Петров Иван Сидорович"},
        "p3": {"alias": "Сын", "fio": "Сидоров Пётр Александрович"},
    }

    def test_no_patients_only_add_button(self):
        from keyboards.inline import get_patient_selection

        mk = get_patient_selection({}, {})
        buttons = _extract_buttons(mk)
        assert len(buttons) == 1
        assert buttons[0] == ("➕ Добавить пациента", "start_add_p")

    def test_patients_sorted_by_display_name(self):
        """Сортировка по alias (если есть) или fio, алфавитно."""
        from keyboards.inline import get_patient_selection

        mk = get_patient_selection(self.SAMPLE_PATIENTS, {})
        buttons = _extract_buttons(mk)

        # Ожидаемый порядок: Мама (p1), Петров Иван Сидорович (p2), Сын (p3)
        # Плюс кнопка "Добавить"
        assert buttons[0] == ("👤 Мама", "sel_p_p1")
        assert buttons[1] == ("🗑", "del_p_ask_p1")
        assert buttons[2] == ("👤 Петров Иван Сидорович", "sel_p_p2")
        assert buttons[3] == ("🗑", "del_p_ask_p2")
        assert buttons[4] == ("👤 Сын", "sel_p_p3")
        assert buttons[5] == ("🗑", "del_p_ask_p3")
        assert buttons[6] == ("➕ Добавить пациента", "start_add_p")

    def test_monitoring_count_shown(self):
        from keyboards.inline import get_patient_selection

        monitoring = {"p1": {"d1": {}, "d2": {}}, "p3": {"d3": {}}}
        mk = get_patient_selection(self.SAMPLE_PATIENTS, monitoring)
        buttons = _extract_buttons(mk)
        assert buttons[0] == ("👤 Мама (2)", "sel_p_p1")
        assert buttons[2] == ("👤 Петров Иван Сидорович", "sel_p_p2")  # no count
        assert buttons[4] == ("👤 Сын (1)", "sel_p_p3")

    def test_stop_all_button_when_active_monitoring(self):
        from keyboards.inline import get_patient_selection

        monitoring = {"p1": {"d1": {}}}
        mk = get_patient_selection(self.SAMPLE_PATIENTS, monitoring)
        buttons = _extract_buttons(mk)
        assert ("🛑 Сбросить весь мониторинг", "stop_all") in buttons

    def test_no_stop_all_when_no_monitoring(self):
        from keyboards.inline import get_patient_selection

        mk = get_patient_selection(self.SAMPLE_PATIENTS, {})
        buttons = _extract_buttons(mk)
        assert ("🛑 Сбросить весь мониторинг", "stop_all") not in buttons

    def test_row_structure_patients_in_pairs(self):
        """Каждый пациент — 2 кнопки в ряду, затем 1 кнопка добавить."""
        from keyboards.inline import get_patient_selection

        mk = get_patient_selection(self.SAMPLE_PATIENTS, {})
        rows = _extract_rows(mk)
        # 3 пациента → 3 ряда по 2 кнопки + 1 ряд с кнопкой "Добавить"
        assert len(rows) == 4
        for i in range(3):
            assert len(rows[i]) == 2
        assert len(rows[3]) == 1


# ── T4.5 get_city_selection ───────────────────────────────────────────


class TestCitySelection:
    """Тесты get_city_selection."""

    def test_cities_with_indices(self):
        from keyboards.inline import get_city_selection

        mk = get_city_selection(
            p_id="p1",
            cities=["Москва", "Санкт-Петербург", "Казань"],
        )
        buttons = _extract_buttons(mk)
        # Города с 1-based индексами
        assert ("📍 Москва", "sel_cty_p1_1") in buttons
        assert ("📍 Санкт-Петербург", "sel_cty_p1_2") in buttons
        assert ("📍 Казань", "sel_cty_p1_3") in buttons
        # Все города
        assert ("🏥 Все", "sel_cty_p1_all") in buttons
        # Навигация
        assert ("⬅️ Назад к списку", "back_to_main") in buttons

    def test_monitoring_counts_per_city(self):
        from keyboards.inline import get_city_selection

        monitoring = {
            "p1": {
                "d1": {"clinic_id": "271"},
                "d2": {"clinic_id": "271"},
                "d3": {"clinic_id": "272"},
            }
        }
        clinics_data = [
            {"clinic_id": "271", "city": "Москва"},
            {"clinic_id": "272", "city": "Казань"},
        ]
        mk = get_city_selection(
            p_id="p1",
            cities=["Москва", "Казань"],
            monitoring=monitoring,
            clinics_data=clinics_data,
        )
        buttons = _extract_buttons(mk)
        assert ("📍 Москва (2)", "sel_cty_p1_1") in buttons
        assert ("📍 Казань (1)", "sel_cty_p1_2") in buttons
        assert ("🏥 Все (3)", "sel_cty_p1_all") in buttons

    def test_stop_patient_button_when_monitoring(self):
        from keyboards.inline import get_city_selection

        monitoring = {"p1": {"d1": {"clinic_id": "271"}}}
        clinics_data = [{"clinic_id": "271", "city": "Москва"}]
        mk = get_city_selection(
            p_id="p1",
            cities=["Москва"],
            monitoring=monitoring,
            clinics_data=clinics_data,
        )
        buttons = _extract_buttons(mk)
        assert (
            "🛑 Сбросить мониторинг этого пациента",
            "stop_patient_p1_city",
        ) in buttons

    def test_no_stop_button_when_no_monitoring(self):
        from keyboards.inline import get_city_selection

        mk = get_city_selection(p_id="p1", cities=["Москва"])
        buttons = _extract_buttons(mk)
        assert (
            "🛑 Сбросить мониторинг этого пациента",
            "stop_patient_p1_city",
        ) not in buttons

    def test_no_cities_all_button_only(self):
        from keyboards.inline import get_city_selection

        mk = get_city_selection(p_id="p1")
        buttons = _extract_buttons(mk)
        assert ("🏥 Все клиники", "sel_cty_p1_all") in buttons


# ── T4.6 get_doctor_selection ─────────────────────────────────────────


class TestDoctorSelection:
    """Тесты get_doctor_selection."""

    DOCTORS = {
        "d1": {"name": "Иванов Иван Иванович", "specialty": "Терапия"},
        "d2": {"name": "Петров Пётр Петрович", "specialty": "Хирургия"},
        "d3": {"name": "Сидоров Алексей Борисович", "specialty": "Терапия"},
        "d4": {"name": "Кабинет УЗИ", "specialty": ""},  # кабинет
        "d5": {"name": "Процедурный кабинет", "specialty": ""},  # кабинет
    }

    def test_doctors_sorted_by_specialty_then_name(self):
        from keyboards.inline import get_doctor_selection

        mk = get_doctor_selection("p1", "271", self.DOCTORS, {})
        buttons = _extract_buttons(mk)
        # Врачи должны идти раньше кабинетов
        # Терапия: Иванов → Сидоров, Хирургия: Петров
        # Затем кабинеты по алфавиту: Кабинет УЗИ → Процедурный кабинет
        assert (
            buttons[0][0] == "▫️ [Терапевт] Иванов И. И."
        )  # shorten_fio + shorten_specialty
        assert buttons[1][0] == "▫️ [Терапевт] Сидоров А. Б."
        assert buttons[2][0] == "▫️ [Хирург] Петров П. П."
        # Кабинеты
        assert buttons[3][0] == "▫️ Кабинет УЗИ"
        assert buttons[4][0] == "▫️ Процедурный кабинет"

    def test_monitored_doctor_has_checkmark(self):
        from keyboards.inline import get_doctor_selection

        monitored = {"d1": {"name": "Иванов И.И.", "clinic_id": "271"}}
        mk = get_doctor_selection("p1", "271", self.DOCTORS, monitored)
        buttons = _extract_buttons(mk)
        assert buttons[0][0] == "✅ [Терапевт] Иванов И. И."

    def test_callback_data_format(self):
        from keyboards.inline import get_doctor_selection

        mk = get_doctor_selection("p_abc", "300", self.DOCTORS, {})
        buttons = _extract_buttons(mk)
        assert buttons[0][1] == "tgl_p_abc_300_d1"

    def test_navigation_buttons(self):
        from keyboards.inline import get_doctor_selection

        mk = get_doctor_selection("p1", "271", self.DOCTORS, {}, city_idx="2")
        buttons = _extract_buttons(mk)
        assert ("⬅️ К выбору клиники", "back_to_clinics_p1_2") in buttons
        assert ("⬅️ Назад к списку", "back_to_main") in buttons

    def test_stop_clinic_button_when_monitoring_in_clinic(self):
        from keyboards.inline import get_doctor_selection

        monitored = {
            "d1": {"name": "X", "clinic_id": "271"},
            "d9": {"name": "Y", "clinic_id": "999"},
        }
        mk = get_doctor_selection("p1", "271", self.DOCTORS, monitored)
        buttons = _extract_buttons(mk)
        # d1 в клинике 271 — кнопка сброса должна быть
        assert ("🛑 Сбросить мониторинг этой клиники", "stop_clinic_p1_271") in buttons

    def test_no_stop_clinic_when_no_monitoring_in_that_clinic(self):
        from keyboards.inline import get_doctor_selection

        monitored = {"d9": {"name": "Y", "clinic_id": "999"}}  # другая клиника
        mk = get_doctor_selection("p1", "271", self.DOCTORS, monitored)
        buttons = _extract_buttons(mk)
        assert (
            "🛑 Сбросить мониторинг этой клиники",
            "stop_clinic_p1_271",
        ) not in buttons

    def test_dental_clinic_filters_child_specialties(self):
        """Клиника 272: для детей — только 'детск' специальности."""
        from keyboards.inline import get_doctor_selection

        doctors = {
            "d1": {
                "name": "Иванов Иван Иванович",
                "specialty": "Стоматология общей практики",
            },
            "d2": {"name": "Петров Пётр Петрович", "specialty": "Детская стоматология"},
            "d3": {"name": "Сидоров Алексей Борисович", "specialty": "Ортодонтия"},
        }
        # Ребёнок (bday 2020-01-01 → ~6 лет)
        mk = get_doctor_selection("p1", "272", doctors, {}, bday_str="2020-01-01")
        buttons = _extract_buttons(mk)
        # Только d2 (Детская стоматология) — содержит "детск"
        doctor_texts = [b[0] for b in buttons if b[1].startswith("tgl_")]
        assert len(doctor_texts) == 1
        assert "Дет. стоматолог" in doctor_texts[0]

    def test_dental_clinic_filters_adult_specialties(self):
        """Клиника 272: для взрослых — исключаем 'детск'."""
        from keyboards.inline import get_doctor_selection

        doctors = {
            "d1": {
                "name": "Иванов Иван Иванович",
                "specialty": "Стоматология общей практики",
            },
            "d2": {"name": "Петров Пётр Петрович", "specialty": "Детская стоматология"},
        }
        # Взрослый (bday 1990-01-01 → ~36 лет)
        mk = get_doctor_selection("p1", "272", doctors, {}, bday_str="1990-01-01")
        buttons = _extract_buttons(mk)
        doctor_texts = [b[0] for b in buttons if b[1].startswith("tgl_")]
        assert len(doctor_texts) == 1
        assert "Стоматолог" in doctor_texts[0]


# ── T4.7 get_clinic_selection ─────────────────────────────────────────


class TestClinicSelection:
    """Тесты get_clinic_selection."""

    CLINICS_DATA = [
        {
            "clinic_id": "271",
            "name": 'ГБУЗ "Поликлиника №1" Взрослое отделение',
            "type": "adult",
            "city": "Москва",
        },
        {
            "clinic_id": "272",
            "name": 'ГБУЗ "Стоматология №1" Стоматологическое отделение',
            "type": "all",
            "city": "Москва",
        },
        {
            "clinic_id": "161",
            "name": 'ГБУЗ "Детская поликлиника" Детское отделение',
            "type": "child",
            "city": "Казань",
        },
        {
            "clinic_id": "300",
            "name": 'ГБУЗ "Другая поликлиника" Взрослое отделение',
            "type": "adult",
            "city": "Казань",
        },
    ]

    CLINIC_NAMES = {
        "271": "Поликлиника №1",
        "272": "Стоматология №1",
        "161": "Детская поликлиника",
        "300": "Другая поликлиника",
    }

    def test_adult_sees_adult_and_all_clinics(self):
        """Возраст >= 18 — видны adult и all, не видны child."""
        from keyboards.inline import get_clinic_selection

        mk = get_clinic_selection(
            p_id="p1",
            bday_str="1990-01-01",  # ~36 лет
            clinics_data=self.CLINICS_DATA,
            clinic_names=self.CLINIC_NAMES,
        )
        buttons = _extract_buttons(mk)
        callbacks = [b[1] for b in buttons]
        assert "sel_c_p1_271_all" in callbacks  # adult — видна
        assert "sel_c_p1_272_all" in callbacks  # all — видна
        assert "sel_c_p1_300_all" in callbacks  # adult — видна
        assert "sel_c_p1_161_all" not in callbacks  # child — не видна

    def test_child_sees_child_and_all_clinics(self):
        """Возраст < 18 — видны child и all, не видны adult."""
        from keyboards.inline import get_clinic_selection

        mk = get_clinic_selection(
            p_id="p1",
            bday_str="2020-01-01",  # ~6 лет
            clinics_data=self.CLINICS_DATA,
            clinic_names=self.CLINIC_NAMES,
        )
        buttons = _extract_buttons(mk)
        callbacks = [b[1] for b in buttons]
        assert "sel_c_p1_161_all" in callbacks  # child — видна
        assert "sel_c_p1_272_all" in callbacks  # all — видна
        assert "sel_c_p1_271_all" not in callbacks  # adult — не видна
        assert "sel_c_p1_300_all" not in callbacks  # adult — не видна

    def test_city_filter(self):
        from keyboards.inline import get_clinic_selection

        mk = get_clinic_selection(
            p_id="p1",
            bday_str="1990-01-01",
            selected_city="Казань",
            clinics_data=self.CLINICS_DATA,
            clinic_names=self.CLINIC_NAMES,
        )
        buttons = _extract_buttons(mk)
        callbacks = [b[1] for b in buttons]
        # Только клиники Казани (300 — adult, видна для взрослого)
        assert "sel_c_p1_300_all" in callbacks
        assert "sel_c_p1_271_all" not in callbacks
        assert "sel_c_p1_272_all" not in callbacks

    def test_monitoring_counts(self):
        from keyboards.inline import get_clinic_selection

        monitoring = {
            "p1": {
                "d1": {"clinic_id": "271"},
                "d2": {"clinic_id": "271"},
                "d3": {"clinic_id": "300"},
            }
        }
        mk = get_clinic_selection(
            p_id="p1",
            bday_str="1990-01-01",
            monitoring=monitoring,
            clinics_data=self.CLINICS_DATA,
            clinic_names=self.CLINIC_NAMES,
        )
        buttons = _extract_buttons(mk)
        # 271: "Поликлиника №1 (2)"
        assert ("Поликлиника №1 (2)", "sel_c_p1_271_all") in buttons
        assert ("Другая поликлиника (1)", "sel_c_p1_300_all") in buttons
        # 272: без мониторинга
        assert ("Стоматология №1", "sel_c_p1_272_all") in buttons

    def test_navigation_buttons(self):
        from keyboards.inline import get_clinic_selection

        mk = get_clinic_selection(
            p_id="p1",
            bday_str="1990-01-01",
            clinics_data=self.CLINICS_DATA,
            clinic_names=self.CLINIC_NAMES,
        )
        buttons = _extract_buttons(mk)
        assert ("⬅️ К выбору города", "back_to_cities_p1") in buttons
        assert ("⬅️ Назад к списку", "back_to_main") in buttons

    def test_stop_patient_button_when_monitoring(self):
        from keyboards.inline import get_clinic_selection

        monitoring = {"p1": {"d1": {"clinic_id": "271"}}}
        mk = get_clinic_selection(
            p_id="p1",
            bday_str="1990-01-01",
            monitoring=monitoring,
            clinics_data=self.CLINICS_DATA,
            clinic_names=self.CLINIC_NAMES,
        )
        buttons = _extract_buttons(mk)
        assert (
            "🛑 Сбросить мониторинг этого пациента",
            "stop_patient_p1_clinic_all",
        ) in buttons

    def test_no_stop_button_when_no_monitoring(self):
        from keyboards.inline import get_clinic_selection

        mk = get_clinic_selection(
            p_id="p1",
            bday_str="1990-01-01",
            clinics_data=self.CLINICS_DATA,
            clinic_names=self.CLINIC_NAMES,
        )
        buttons = _extract_buttons(mk)
        assert (
            "🛑 Сбросить мониторинг этого пациента",
            "stop_patient_p1_clinic_all",
        ) not in buttons

    def test_city_idx_passed_to_callback(self):
        from keyboards.inline import get_clinic_selection

        monitoring = {"p1": {"d1": {"clinic_id": "271"}}}
        mk = get_clinic_selection(
            p_id="p1",
            bday_str="1990-01-01",
            clinics_data=self.CLINICS_DATA,
            clinic_names=self.CLINIC_NAMES,
            city_idx="3",
            monitoring=monitoring,
        )
        buttons = _extract_buttons(mk)
        # callback содержит city_idx
        assert ("sel_c_p1_271_3") in [b[1] for b in buttons]
        # Стоп тоже содержит city_idx
        assert ("stop_patient_p1_clinic_3") in [b[1] for b in buttons]
