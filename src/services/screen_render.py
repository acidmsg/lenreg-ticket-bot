"""
Чистый рендерер экрана чата (single screen message).

Модуль не выполняет ввода-вывода и не обращается ко времени: всё, что влияет
на результат, приходит аргументами. Благодаря этому рендер покрывается
юнит-тестами без БД и без Telegram, а ``render_hash`` остаётся стабильным.

Клавиатура в этом модуле не собирается: ``web_app``/deep-link кнопку строит
слой ``handlers`` (см. дизайн §10.3).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass

from src.config import settings
from src.i18n import _

# Резерв символов на заголовок, хвост «ещё N событий» и разделители.
_FOOTER_RESERVE = 160
# Минимальный бюджет тела экрана: ниже него отсечение бессмысленно.
_MIN_BODY_BUDGET = 200


@dataclass(frozen=True, slots=True)
class ScreenItem:
    """Один врач в экране: стабильные данные, без ORM/DB-записей.

    ``last_event_label`` — уже готовая относительная метка времени (например,
    «5 минут назад»). Она попадает в текст, но **не** входит в ``render_hash``:
    иначе hash менялся бы от рендера к рендеру без изменения состояния.
    """

    p_id: int
    d_id: int
    patient_name: str
    doctor_name: str
    has_new_events: bool
    lines: tuple[str, ...] = ()
    clinic_name: str = ""
    last_event_label: str = ""


@dataclass(frozen=True, slots=True)
class ScreenLimits:
    """Лимиты рендера; по умолчанию — значения из конфигурации."""

    max_doctors: int = settings.SCREEN_MAX_DOCTORS
    max_lines: int = settings.SCREEN_MAX_LINES
    soft_limit: int = settings.SCREEN_TEXT_SOFT_LIMIT


@dataclass(frozen=True, slots=True)
class RenderedScreen:
    """Результат рендера экрана."""

    text: str
    """Готовый текст сообщения (без разметки, лимит — ``soft_limit``)."""

    render_hash: str
    """SHA-256 канонического состояния: порядок, флаги новизны, строки врачей."""

    items: list[tuple[int, int]]
    """Пары ``(p_id, d_id)`` показанных врачей — для deep-link кнопки."""

    truncated: bool
    """``True``, если часть событий не поместилась в экран."""

    event_count: int
    """Сколько событий (врачей) пришло на вход рендера."""


def render_screen(
    items: Sequence[ScreenItem], *, limits: ScreenLimits | None = None
) -> RenderedScreen:
    """Собирает текст экрана и его стабильный hash.

    Порядок: пациент → новые события сверху → имя врача. Отсечение идёт по
    трём пределам: число врачей, число строк, мягкий лимит символов.
    """
    active = limits or ScreenLimits()
    ordered = _sort_items(items)
    blocks = _build_blocks(ordered, active.max_doctors, active.max_lines)
    blocks = _fit_blocks(blocks, _char_budget(active))
    shown = [item for block in blocks for item, _rows in block[1]]
    dropped = len(ordered) - len(shown)
    return RenderedScreen(
        text=_render_text(blocks, dropped),
        render_hash=_compute_hash(shown, truncated=dropped > 0, total=len(items)),
        items=[(item.p_id, item.d_id) for item in shown],
        truncated=dropped > 0,
        event_count=len(items),
    )


def _sort_items(items: Sequence[ScreenItem]) -> list[ScreenItem]:
    """Сортирует «пациент → наличие новых событий → имя врача»."""
    return sorted(items, key=_sort_key)


def _sort_key(item: ScreenItem) -> tuple[str, int, str]:
    """Ключ сортировки строки врача (новые события — выше)."""
    return (
        item.patient_name.casefold(),
        0 if item.has_new_events else 1,
        item.doctor_name.casefold(),
    )


def _patient_header(patient_name: str) -> str:
    """Заголовок блока пациента."""
    return _("screen-patient-header").format(name=patient_name)


def _item_rows(item: ScreenItem) -> list[str]:
    """Строки одного врача: имя с маркером новизны и строки слотов."""
    marker = _("screen-new-marker") if item.has_new_events else _("screen-old-marker")
    head = f"{marker} {item.doctor_name}"
    if item.clinic_name:
        head = f"{head} ({item.clinic_name})"
    if item.last_event_label:
        head = f"{head} · {item.last_event_label}"
    indent = _("screen-slot-indent")
    return [head, *(f"{indent}{line}" for line in item.lines)]


def _build_blocks(
    ordered: Sequence[ScreenItem], max_doctors: int, max_lines: int
) -> list[tuple[str, list[tuple[ScreenItem, list[str]]]]]:
    """Группирует строки по пациентам, соблюдая лимиты врачей и строк."""
    blocks: list[tuple[str, list[tuple[ScreenItem, list[str]]]]] = []
    rows = 0
    for doctors, item in enumerate(ordered):
        if doctors >= max_doctors:
            break
        new_rows = _item_rows(item)
        if rows + len(new_rows) > max_lines:
            break
        if not blocks or blocks[-1][0] != item.patient_name:
            blocks.append((item.patient_name, []))
        blocks[-1][1].append((item, new_rows))
        rows += len(new_rows)
    return blocks


def _blocks_text_len(
    blocks: list[tuple[str, list[tuple[ScreenItem, list[str]]]]],
) -> int:
    """Оценка длины текста блоков в символах (для отсечения по лимиту)."""
    total = len(_("screen-title"))
    for patient_name, entries in blocks:
        total += len(_patient_header(patient_name)) + 1
        for entry in entries:
            total += sum(len(row) + 1 for row in entry[1])
    return total


def _fit_blocks(
    blocks: list[tuple[str, list[tuple[ScreenItem, list[str]]]]], budget: int
) -> list[tuple[str, list[tuple[ScreenItem, list[str]]]]]:
    """Отбрасывает хвостовые события, пока текст не уложится в бюджет.

    Последний оставшийся блок с единственным врачом не усекается: экран обязан
    сохранить хотя бы одну строку состояния.
    """
    while blocks and _blocks_text_len(blocks) > budget:
        entries = blocks[-1][1]
        if len(blocks) == 1 and len(entries) <= 1:
            break
        if entries:
            entries.pop()
        if not entries:
            blocks.pop()
    return blocks


def _render_text(
    blocks: list[tuple[str, list[tuple[ScreenItem, list[str]]]]], dropped: int
) -> str:
    """Собирает итоговый текст экрана из блоков и хвоста усечения."""
    lines = [_("screen-title")]
    for patient_name, entries in blocks:
        lines.extend(("", _patient_header(patient_name)))
        for entry in entries:
            lines.extend(entry[1])
    if dropped:
        lines.extend(("", _("screen-more-events").format(count=dropped)))
    return "\n".join(lines)


def _char_budget(limits: ScreenLimits) -> int:
    """Бюджет символов на тело экрана: мягкий лимит минус заголовок и хвост."""
    reserve = len(_("screen-title")) + _FOOTER_RESERVE
    return max(limits.soft_limit - reserve, _MIN_BODY_BUDGET)


def _compute_hash(shown: Sequence[ScreenItem], *, truncated: bool, total: int) -> str:
    """SHA-256 канонического состояния экрана.

    В hash входят: порядок показа, пара ``(p_id, d_id)``, имена, флаг новизны,
    строки слотов, клиника, признак усечения и общее число событий.
    Не входят: относительные метки времени (``last_event_label``) — они
    меняются от рендера к рендеру без изменения состояния.
    """
    payload = {
        "items": [
            [
                item.p_id,
                item.d_id,
                item.patient_name,
                item.doctor_name,
                item.has_new_events,
                list(item.lines),
                item.clinic_name,
            ]
            for item in shown
        ],
        "truncated": truncated,
        "event_count": total,
    }
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
