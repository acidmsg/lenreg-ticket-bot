"""
Вспомогательные функции для форматирования отображаемых данных.
"""

import re
from collections import defaultdict
from datetime import datetime, time

from loguru import logger

from src.i18n import _data

# ── Кэш псевдонимов специальностей, загружаемый из БД ────────
_db_specialty_aliases: dict[str, str] = {}

# ── Дни недели (сокращения для отображения) ─────────────────────
_WEEKDAYS = [
    _data("weekday-mon"),
    _data("weekday-tue"),
    _data("weekday-wed"),
    _data("weekday-thu"),
    _data("weekday-fri"),
    _data("weekday-sat"),
    _data("weekday-sun"),
]


async def load_specialty_aliases_from_db(db):
    """Загружает псевдонимы специальностей из БД в кэш."""
    global _db_specialty_aliases
    try:
        aliases = await db.get_all_specialty_aliases()
        if aliases:
            _db_specialty_aliases = aliases
    except Exception as e:
        logger.warning("Не удалось загрузить псевдонимы из БД: {}", e)


def is_child(bday_str: str) -> bool:
    """
    Определяет, является ли пациент ребёнком (< 18 лет).
    Принимает дату рождения в формате '%Y-%m-%d'.
    При ошибке парсинга или отсутствии даты считает взрослым.
    """
    try:
        bday = datetime.strptime(bday_str, "%Y-%m-%d")
        age = (datetime.now() - bday).days // 365
        return age < 18
    except (ValueError, TypeError):
        return False


# ── Маппинг специальностей: полное название → короткое ──────────
SPECIALTY_ALIASES = {
    "Оториноларингология": "ЛОР",
    "Офтальмология": "Окулист",
    "Акушерство и гинекология": "Гинеколог",
    "Акушерство-гинекология": "Гинеколог",
    "Детская кардиология": "Дет. кардиолог",
    "Детская хирургия": "Дет. хирург",
    "Детская стоматология": "Дет. стоматолог",
    "Детская эндокринология": "Дет. эндокринолог",
    "Инфекционные болезни": "Инфекционист",
    "Клиническая лабораторная диагностика": "Лаб. диагностика",
    "Лечебная физкультура и спортивная медицина": "ЛФК",
    "Мануальная терапия": "Мануальщик",
    "Медицинская реабилитация": "Реабилитолог",
    "Неврология": "Невролог",
    "Нейрохирургия": "Нейрохирург",
    "Общая врачебная практика (семейная медицина)": "Семейный врач",
    "Онкология": "Онколог",
    "Ортодонтия": "Ортодонт",
    "Остеопатия": "Остеопат",
    "Педиатрия": "Педиатр",
    "Психиатрия": "Психиатр",
    "Психиатрия-наркология": "Психиатр-нарколог",
    "Пульмонология": "Пульмонолог",
    "Ревматология": "Ревматолог",
    "Рентгенология": "Рентгенолог",
    "Рентгенэндоваскулярные диагностика и лечение": "Рентгенхирург",
    "Рефлексотерапия": "Рефлексотерапевт",
    "Сердечно-сосудистая хирургия": "Сосуд. хирург",
    "Скорая медицинская помощь": "Скорая помощь",
    "Стоматология общей практики": "Стоматолог",
    "Стоматология ортопедическая": "Стоматолог-ортопед",
    "Стоматология детская": "Дет. стоматология",
    "Стоматология профилактическая": "Стоматология проф.",
    "Стоматология (средний медперсонал)": "Ср. медперсонал",
    "Стоматология терапевтическая": "Стоматолог-терапевт",
    "Стоматология хирургическая": "Стоматолог-хирург",
    "Судебно-медицинская экспертиза": "Судмедэксперт",
    "Терапия": "Терапевт",
    "Травматология и ортопедия": "Травматолог",
    "Ультразвуковая диагностика": "УЗИ",
    "Урология": "Уролог",
    "Физиотерапия": "Физиотерапевт",
    "Фтизиатрия": "Фтизиатр",
    "Функциональная диагностика": "Функц. диагностика",
    "Хирургия": "Хирург",
    "Челюстно-лицевая хирургия": "Челюст.-лиц. хирург",
    "Эндокринология": "Эндокринолог",
    "Эндоскопия": "Эндоскопист",
    "Аллергология и иммунология": "Аллерголог",
    "Ангиология": "Ангиолог",
    "Гастроэнтерология": "Гастроэнтеролог",
    "Гематология": "Гематолог",
    "Гериатрия": "Гериатр",
    "Дерматовенерология": "Дерматолог",
    "Диетология": "Диетолог",
    "Кардиология": "Кардиолог",
    "Колопроктология": "Проктолог",
    "Нефрология": "Нефролог",
}


def is_cabinet(name: str) -> bool:
    """
    Определяет, является ли запись 'кабинетом' (не врачом-человеком).

    Критерий: если name состоит из трёх слов, каждое из которых начинается
    с заглавной буквы и содержит только русские буквы — это ФИО (человек).
    Иначе — кабинет / процедура.
    """
    if not name:
        return True
    words = name.strip().split()
    if len(words) == 3:
        # Проверяем, похоже ли на ФИО Иванов Иван Иванович
        russian_word = re.compile(r"^[А-ЯЁ][а-яё]+$")
        if all(russian_word.match(w) for w in words):
            return False  # это человек
    return True  # это кабинет


def shorten_fio(name: str) -> str:
    """
    Сокращает ФИО до вида: "Бранчель Н. П."
    Если имя не похоже на ФИО — возвращает как есть.
    """
    parts = name.strip().split()
    if len(parts) == 3:
        surname = parts[0]
        first = parts[1][0] if parts[1] else ""
        middle = parts[2][0] if parts[2] else ""
        return f"{surname} {first}. {middle}."
    return name


