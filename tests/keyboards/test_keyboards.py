"""
Тесты для keyboards/inline.py — T4.
"""

from typing import ClassVar

from src.handlers.callbacks import (
    AddPatient,
    BackToCities,
    BackToClinics,
    BackToMain,
    CancelRegistration,
    CitySelect,
    ClinicSelect,
    DeletePatientAsk,
    DeletePatientConfirm,
    PatientSelect,
    SkipAlias,
    StopAllMonitoring,
    StopClinicMonitoring,
    StopPatientMonitoring,
    ToggleDoctor,
)


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
        from src.keyboards.inline import get_registration_keyboard

        mk = get_registration_keyboard(step="alias")
        buttons = _extract_buttons(mk)
        assert ("Пропустить", SkipAlias().pack()) in buttons
        assert ("❌ Отмена регистрации", CancelRegistration().pack()) in buttons

    def test_fio_step_no_skip_button(self):
        from src.keyboards.inline import get_registration_keyboard

        mk = get_registration_keyboard(step="fio")
        buttons = _extract_buttons(mk)
        assert ("Пропустить", SkipAlias().pack()) not in buttons
        assert ("❌ Отмена регистрации", CancelRegistration().pack()) in buttons

    def test_bday_step_no_skip_button(self):
        from src.keyboards.inline import get_registration_keyboard

        mk = get_registration_keyboard(step="bday")
        buttons = _extract_buttons(mk)
        assert ("Пропустить", SkipAlias().pack()) not in buttons
        assert ("❌ Отмена регистрации", CancelRegistration().pack()) in buttons


# ── T4.2 get_confirm_deletion ─────────────────────────────────────────


class TestConfirmDeletion:
    """Тесты get_confirm_deletion."""

    def test_buttons_present(self):
        from src.keyboards.inline import get_confirm_deletion

        mk = get_confirm_deletion("patient_123")
        buttons = _extract_buttons(mk)
        assert (
            "✅ Да, удалить",
            DeletePatientConfirm(p_id="patient_123").pack(),
        ) in buttons
        assert ("❌ Нет", PatientSelect(p_id="patient_123").pack()) in buttons

    def test_returns_markup(self):
        from src.keyboards.inline import get_confirm_deletion

        mk = get_confirm_deletion("abc")
        rows = _extract_rows(mk)
        assert len(rows) == 1
        assert len(rows[0]) == 2


# ── T4.3 _short_clinic_label ──────────────────────────────────────────


class TestShortClinicLabel:
    """Тесты _short_clinic_label — вспомогательная функция."""

    def test_extracts_after_quote(self):
        from src.keyboards.inline import _short_clinic_label

        name = 'ГБУЗ "Городская поликлиника №1" Детское отделение'
        result = _short_clinic_label(name, 0)
        assert result == "Детское отделение"

    def test_extracts_after_quote_with_count(self):
        from src.keyboards.inline import _short_clinic_label

        name = 'ГБУЗ "Поликлиника №2" Взрослое отделение'
        result = _short_clinic_label(name, 3)
        assert result == "Взрослое отделение (3)"

    def test_no_quote_fallback_short(self):
        from src.keyboards.inline import _short_clinic_label

        name = "Короткое название"
        result = _short_clinic_label(name, 0)
        assert result == "Короткое название"

    def test_no_quote_fallback_long(self):
        from src.keyboards.inline import _short_clinic_label

        name = (
            "Очень длинное название поликлиники "
            "которое превышает пятьдесят символов точно"
        )
        result = _short_clinic_label(name, 0)
        assert result == name[:50] + "..."

    def test_empty_quote_content(self):
        from src.keyboards.inline import _short_clinic_label

        name = 'ГБУЗ ""'
        result = _short_clinic_label(name, 1)
        assert result == 'ГБУЗ "" (1)'


# ── T4.1 get_patient_selection ────────────────────────────────────────


