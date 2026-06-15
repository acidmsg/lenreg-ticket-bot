# Session: 2026-06-15

## Дашборд — 3 бага + кэширование

| Файл                                                      | Коммит                    | Исправление                                                                                                                                |
| --------------------------------------------------------- | ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| [`logs.html`](src/web/templates/logs.html:15)             | 2a273ef                   | Jinja2 `status_filter="" ="..."` → `status_filter == "..."`                                                                                |
| [`dashboard.css`](src/web/static/dashboard.css:325)       | 2a273ef, aa80882, a0f5d58 | Спиннер: `.hidden` после `.spinner__icon` + `!important`. Кнопки: `appearance: none`, полный рефакторинг на CSS-переменные мини-приложения |
| [`backups.js`](src/web/static/app/js/views/backups.js:44) | aa80882                   | `AbortController` + 30s таймаут для fetch                                                                                                  |
| [`app.py`](src/web/app.py:28)                             | f70b98a                   | `StaticNoCacheMiddleware` для `/static/*`                                                                                                  |
| Cloudflare                                                | —                         | Browser Cache TTL → Respect Existing Headers, Purge Cache                                                                                  |

## Календарь — синхронная подсветка, тема, blur

| Файл                                                         | Коммит  | Что                                                                                     |
| ------------------------------------------------------------ | ------- | --------------------------------------------------------------------------------------- |
| [`patients.js`](src/web/static/app/js/views/patients.js:325) | b9885d5 | Синхронная подсветка при вводе: `calendar.selectedDates` + синтетическая ISO            |
| [`style.css`](src/web/static/app/css/style.css:1388)         | f89b230 | Тема 1h: today инвертированная пилюля, selected accent-рамка 1px, `--color-accent-rgb`  |
|                                                              | c7b5ae8 | Удалён самописный `calendar.js`, CSS кастомного календаря, `calendar-component-spec.md` |
| [`patients.js`](src/web/static/app/js/views/patients.js:471) | 07822f6 | `calendar.hide()` при Tab: `setTimeout` + `activeElement` проверка                      |
| [`patients.js`](src/web/static/app/js/views/patients.js:287) | 644367f | Обратное поведение: откат подсветки при стирании, сброс на 0/1 цифре                    |

## Дизайн-лаборатория

`_design_lab/calendar-variants/` — 10 вариантов подсветки (variant-1, 1b–1h, 2–4). Утверждён 1h.

## Изменённые файлы

- `src/web/templates/logs.html`
- `src/web/static/dashboard.css`
- `src/web/static/app/js/views/backups.js`
- `src/web/app.py`
- `src/web/static/app/js/views/patients.js`
- `src/web/static/app/css/style.css`
- `src/web/static/app/index.html`
- `_design_lab/calendar-variants/` (10 новых файлов)

## Удалённые файлы

- `src/web/static/app/js/components/calendar.js`
- `src/web/static/app/vendor/vanilla-calendar.min.css`
- `src/web/static/app/vendor/vanilla-calendar.min.js`
- `plans/calendar-component-spec.md`
