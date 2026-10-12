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
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from gettext import GNUTranslations, NullTranslations, find, translation
from typing import Final, cast

from loguru import logger

# Язык по умолчанию; он же fallback для остальных языков
DEFAULT_LANGUAGE: Final = "ru"

# Имя директории с каталогами локалей в корне проекта
LOCALES_DIRNAME: Final = "locales"

# Язык по умолчанию (устанавливается setup_i18n)
_current_lang: str = DEFAULT_LANGUAGE

# Поддерживаемые языки (каталоги locales/<code>/LC_MESSAGES)
SUPPORTED_LANGUAGES: Final = ("ru", "en")

# Каталоги по языкам: {lang: (bot, data)}
_catalogs: dict[
    str, tuple[GNUTranslations | NullTranslations, GNUTranslations | NullTranslations]
] = {}

# Язык текущего контекста (contextvars): позволяет собрать сообщение на языке
# получателя, не меняя глобальный язык процесса.
_lang_var: ContextVar[str] = ContextVar("i18n_lang", default=DEFAULT_LANGUAGE)


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


def _available_languages(locales_dir: str) -> list[str]:
    """Языки каталогов locales/, ограниченные SUPPORTED_LANGUAGES (ru, en).

    Поддержаны только русский и английский; любой другой language_code
    сводится к русскому в resolve_language(). Русский всегда присутствует —
    он fallback для остальных.
    """
    return [
        code
        for code in SUPPORTED_LANGUAGES
        if os.path.isdir(os.path.join(locales_dir, code, "LC_MESSAGES"))
    ]


def _load_pair(
    lang: str, locales_dir: str
) -> tuple[GNUTranslations | NullTranslations, GNUTranslations | NullTranslations]:
    """Загружает пару каталогов (bot, data) для языка с fallback на русский."""
    t_bot = _load_domain("bot", lang, locales_dir)
    t_data = _load_domain("data", lang, locales_dir)
    if lang != DEFAULT_LANGUAGE:
        t_bot.add_fallback(_load_domain("bot", DEFAULT_LANGUAGE, locales_dir))
        logger.debug(
            f"i18n: домен=bot, язык={lang} — подключён fallback {DEFAULT_LANGUAGE}"
        )
        t_data.add_fallback(_load_domain("data", DEFAULT_LANGUAGE, locales_dir))
        logger.debug(
            f"i18n: домен=data, язык={lang} — подключён fallback {DEFAULT_LANGUAGE}"
        )
    return t_bot, t_data


def _catalog_for(
    lang: str,
) -> tuple[GNUTranslations | NullTranslations, GNUTranslations | NullTranslations]:
    """Каталог для языка; при отсутствии — русский (или пустой)."""
    if lang in _catalogs:
        return _catalogs[lang]
    return _catalogs.get(DEFAULT_LANGUAGE, (NullTranslations(), NullTranslations()))


def setup_i18n(lang: str) -> None:
    """Загружает каталоги всех доступных языков и задаёт язык по умолчанию.

    Домены: 'bot' (сообщения) и 'data' (форматные строки, дни недели). Язык
    конкретного сообщения выбирается через set_language()/use_language(); по
    умолчанию — аргумент lang (обычно BOT_LANGUAGE).
    """
    global _current_lang
    _current_lang = lang
    _lang_var.set(lang)

    locales_dir = _locales_dir()
    if not os.path.isdir(locales_dir):
        logger.warning(f"i18n: каталог локалей отсутствует — {locales_dir}")

    _catalogs.clear()
    for code in _available_languages(locales_dir):
        _catalogs[code] = _load_pair(code, locales_dir)
    if lang not in _catalogs:
        _catalogs[lang] = _load_pair(lang, locales_dir)
    logger.info(f"i18n: инициализировано, язык={lang}, доступны={sorted(_catalogs)}")


def set_language(lang: str) -> None:
    """Устанавливает язык текущего контекста (без смены глобального)."""
    _lang_var.set(lang)


@contextmanager
def use_language(lang: str) -> Iterator[None]:
    """Контекстный менеджер: язык сообщения на время блока."""
    token = _lang_var.set(lang)
    try:
        yield
    finally:
        _lang_var.reset(token)


def resolve_language(language_code: str | None) -> str:
    """Код языка Telegram -> язык сообщения.

    Русский — для русскоязычных (ru*), английский — для всех остальных
    вариантов (en, de, fr, а также пустой/неизвестный).
    """
    if language_code and language_code.lower().startswith("ru"):
        return "ru"
    return "en"


def _(msgid: str) -> str:
    """
    Возвращает перевод строки из домена 'bot'.

    Если перевод не найден — возвращает msgid как есть.
    Это основная функция для пользовательских сообщений.
    """
    return _catalog_for(_lang_var.get())[0].gettext(msgid)


def _n(msgid1: str, msgid2: str, n: int) -> str:
    """
    Возвращает перевод с учётом плюрализации из домена 'bot'.

    msgid1 — форма для единственного числа (или msgid).
    msgid2 — форма для множественного числа (или msgid).
    n — количество, определяющее форму.

    Пример:
        text = _n("slots-count", "slots-count", count).format(count=count)
    """
    return _catalog_for(_lang_var.get())[0].ngettext(msgid1, msgid2, n)


def _data(msgid: str) -> str:
    """
    Возвращает перевод строки из домена 'data'.

    Используется для дней недели, меток типов данных и т.п.
    """
    return _catalog_for(_lang_var.get())[1].gettext(msgid)


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