class TestPatientSelection:
    """Тесты get_patient_selection."""

    SAMPLE_PATIENTS: ClassVar[dict] = {
        "p1": {"alias": "Мама", "fio": "Иванова Анна Петровна"},
        "p2": {"alias": None, "fio": "Петров Иван Сидорович"},
        "p3": {"alias": "Сын", "fio": "Сидоров Пётр Александрович"},
    }

    def test_no_patients_only_add_button(self):
        from src.keyboards.inline import get_patient_selection

        mk = get_patient_selection({}, {})
        buttons = _extract_buttons(mk)
        assert len(buttons) == 1
        assert buttons[0] == ("➕ Добавить пациента", AddPatient().pack())

    def test_patients_sorted_by_display_name(self):
        from src.keyboards.inline import get_patient_selection

        mk = get_patient_selection(self.SAMPLE_PATIENTS, {})
        buttons = _extract_buttons(mk)

        assert buttons[0] == ("👤 Мама", PatientSelect(p_id="p1").pack())
        assert buttons[1] == ("🗑", DeletePatientAsk(p_id="p1").pack())
        assert buttons[2] == (
            "👤 Петров Иван Сидорович",
            PatientSelect(p_id="p2").pack(),
        )
        assert buttons[3] == ("🗑", DeletePatientAsk(p_id="p2").pack())
        assert buttons[4] == ("👤 Сын", PatientSelect(p_id="p3").pack())
        assert buttons[5] == ("🗑", DeletePatientAsk(p_id="p3").pack())
        assert buttons[6] == ("➕ Добавить пациента", AddPatient().pack())

    def test_monitoring_count_shown(self):
        from src.keyboards.inline import get_patient_selection

        monitoring: dict[str, dict[str, dict]] = {
            "p1": {"d1": {}, "d2": {}},
            "p3": {"d3": {}},
        }
        mk = get_patient_selection(self.SAMPLE_PATIENTS, monitoring)
        buttons = _extract_buttons(mk)
        assert buttons[0] == ("👤 Мама (2)", PatientSelect(p_id="p1").pack())
        assert buttons[2] == (
            "👤 Петров Иван Сидорович",
            PatientSelect(p_id="p2").pack(),
        )
        assert buttons[4] == ("👤 Сын (1)", PatientSelect(p_id="p3").pack())

    def test_stop_all_button_when_active_monitoring(self):
        from src.keyboards.inline import get_patient_selection

        monitoring: dict[str, dict[str, dict]] = {"p1": {"d1": {}}}
        mk = get_patient_selection(self.SAMPLE_PATIENTS, monitoring)
        buttons = _extract_buttons(mk)
        assert ("🛑 Сбросить весь мониторинг", StopAllMonitoring().pack()) in buttons

    def test_no_stop_all_when_no_monitoring(self):
        from src.keyboards.inline import get_patient_selection

        mk = get_patient_selection(self.SAMPLE_PATIENTS, {})
        buttons = _extract_buttons(mk)
        assert (
            "🛑 Сбросить весь мониторинг",
            StopAllMonitoring().pack(),
        ) not in buttons

    def test_row_structure_patients_in_pairs(self):
        from src.keyboards.inline import get_patient_selection

        mk = get_patient_selection(self.SAMPLE_PATIENTS, {})
        rows = _extract_rows(mk)
        assert len(rows) == 4
        for i in range(3):
            assert len(rows[i]) == 2
        assert len(rows[3]) == 1


# ── T4.5 get_city_selection ───────────────────────────────────────────


