# Результат проверки `keyboards/inline.py` на неактуальные строки

## Методология

Проверены:

- Все callback_data, генерируемые в `keyboards/inline.py`, на наличие соответствующих хэндлеров в `handlers/*.py`
- Все функции модуля на наличие вызовов во всём проекте (`*.py`)
- Все импорты на фактическое использование внутри модуля

## Найденные неактуальные строки

### 1. Функция `get_main_menu()` (строки 10–15)

```python
def get_main_menu():
    builder = ReplyKeyboardBuilder()
    builder.button(text="🔍 Настроить поиск")
    builder.button(text="🛑 Стоп все")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)
```

- **Статус:** НЕ ИСПОЛЬЗУЕТСЯ
- Импортируется в `handlers/common.py` (строка 17), но **нигде не вызывается** во всём проекте.
- Вместе с ней становится неактуальным импорт `ReplyKeyboardBuilder` (строка 4), так как это единственное место использования.

### 2. Импорт `types` (строка 3)

```python
from aiogram import types
```

- **Статус:** НЕ ИСПОЛЬЗУЕТСЯ
- Модуль `types` импортирован, но в файле нет ни одного обращения к `types.*`.

## Всё актуально (не требует изменений)

| Callback / функция | Используется в хэндлере |
|---|---|
| `sel_p_` | `handlers/common.py` — `select_patient` |
| `sel_c_` | `handlers/common.py` — `select_clinic` |
| `tgl_` | `handlers/common.py` — `toggle_doctor` |
| `back_to_main` | `handlers/common.py` — `back_to_main` |
| `stop_patient_` | `handlers/common.py` — `stop_patient_monitoring` |
| `stop_clinic_` | `handlers/common.py` — `stop_clinic_monitoring` |
| `stop_all` | `handlers/common.py` — `stop_all_monitoring` |
| `start_add_p` | `handlers/registration.py` — `start_add_patient` |
| `skip_alias` | `handlers/registration.py` — `skip_alias` |
| `del_p_ask_` / `del_p_yes_` | `handlers/common.py` — `handle_delete_patient` |
| `get_patient_selection()` | Вызывается в 3 местах (`common.py`) |
| `get_clinic_selection()` | Вызывается в `common.py` |
| `get_doctor_selection()` | Вызывается в 2 местах (`common.py`) |
| `get_confirm_deletion()` | Вызывается в `handlers/common.py` |
| `get_skip_alias_keyboard()` | Вызывается в `handlers/registration.py` |
| `from datetime import datetime` | Используется в `get_clinic_selection()` (расчёт возраста) |
| `from config import CLINICS_REGISTRY` | Используется в `get_clinic_selection()` |
| `from utils.helpers import ...` | Все функции используются в `get_doctor_selection()` |

## Рекомендация

Удалить:

- Строку 1 (под вопросом — `datetime` нужен для `get_clinic_selection()` — **НЕТ, нужно оставить**)
- Строку 3: `from aiogram import types`
- Строки 4, 10-15: функцию `get_main_menu()` и импорт `ReplyKeyboardBuilder`

Если `get_main_menu()` планируется использовать в будущем, можно оставить, но на данный момент это мёртвый код.
