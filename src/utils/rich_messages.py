"""Сборка rich-сообщений (Bot API 10.3) для экранов бота.

Модуль формирует :class:`InputRichMessage` из блоков для главного экрана
«📋 Ваши пациенты». Изображение-шапка прикрепляется блоком
``InputRichBlockPhoto`` — файл уходит через multipart (``attach://``),
поэтому отдельный список ``media`` не требуется (он служит только для
``tg://``-ссылок в ``markdown``/``html``).
"""

from pathlib import Path
from typing import Any

from aiogram.types import (
    FSInputFile,
    InputMediaPhoto,
    InputRichBlockDetails,
    InputRichBlockDivider,
    InputRichBlockList,
    InputRichBlockListItem,
    InputRichBlockParagraph,
    InputRichBlockPhoto,
    InputRichBlockSectionHeading,
    InputRichMessage,
)

from src.i18n import _
from src.utils.helpers import shorten_fio, shorten_specialty


def _patient_display_name(p_info: dict[str, Any]) -> str:
    """Имя пациента для отображения: псевдоним, иначе ФИО, иначе fallback."""
    name = p_info.get("alias") or p_info.get("fio")
    return str(name) if name else _("patient-fallback-name")


def _doctor_label(d_info: Any) -> str:
    """Строка врача «🧑‍⚕️ ФИО — специальность» для элемента списка."""
    if isinstance(d_info, dict):
        doctor_name = shorten_fio(d_info.get("name", _("doctor-fallback-name")))
        specialty = shorten_specialty(d_info.get("specialty", ""))
    else:
        doctor_name = str(d_info)
        specialty = ""
    if specialty:
        return _("monitoring-doctor-line").format(name=doctor_name, specialty=specialty)
    return _("monitoring-doctor-line-no-specialty").format(name=doctor_name)


def _monitoring_details(p_name: str, doctors: dict[str, Any]) -> InputRichBlockDetails:
    """Блок ``<details>`` пациента с раскрытым списком его врачей."""
    sorted_doctors = sorted(
        doctors.items(),
        key=lambda x: x[1].get("name", "") if isinstance(x[1], dict) else str(x[1]),
    )
    items = [
        InputRichBlockListItem(
            blocks=[InputRichBlockParagraph(text=_doctor_label(d_info))]
        )
        for _d_id, d_info in sorted_doctors
    ]
    return InputRichBlockDetails(
        summary=_("monitoring-patient-summary").format(name=p_name, count=len(doctors)),
        blocks=[InputRichBlockList(items=items)],
        is_open=False,
    )


def build_main_screen_rich(
    patients: dict[str, Any],
    monitoring: dict[str, dict[str, Any]],
    photo_path: Path | None = None,
) -> InputRichMessage:
    """Собирает rich-сообщение главного экрана «📋 Ваши пациенты».

    Args:
        patients: Пациенты пользователя ``{p_id: PatientInfo}``.
        monitoring: Мониторинг ``{p_id: {d_id: DoctorInfo}}``.
        photo_path: Путь к изображению-шапке; если задан — добавляется первым
            блоком. ``None`` — экран отправляется без картинки.

    Returns:
        ``InputRichMessage`` с заголовком, подзаголовком, разделителем и
        секцией активного мониторинга (при его наличии).
    """
    blocks: list[Any] = []
    if photo_path is not None:
        blocks.append(
            InputRichBlockPhoto(photo=InputMediaPhoto(media=FSInputFile(photo_path)))
        )

    if not patients:
        blocks.append(InputRichBlockParagraph(text=_("no-patients-welcome")))
        return InputRichMessage(blocks=blocks)

    blocks.append(InputRichBlockSectionHeading(text=_("main-screen-heading"), size=2))
    blocks.append(InputRichBlockParagraph(text=_("main-screen-subtitle")))

    patient_blocks: list[Any] = []
    for p_id, doctors in monitoring.items():
        raw_patient = patients.get(p_id)
        if raw_patient is None:
            continue
        p_name = _patient_display_name(raw_patient)
        if not doctors:
            patient_blocks.append(
                InputRichBlockParagraph(
                    text=_("monitoring-patient-without-doctors").format(name=p_name)
                )
            )
            continue
        patient_blocks.append(_monitoring_details(p_name, doctors))

    if patient_blocks:
        blocks.append(InputRichBlockDivider())
        blocks.append(
            InputRichBlockSectionHeading(text=_("monitoring-summary-heading"), size=4)
        )
        blocks.extend(patient_blocks)

    return InputRichMessage(blocks=blocks)