class TestCitySelection:
    """Тесты get_city_selection."""

    def test_cities_with_indices(self):
        from src.keyboards.inline import get_city_selection

        mk = get_city_selection(
            p_id="p1",
            cities=["Москва", "Санкт-Петербург", "Казань"],
        )
        buttons = _extract_buttons(mk)
        assert ("📍 Москва", CitySelect(p_id="p1", idx="1").pack()) in buttons
        assert ("📍 Санкт-Петербург", CitySelect(p_id="p1", idx="2").pack()) in buttons
        assert ("📍 Казань", CitySelect(p_id="p1", idx="3").pack()) in buttons
        assert ("🏥 Все", CitySelect(p_id="p1", idx="all").pack()) in buttons
        assert ("⬅️ Назад к списку", BackToMain().pack()) in buttons

    def test_monitoring_counts_per_city(self):
        from src.keyboards.inline import get_city_selection

        monitoring = {
            "p1": {
                "d1": {"clinic_id": "271"},
                "d2": {"clinic_id": "271"},
                "d3": {"clinic_id": "272"},
            }
        }
        from src.database.types import ClinicInfo

        clinics_data: list[ClinicInfo] = [
            {
                "clinic_id": "271",
                "name": "Поликлиника №1",
                "type": "adult",
                "is_active": 1,
                "city": "Москва",
            },
            {
                "clinic_id": "272",
                "name": "Поликлиника №2",
                "type": "child",
                "is_active": 1,
                "city": "Казань",
            },
        ]
        mk = get_city_selection(
            p_id="p1",
            cities=["Москва", "Казань"],
            monitoring=monitoring,
            clinics_data=clinics_data,
        )
        buttons = _extract_buttons(mk)
        assert ("📍 Москва (2)", CitySelect(p_id="p1", idx="1").pack()) in buttons
        assert ("📍 Казань (1)", CitySelect(p_id="p1", idx="2").pack()) in buttons
        assert ("🏥 Все (3)", CitySelect(p_id="p1", idx="all").pack()) in buttons

    def test_stop_patient_button_when_monitoring(self):
        from src.keyboards.inline import get_city_selection

        monitoring = {"p1": {"d1": {"clinic_id": "271"}}}
        from src.database.types import ClinicInfo

        clinics_data: list[ClinicInfo] = [
            {
                "clinic_id": "271",
                "name": "Поликлиника №1",
                "type": "adult",
                "is_active": 1,
                "city": "Москва",
            },
        ]
        mk = get_city_selection(
            p_id="p1",
            cities=["Москва"],
            monitoring=monitoring,
            clinics_data=clinics_data,
        )
        buttons = _extract_buttons(mk)
        assert (
            "🛑 Сбросить мониторинг этого пациента",
            StopPatientMonitoring(p_id="p1", origin="city").pack(),
        ) in buttons

    def test_no_stop_button_when_no_monitoring(self):
        from src.keyboards.inline import get_city_selection

        mk = get_city_selection(p_id="p1", cities=["Москва"])
        buttons = _extract_buttons(mk)
        assert (
            "🛑 Сбросить мониторинг этого пациента",
            StopPatientMonitoring(p_id="p1", origin="city").pack(),
        ) not in buttons

    def test_no_cities_all_button_only(self):
        from src.keyboards.inline import get_city_selection

        mk = get_city_selection(p_id="p1")
        buttons = _extract_buttons(mk)
        assert ("🏥 Все клиники", CitySelect(p_id="p1", idx="all").pack()) in buttons


# ── T4.6 get_doctor_selection ─────────────────────────────────────────


