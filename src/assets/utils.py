"""Хелперы для работы с изображениями-заголовками сообщений.

Используются для отправки изображений через send_photo() Telegram Bot API.
Правила именования файлов: см. src/assets/README.md.
"""

from pathlib import Path

# Директория с PNG-изображениями
ASSETS_DIR = Path(__file__).parent / "images"

# Маппинг типа уведомления → имя файла
# Ключи соответствуют notify_type из _classify_slot_change()
NOTIFY_IMAGE_MAP: dict[str, str] = {
    "empty": "slot_empty.png",
    "available": "slot_available.png",
    "new": "slot_new.png",
    "decreased": "slot_decreased.png",
}

# Маппинг экранов навигации → имя файла
NAV_IMAGE_MAP: dict[str, str] = {
    "patient": "patient_select.png",
    "clinic": "clinic_select.png",
    "doctor_adult": "doctor_adult_select.png",
    "doctor_child": "doctor_child_select.png",
    "doctor_dentist": "doctor_dentist_select.png",
}


def get_photo_path(filename: str) -> Path | None:
    """Возвращает полный путь к изображению, если файл существует.

    Args:
        filename: Имя файла (только имя, без пути).

    Returns:
        Path до файла или None, если файл отсутствует.
    """
    path = ASSETS_DIR / filename
    return path if path.is_file() else None


def get_notify_image_path(notify_type: str) -> Path | None:
    """Возвращает путь к изображению для типа уведомления.

    Args:
        notify_type: Тип уведомления (empty, available, new, decreased).

    Returns:
        Path до PNG-файла или None, если файл не найден.
    """
    filename = NOTIFY_IMAGE_MAP.get(notify_type)
    if filename is None:
        return None
    return get_photo_path(filename)


def get_nav_image_path(nav_type: str) -> Path | None:
    """Возвращает путь к изображению для экрана навигации.

    Args:
        nav_type: Тип экрана
            (patient, clinic, doctor_adult, doctor_child, doctor_dentist).

    Returns:
        Path до PNG-файла или None, если файл не найден.
    """
    filename = NAV_IMAGE_MAP.get(nav_type)
    if filename is None:
        return None
    return get_photo_path(filename)
