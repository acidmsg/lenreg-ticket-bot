# Session: 2026-06-15

## Выполненные задачи

### Багфикс: Дашборд — 3 бага

| #   | Баг              | Файл                                            | Строки      | Причина                                            | Исправление                                         |
| --- | ---------------- | ----------------------------------------------- | ----------- | -------------------------------------------------- | --------------------------------------------------- |
| 1   | Логи 500         | [`logs.html`](src/web/templates/logs.html)      | 15,18,19,22 | `status_filter="" ="..."` — нет `==` в Jinja2      | Заменён синтаксис на `status_filter == "..."`       |
| 2   | Спиннер бэкапов  | [`dashboard.css`](src/web/static/dashboard.css) | 325-343     | `.spinner__icon` переопределял `.hidden`           | `.hidden` перенесён после, добавлен `!important`    |
| 3   | Белый фон иконок | [`dashboard.css`](src/web/static/dashboard.css) | 232-238     | `.btn-link` не сбрасывал `background` у `<button>` | Добавлены `background: transparent`, `border: none` |

### Фича: Синхронная навигация календаря при вводе даты

| Файл                                                          | Строки    | Описание                                                                                |
| ------------------------------------------------------------- | --------- | --------------------------------------------------------------------------------------- |
| [`calendar.js`](src/web/static/app/js/components/calendar.js) | 461-558   | Новые хелперы `parsePartialDate()` и `determineTargetMonth()`                           |
| [`calendar.js`](src/web/static/app/js/components/calendar.js) | 778       | `setValue()` теперь принимает `null` для снятия подсветки                               |
| [`calendar.js`](src/web/static/app/js/components/calendar.js) | 1068-1139 | `createDatePicker()`: focus/blur для показа календаря, обработчик `input` для навигации |
| [`style.css`](src/web/static/app/css/style.css)               | 1430-1699 | CSS-блоки календаря (сетка, ячейки, month-picker, date-input, date-picker)              |

## Изменённые файлы

- `src/web/templates/logs.html`
- `src/web/static/dashboard.css`
- `src/web/static/app/js/components/calendar.js`
- `src/web/static/app/css/style.css`