class TestDoctorSelection:
    """Тесты get_doctor_selection."""

    DOCTORS: ClassVar[dict] = {
        "d1": {"name": "Иванов Иван Иванович", "specialty": "Терапия"},
        "d2": {"name": "Петров Пётр Петрович", "specialty": "Хирургия"},
        "d3": {"name": "Сидоров Алексей Борисович", "specialty": "Терапия"},
        "d4": {"name": "Кабинет УЗИ", "specialty": ""},
        "d5": {"name": "Процедурный кабинет", "specialty": ""},
    }

    def test_doctors_sorted_by_specialty_then_name(self):
        from src.keyboards.inline import get_doctor_selection

        mk = get_doctor_selection("p1", "271", self.DOCTORS, {})
        buttons = _extract_buttons(mk)
        assert buttons[0][0] == "▫️ [Терапевт] Иванов И. И."
        assert buttons[1][0] == "▫️ [Терапевт] Сидоров А. Б."
        assert buttons[2][0] == "▫️ [Хирург] Петров П. П."
        assert buttons[3][0] == "▫️ Кабинет УЗИ"
        assert buttons[4][0] == "▫️ Процедурный кабинет"

    def test_monitored_doctor_has_checkmark(self):
        from src.keyboards.inline import get_doctor_selection

        monitored = {"d1": {"name": "Иванов И.И.", "clinic_id": "271"}}
        mk = get_doctor_selection("p1", "271", self.DOCTORS, monitored)
        buttons = _extract_buttons(mk)
        assert buttons[0][0] == "✅ [Терапевт] Иванов И. И."

    def test_callback_data_format(self):
        from src.keyboards.inline import get_doctor_selection

        mk = get_doctor_selection("p_abc", "300", self.DOCTORS, {})
        buttons = _extract_buttons(mk)
        assert (
            buttons[0][1]
            == ToggleDoctor(p_id="p_abc", clinic_id="300", d_id="d1").pack()
        )

    def test_navigation_buttons(self):
        from src.keyboards.inline import get_doctor_selection

        mk = get_doctor_selection("p1", "271", self.DOCTORS, {}, city_idx="2")
        buttons = _extract_buttons(mk)
        assert (
            "⬅️ К выбору клиники",
            BackToClinics(p_id="p1", city_idx="2").pack(),
        ) in buttons
        assert ("⬅️ Назад к списку", BackToMain().pack()) in buttons

    def test_stop_clinic_button_when_monitoring_in_clinic(self):
        from src.keyboards.inline import get_doctor_selection

        monitored = {
            "d1": {"name": "X", "clinic_id": "271"},
            "d9": {"name": "Y", "clinic_id": "999"},
        }
        mk = get_doctor_selection("p1", "271", self.DOCTORS, monitored)
        buttons = _extract_buttons(mk)
        assert (
            "🛑 Сбросить мониторинг этой клиники",
            StopClinicMonitoring(p_id="p1", clinic_id="271").pack(),
        ) in buttons

    def test_no_stop_clinic_when_no_monitoring_in_that_clinic(self):
        from src.keyboards.inline import get_doctor_selection

        monitored = {"d9": {"name": "Y", "clinic_id": "999"}}
        mk = get_doctor_selection("p1", "271", self.DOCTORS, monitored)
        buttons = _extract_buttons(mk)
        assert (
            "🛑 Сбросить мониторинг этой клиники",
            StopClinicMonitoring(p_id="p1", clinic_id="271").pack(),
        ) not in buttons

    def test_dental_clinic_filters_child_specialties(self):
        from src.keyboards.inline import get_doctor_selection

        doctors = {
            "d1": {
                "name": "Иванов Иван Иванович",
                "specialty": "Стоматология общей практики",
            },
            "d2": {"name": "Петров Пётр Петрович", "specialty": "Детская стоматология"},
            "d3": {"name": "Сидоров Алексей Борисович", "specialty": "Ортодонтия"},
        }
        mk = get_doctor_selection("p1", "272", doctors, {}, bday_str="2020-01-01")
        buttons = _extract_buttons(mk)
        tgl_prefix = (
            ToggleDoctor(p_id="p1", clinic_id="272", d_id="").pack().rsplit(":", 1)[0]
            + ":"
        )
        doctor_texts = [b[0] for b in buttons if b[1].startswith(tgl_prefix)]
        assert len(doctor_texts) == 1
        assert "Дет. стоматолог" in doctor_texts[0]

    def test_dental_clinic_filters_adult_specialties(self):
        from src.keyboards.inline import get_doctor_selection

        doctors = {
            "d1": {
                "name": "Иванов Иван Иванович",
                "specialty": "Стоматология общей практики",
            },
            "d2": {"name": "Петров Пётр Петрович", "specialty": "Детская стоматология"},
        }
        mk = get_doctor_selection("p1", "272", doctors, {}, bday_str="1990-01-01")
        buttons = _extract_buttons(mk)
        tgl_prefix = (
            ToggleDoctor(p_id="p1", clinic_id="272", d_id="").pack().rsplit(":", 1)[0]
            + ":"
        )
        doctor_texts = [b[0] for b in buttons if b[1].startswith(tgl_prefix)]
        assert len(doctor_texts) == 1
        assert "Стоматолог" in doctor_texts[0]


# ── T4.7 get_clinic_selection ─────────────────────────────────────────


