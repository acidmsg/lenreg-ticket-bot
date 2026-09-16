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
import struct
from gettext import GNUTranslations, NullTranslations, find, translation
from typing import Final, cast

from loguru import logger

# Язык по умолчанию; он же fallback для остальных языков
DEFAULT_LANGUAGE: Final = "ru"

# Имя директории с каталогами локалей в корне проекта
LOCALES_DIRNAME: Final = "locales"

# Текущий язык (устанавливается при старте)
_current_lang: str = DEFAULT_LANGUAGE

# Gettext-обёртки (устанавливаются через setup_i18n)
_translations_bot: "GNUTranslations | NullTranslations" = NullTranslations()
_translations_data: "GNUTranslations | NullTranslations" = NullTranslations()


def _locales_dir() -> str:
    """Возвращает путь к директории локалей в корне проекта."""
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        LOCALES_DIRNAME,
    )


def _load_domain(
    domain: str, lang: str, locales_dir: str
) -> GNUTranslations | NullTranslations:
    """
    Загружает каталог домена и логирует результат загрузки.

    Успешная загрузка фиксируется на уровне INFO, отсутствие каталога `.mo` —
    на уровне WARNING (бот продолжает работу на msgid), нечитаемый `.mo` —
    на уровне ERROR. Ошибки не замалчиваются.

    Args:
        domain: Имя домена каталога ('bot' или 'data').
        lang: Код языка (например, 'ru').
        locales_dir: Абсолютный путь к директории локалей.

    Returns:
        Загруженный каталог либо NullTranslations, если каталог недоступен.
    """
    mo_path = find(domain, locales_dir, languages=[lang])
    if mo_path is None:
        logger.warning(
            f"i18n: каталог .mo не найден — домен={domain}, язык={lang}, "
            f"localedir={locales_dir}; будет возвращён msgid"
        )
        return NullTranslations()

    try:
        catalog = translation(
            domain,
            localedir=locales_dir,
            languages=[lang],
            fallback=False,
        )
    except (OSError, struct.error) as exc:
        logger.error(
            f"i18n: каталог .mo повреждён — домен={domain}, язык={lang}, "
            f"файл={mo_path}, ошибка={exc!r}; будет возвращён msgid"
        )
        return NullTranslations()

    logger.info(f"i18n: домен={domain}, язык={lang}, каталог={mo_path}")
    return catalog


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

    locales_dir = _locales_dir()
    if not os.path.isdir(locales_dir):
        logger.warning(f"i18n: каталог локалей отсутствует — {locales_dir}")

    t_bot = _load_domain("bot", lang, locales_dir)
    if lang != DEFAULT_LANGUAGE:
        t_bot.add_fallback(_load_domain("bot", DEFAULT_LANGUAGE, locales_dir))
        logger.debug(
            f"i18n: домен=bot, язык={lang} — подключён fallback {DEFAULT_LANGUAGE}"
        )
    _translations_bot = t_bot

    t_data = _load_domain("data", lang, locales_dir)
    if lang != DEFAULT_LANGUAGE:
        t_data.add_fallback(_load_domain("data", DEFAULT_LANGUAGE, locales_dir))
        logger.debug(
            f"i18n: домен=data, язык={lang} — подключён fallback {DEFAULT_LANGUAGE}"
        )
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
    locales_dir = _locales_dir()

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