def shorten_specialty(specialty: str) -> str:
    """
    Возвращает короткий псевдоним специальности, если он есть в словаре,
    иначе — исходное название.
    Сначала проверяет кэш из БД, затем хардкод SPECIALTY_ALIASES.
    """
    if not specialty:
        return ""
    # Сначала проверяем кэш из БД (если загружен и не пуст)
    if _db_specialty_aliases:
        return _db_specialty_aliases.get(specialty, specialty)
    # Fallback на хардкод
    return SPECIALTY_ALIASES.get(specialty, specialty)


def extract_msg_id(value) -> int | None:
    """
    Извлекает message_id из значения last_messages.
    Принимает как старый формат (int), так и новый (dict с msg_id/ts).
    """
    if isinstance(value, dict):
        return value.get("msg_id")
    if isinstance(value, int):
        return value
    return None


# ── Форматирование списка номерков ────────────────────────────────


def _parse_slot(slot: str) -> tuple[datetime, time]:
    """Парсит строку слота 'YYYY-MM-DD в HH:MM' в (date, time).

    Игнорирует префикс '[NEW] ' если присутствует (добавляется _classify_slot_change).
    """
    try:
        # Отбрасываем префикс [NEW] если есть
        clean = slot[6:] if slot.startswith("[NEW] ") else slot
        parts = clean.split(" в ")
        dt = datetime.strptime(parts[0].strip(), "%Y-%m-%d")
        t = time.fromisoformat(parts[1].strip())
        return dt, t
    except (ValueError, IndexError):
        return datetime(2000, 1, 1), time(0, 0)


def _slot_sort_key(slot: str) -> tuple[datetime, time]:
    """Ключ сортировки для слота по дате и времени."""
    return _parse_slot(slot)


def format_slots(
    slots: list[str],
    detail_threshold: int = 10,
    compact_threshold: int = 15,
) -> list[str]:
    """
    Форматирует список слотов 'YYYY-MM-DD в HH:MM' в читаемый вид.

    Поддерживает префикс '[NEW] ' для отметки новых слотов (отображается как 🆕).

    Если всего слотов <= compact_threshold — детальный формат (Вариант M):
        📆 Пн 19.05 — 6 шт.
           ─ 09:00, 🆕 09:15, 10:20

    Если > compact_threshold — компактный формат:
        📆 Пн 19.05 — 6 шт. с 09:00 до 10:50

    Слоты на конкретную дату длиннее detail_threshold — также диапазон.

    Возвращает список строк (без начальных/конечных переносов).
    """
    if not slots:
        return []

    # Очищаем префиксы [NEW] и отслеживаем новые слоты
    _new_prefix = "[NEW] "
    cleaned: list[str] = []
    new_set: set[str] = set()  # чистые строки, которые были промаркированы как NEW
    for s in slots:
        if s.startswith(_new_prefix):
            clean = s[len(_new_prefix) :]
            cleaned.append(clean)
            new_set.add(clean)
        else:
            cleaned.append(s)

    # Сортируем слоты по дате и времени
    sorted_slots = sorted(cleaned, key=_slot_sort_key)

    # Группируем по дате, сохраняя флаг is_new для каждого времени
    by_date: dict[datetime, list[tuple[time, bool]]] = defaultdict(list)
    for slot in sorted_slots:
        dt, t = _parse_slot(slot)
        by_date[dt].append((t, slot in new_set))

    total = sum(len(times) for times in by_date.values())
    lines: list[str] = []

    for date_obj in sorted(by_date.keys()):
        time_entries = by_date[date_obj]  # list of (time, is_new)
        times = [entry[0] for entry in time_entries]
        cnt = len(times)
        wd = _WEEKDAYS[date_obj.weekday()]
        date_fmt = date_obj.strftime("%d.%m")

        if total <= compact_threshold and cnt <= detail_threshold:
            # Детальный формат — показываем времена, новые помечаем 🆕
            lines.append(f"📆 {wd} {date_fmt} — {cnt} шт.")
            time_strs: list[str] = []
            for t, is_new in time_entries:
                ts = f"{t:%H:%M}"
                if is_new:
                    ts = f"🆕 {ts}"
                time_strs.append(ts)
            chunk_size = 6
            for i in range(0, len(time_strs), chunk_size):
                chunk = time_strs[i : i + chunk_size]
                prefix = "   ─ " if i == 0 else "     "
                lines.append(prefix + ", ".join(chunk))
        else:
            # Компактный формат (диапазон) — 🆕 если есть хотя бы один новый
            t_min = times[0]
            t_max = times[-1]
            new_count = sum(1 for _, is_new in time_entries if is_new)
            new_mark = " 🆕" if new_count > 0 else ""
            if cnt == 1:
                lines.append(f"📆 {wd} {date_fmt} — 1 шт. ({t_min:%H:%M}){new_mark}")
            else:
                lines.append(
                    f"📆 {wd} {date_fmt} — {cnt} шт."
                    f" с {t_min:%H:%M} до {t_max:%H:%M}{new_mark}"
                )

    return lines


def format_notification_text(
    p_label: str,
    d_name_display: str,
    spec_text: str,
    header_or_status: str,
    slots_display: str,
    link: str = "",
) -> str:
    """Собирает полный текст уведомления о номерках.

    Принимает уже отформатированные компоненты и возвращает итоговую строку
    с единообразной структурой: специальность, врач, пациент, статус, слоты, ссылка.
    """
    return (
        f"{spec_text}🧑‍⚕️ {d_name_display}\n"
        f"👤 {p_label}\n{header_or_status}\n\n{slots_display}{link}"
    )