class TestClinicSelection:
    """Тесты get_clinic_selection."""

    CLINICS_DATA: ClassVar[list] = [
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

    CLINIC_NAMES: ClassVar[dict] = {
        "271": "Поликлиника №1",
        "272": "Стоматология №1",
        "161": "Детская поликлиника",
        "300": "Другая поликлиника",
    }

    def _sel_c(self, p_id: str, clinic_id: str, city_idx: str = "all") -> str:
        return ClinicSelect(p_id=p_id, clinic_id=clinic_id, city_idx=city_idx).pack()

    def test_adult_sees_adult_and_all_clinics(self):
        from src.keyboards.inline import get_clinic_selection

        mk = get_clinic_selection(
            p_id="p1",
            bday_str="1990-01-01",
            clinics_data=self.CLINICS_DATA,
            clinic_names=self.CLINIC_NAMES,
        )
        buttons = _extract_buttons(mk)
        callbacks = [b[1] for b in buttons]
        assert self._sel_c("p1", "271") in callbacks
        assert self._sel_c("p1", "272") in callbacks
        assert self._sel_c("p1", "300") in callbacks
        assert self._sel_c("p1", "161") not in callbacks

    def test_child_sees_child_and_all_clinics(self):
        from src.keyboards.inline import get_clinic_selection

        mk = get_clinic_selection(
            p_id="p1",
            bday_str="2020-01-01",
            clinics_data=self.CLINICS_DATA,
            clinic_names=self.CLINIC_NAMES,
        )
        buttons = _extract_buttons(mk)
        callbacks = [b[1] for b in buttons]
        assert self._sel_c("p1", "161") in callbacks
        assert self._sel_c("p1", "272") in callbacks
        assert self._sel_c("p1", "271") not in callbacks
        assert self._sel_c("p1", "300") not in callbacks

    def test_city_filter(self):
        from src.keyboards.inline import get_clinic_selection

        mk = get_clinic_selection(
            p_id="p1",
            bday_str="1990-01-01",
            selected_city="Казань",
            clinics_data=self.CLINICS_DATA,
            clinic_names=self.CLINIC_NAMES,
        )
        buttons = _extract_buttons(mk)
        callbacks = [b[1] for b in buttons]
        assert self._sel_c("p1", "300") in callbacks
        assert self._sel_c("p1", "271") not in callbacks
        assert self._sel_c("p1", "272") not in callbacks

    def test_monitoring_counts(self):
        from src.keyboards.inline import get_clinic_selection

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
        assert ("Поликлиника №1 (2)", self._sel_c("p1", "271")) in buttons
        assert ("Другая поликлиника (1)", self._sel_c("p1", "300")) in buttons
        assert ("Стоматология №1", self._sel_c("p1", "272")) in buttons

    def test_navigation_buttons(self):
        from src.keyboards.inline import get_clinic_selection

        mk = get_clinic_selection(
            p_id="p1",
            bday_str="1990-01-01",
            clinics_data=self.CLINICS_DATA,
            clinic_names=self.CLINIC_NAMES,
        )
        buttons = _extract_buttons(mk)
        assert ("⬅️ К выбору города", BackToCities(p_id="p1").pack()) in buttons
        assert ("⬅️ Назад к списку", BackToMain().pack()) in buttons

    def test_stop_patient_button_when_monitoring(self):
        from src.keyboards.inline import get_clinic_selection

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
            StopPatientMonitoring(p_id="p1", origin="clinic", city_idx="all").pack(),
        ) in buttons

    def test_no_stop_button_when_no_monitoring(self):
        from src.keyboards.inline import get_clinic_selection

        mk = get_clinic_selection(
            p_id="p1",
            bday_str="1990-01-01",
            clinics_data=self.CLINICS_DATA,
            clinic_names=self.CLINIC_NAMES,
        )
        buttons = _extract_buttons(mk)
        assert (
            "🛑 Сбросить мониторинг этого пациента",
            StopPatientMonitoring(p_id="p1", origin="clinic", city_idx="all").pack(),
        ) not in buttons

    def test_city_idx_passed_to_callback(self):
        from src.keyboards.inline import get_clinic_selection

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
        assert self._sel_c("p1", "271", "3") in [b[1] for b in buttons]
        assert (
            StopPatientMonitoring(p_id="p1", origin="clinic", city_idx="3").pack()
            in [b[1] for b in buttons]
        )
