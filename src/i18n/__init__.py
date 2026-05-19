"""
Модуль интернационализации (i18n) на базе gettext.

Предоставляет глобальные функции _() и _n() для перевода строк,
а также load_json_data() для загрузки языковых JSON-словарей.

Использование:
    from src.i18n import _, _n, load_json_data

    text = _("enter-full-name")
    text = _("clinic-prefix").format(city="Москва")
    text = _n("slots-count", "slots-count", count).format(count=count)
    data = load_json_data("specialty_aliases.json")
"""

import json
import os
from gettext import GNUTranslations, NullTranslations, translation
from typing import cast

# Текущий язык (устанавливается при старте)
_current_lang: str = "ru"

# Gettext-обёртки (устанавливаются через setup_i18n)
_translations_bot: "GNUTranslations | NullTranslations" = NullTranslations()
_translations_data: "GNUTranslations | NullTranslations" = NullTranslations()


def setup_i18n(lang: str) -> None:
    """
    Инициализирует gettext для указанного языка.

    Загружает два домена: 'bot' (пользовательские сообщения) и 'data'
    (форматные строки, дни недели). Если .mo файл не найден — используется
    NullTranslations, который возвращает msgid как есть.

    Если запрошенный язык не русский — добавляет русский как fallback.
    """
    global _current_lang, _translations_bot, _translations_data
    _current_lang = lang

    # Определяем путь к директории locales
    locales_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "locales"
    )

    # Домен bot
    t_bot: GNUTranslations | NullTranslations
    try:
        t_bot = translation(
            "bot",
            localedir=locales_dir,
            languages=[lang],
            fallback=False,
        )
    except FileNotFoundError:
        t_bot = NullTranslations()

    # Добавляем fallback на русский для домена bot
    if lang != "ru":
        try:
            ru_bot = translation(
                "bot",
                localedir=locales_dir,
                languages=["ru"],
                fallback=True,
            )
            t_bot.add_fallback(ru_bot)
        except FileNotFoundError:
            pass

    _translations_bot = t_bot

    # Домен data
    t_data: GNUTranslations | NullTranslations
    try:
        t_data = translation(
            "data",
            localedir=locales_dir,
            languages=[lang],
            fallback=False,
        )
    except FileNotFoundError:
        t_data = NullTranslations()

    # Добавляем fallback на русский для домена data
    if lang != "ru":
        try:
            ru_data = translation(
                "data",
                localedir=locales_dir,
                languages=["ru"],
                fallback=True,
            )
            t_data.add_fallback(ru_data)
        except FileNotFoundError:
            pass

    _translations_data = t_data


def _(msgid: str) -> str:
    """
    Возвращает перевод строки из домена 'bot'.

    Если перевод не найден — возвращает msgid как есть.
    Это основная функция для пользовательских сообщений.
    """
    return _translations_bot.gettext(msgid)


def _n(msgid1: str, msgid2: str, n: int) -> str:
    """
    Возвращает перевод с учётом плюрализации из домена 'bot'.

    msgid1 — форма для единственного числа (или msgid).
    msgid2 — форма для множественного числа (или msgid).
    n — количество, определяющее форму.

    Пример:
        text = _n("slots-count", "slots-count", count).format(count=count)
    """
    return _translations_bot.ngettext(msgid1, msgid2, n)


def _data(msgid: str) -> str:
    """
    Возвращает перевод строки из домена 'data'.

    Используется для дней недели, меток типов данных и т.п.
    """
    return _translations_data.gettext(msgid)


def load_json_data(filename: str, lang: str | None = None) -> dict[str, str]:
    """
    Загружает JSON-файл данных для указанного языка (или текущего).

    Пытается загрузить locales/{lang}/data/{filename}.
    Если файл не найден — fallback на locales/ru/data/{filename}.

    Args:
        filename: Имя JSON-файла (например, "specialty_aliases.json").
        lang: Язык (по умолчанию _current_lang).

    Returns:
        dict: Загруженные данные или пустой dict при ошибке.
    """
    target_lang = lang or _current_lang
    locales_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "locales"
    )

    # Пробуем запрошенный язык
    path = os.path.join(locales_dir, target_lang, "data", filename)
    try:
        with open(path, encoding="utf-8") as f:
            return cast(dict[str, str], json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    # Fallback на русский
    if target_lang != "ru":
        ru_path = os.path.join(locales_dir, "ru", "data", filename)
        try:
            with open(ru_path, encoding="utf-8") as f:
                return cast(dict[str, str], json.load(f))
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    return {}
