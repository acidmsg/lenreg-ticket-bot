# Дизайн-система мини-приложения «Здрав.ЛенРег»

Единый источник истины (SSOT) для всех визуальных решений. Все компоненты, стили и темы
ссылаются на токены, определённые в этом документе.

## 1. Обзор архитектуры

| Параметр                | Значение                                              |
| ----------------------- | ----------------------------------------------------- | ----------------- |
| Проект                  | Telegram Mini App + десктопный dashboard              |
| Подход                  | Семантические CSS custom properties, атомарные токены |
| Количество тем          | 2 (dark / light)                                      |
| Автоопределение темы    | `Telegram.WebApp.colorScheme`                         |
| Механизм переключения   | `data-theme="dark                                     | light"`на`<html>` |
| JS-мост                 | Читает `colorScheme` и слушает `themeChanged` event   |
| Fallback (вне Telegram) | `prefers-color-scheme` media query                    |
| Telegram-цвета          | НЕ используются (`--tg-theme-*` игнорированы)         |
| Бэклог                  | OLED-тема, high-contrast тема                         |

Реализация JS-моста: [`src/web/static/app/js/app.js`](../src/web/static/app/js/app.js:12)

## 2. Семантические цветовые токены

### 2.1. Тёмная тема — «Неоновая плазма»

| Имя токена               | Значение                     | Назначение                |
| ------------------------ | ---------------------------- | ------------------------- |
| `--color-bg-primary`     | `#0a0a10`                    | Фон страницы              |
| `--color-bg-secondary`   | `#12121c`                    | Фон карточек / панелей    |
| `--color-text-primary`   | `#e0e8f8`                    | Основной текст            |
| `--color-text-secondary` | `#8899bb`                    | Второстепенный текст      |
| `--color-accent`         | `#09b653`                    | Основной акцент (зелёный) |
| `--color-accent-text`    | `#0a0a10`                    | Текст на accent-фоне      |
| `--color-accent-hover`   | `#07a048`                    | Accent при наведении      |
| `--color-danger`         | `#ea336f`                    | Удаление / опасность      |
| `--color-danger-text`    | `#ffffff`                    | Текст на danger-фоне      |
| `--color-border`         | `rgba(255,255,255, 0.08)`    | Тонкие границы            |
| `--color-border-strong`  | `rgba(255,255,255, 0.14)`    | Выраженные границы        |
| `--shadow-card`          | `0 2px 8px rgb(0,0,0 / 30%)` | Тень карточки             |
| `--status-available`     | `#09b653`                    | Слоты доступны            |
| `--status-noslots`       | `#ea336f`                    | Слотов нет                |
| `--status-checking`      | `#555acf`                    | Проверка                  |
| `--status-unknown`       | `#778899`                    | Неизвестно                |

### 2.2. Светлая тема — «Медицинская чистота»

| Имя токена               | Значение                      | Назначение               |
| ------------------------ | ----------------------------- | ------------------------ |
| `--color-bg-primary`     | `#f4f6f9`                     | Фон страницы             |
| `--color-bg-secondary`   | `#ffffff`                     | Фон карточек             |
| `--color-text-primary`   | `#1e293b`                     | Основной текст           |
| `--color-text-secondary` | `#64748b`                     | Второстепенный текст     |
| `--color-accent`         | `#3b82f6`                     | Основной акцент (синий)  |
| `--color-accent-text`    | `#ffffff`                     | Текст на accent-фоне     |
| `--color-accent-hover`   | `#2563eb`                     | Accent при наведении     |
| `--color-danger`         | `#ef4444`                     | Удаление / опасность     |
| `--color-danger-text`    | `#ffffff`                     | Текст на danger-фоне     |
| `--color-border`         | `rgba(0,0,0, 0.08)`           | Тонкие границы           |
| `--color-border-strong`  | `rgba(0,0,0, 0.14)`           | Выраженные границы       |
| `--shadow-card`          | `0 1px 3px rgba(0,0,0, 0.06)` | Тень карточки            |
| `--status-available`     | `#22c55e`                     | Слоты доступны (зелёный) |
| `--status-noslots`       | `#ef4444`                     | Слотов нет               |
| `--status-checking`      | `#3b82f6`                     | Проверка                 |
| `--status-unknown`       | `#94a3b8`                     | Неизвестно               |

Все цветовые токены объявлены в [`src/web/static/app/css/style.css`](../src/web/static/app/css/style.css:14)

## 3. Типографика

### 3.1. Семейство шрифтов

| Токен           | Значение                                                                                     |
| --------------- | -------------------------------------------------------------------------------------------- |
| `--font-family` | `-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif` |

### 3.2. Размеры шрифта

| Токен       | Значение | Назначение                              |
| ----------- | -------- | --------------------------------------- |
| `--font-xs` | `12px`   | Подписи, бейджи, статус-индикаторы      |
| `--font-sm` | `14px`   | Второстепенный текст, hint, placeholder |
| `--font-md` | `16px`   | Основной текст, содержимое карточек     |
| `--font-lg` | `18px`   | Подзаголовки, названия карточек         |
| `--font-xl` | `22px`   | Заголовки экранов, секций               |

### 3.3. Жирность

| Токен                    | Значение | Назначение                 |
| ------------------------ | -------- | -------------------------- |
| `--font-weight-normal`   | `400`    | Основной текст             |
| `--font-weight-medium`   | `500`    | Акценты, метки, chip       |
| `--font-weight-semibold` | `600`    | Заголовки карточек, кнопки |
| `--font-weight-bold`     | `700`    | Заголовки экранов          |

### 3.4. Межстрочные интервалы

| Токен                   | Значение | Назначение                    |
| ----------------------- | -------- | ----------------------------- |
| `--line-height-tight`   | `1.2`    | Заголовки, однострочный текст |
| `--line-height-normal`  | `1.4`    | Основной текст                |
| `--line-height-relaxed` | `1.6`    | Длинный текст, описания       |

### 3.5. Межбуквенные интервалы

| Токен                     | Значение | Назначение    |
| ------------------------- | -------- | ------------- |
| `--letter-spacing-normal` | `0`      | По умолчанию  |
| `--letter-spacing-wide`   | `0.02em` | Кнопки, метки |

### 3.6. Таблица применения типографики

| Элемент           | Размер             | Жирность                       | line-height                  | letter-spacing                   |
| ----------------- | ------------------ | ------------------------------ | ---------------------------- | -------------------------------- |
| Заголовок экрана  | `--font-xl` (22px) | `--font-weight-bold` (700)     | `--line-height-tight` (1.2)  | normal                           |
| Название карточки | `--font-lg` (18px) | `--font-weight-semibold` (600) | `--line-height-tight` (1.2)  | normal                           |
| Основной текст    | `--font-md` (16px) | `--font-weight-normal` (400)   | `--line-height-normal` (1.4) | normal                           |
| Подсказка / hint  | `--font-sm` (14px) | `--font-weight-normal` (400)   | `--line-height-normal` (1.4) | normal                           |
| Кнопка            | `--font-md` (16px) | `--font-weight-semibold` (600) | —                            | `--letter-spacing-wide` (0.02em) |
| Бейдж / статус    | `--font-xs` (12px) | `--font-weight-medium` (500)   | —                            | normal                           |

Предпросмотр типографики: [`_design_lab/typography/index.html`](../../_design_lab/typography/index.html:1)
Стили предпросмотра: [`_design_lab/typography/styles.css`](../../_design_lab/typography/styles.css:1)

## 4. Отступы (Spacing)

Шкала на базе 4px, 9 ступеней:

| Токен         | Значение | Назначение                                 |
| ------------- | -------- | ------------------------------------------ |
| `--space-xs`  | `4px`    | Иконка ↔ текст, чипы                       |
| `--space-sm`  | `8px`    | Внутренние зазоры, группа кнопок           |
| `--space-md`  | `12px`   | Элементы списка, внутренний padding        |
| `--space-lg`  | `16px`   | Padding карточек, боковые отступы контента |
| `--space-xl`  | `20px`   | Разделение секций                          |
| `--space-2xl` | `24px`   | Вертикальный ритм, крупные блоки           |
| `--space-3xl` | `32px`   | Padding страницы (десктоп)                 |
| `--space-4xl` | `40px`   | Крупные разделители                        |
| `--space-5xl` | `48px`   | Максимальный (hero, dashboard grid-gap)    |

Все токены отступов объявлены в [`src/web/static/app/css/style.css`](../src/web/static/app/css/style.css:40)

## 5. Размеры элементов

### 5.1. Высоты контролов

| Токен               | Значение | Назначение                                  |
| ------------------- | -------- | ------------------------------------------- |
| `--size-control-sm` | `36px`   | Маленькие кнопки, чипы                      |
| `--size-control-md` | `44px`   | Основные кнопки, инпуты (WCAG touch target) |
| `--size-control-lg` | `52px`   | Крупные CTA-кнопки                          |

### 5.2. Иконки

| Токен            | Значение | Назначение                         |
| ---------------- | -------- | ---------------------------------- |
| `--size-icon-sm` | `16px`   | Внутри кнопок, списков             |
| `--size-icon-md` | `20px`   | Стандартные (Lucide)               |
| `--size-icon-lg` | `24px`   | Крупные (пустое состояние, header) |

### 5.3. Специфичные элементы

| Токен                | Значение | Назначение              |
| -------------------- | -------- | ----------------------- |
| `--size-fab`         | `56px`   | Floating Action Button  |
| `--size-dot`         | `8px`    | Статус-точка            |
| `--size-stepper-dot` | `24px`   | Кружок шага stepper     |
| `--size-chip`        | `32px`   | Slot-чип (время записи) |

Все токены размеров объявлены в [`src/web/static/app/css/style.css`](../src/web/static/app/css/style.css:52)
Предпросмотр размеров: [`_design_lab/sizes/index.html`](../../_design_lab/sizes/index.html:1)
Стили предпросмотра: [`_design_lab/sizes/styles.css`](../../_design_lab/sizes/styles.css:1)

## 6. Радиусы

| Токен           | Значение | Назначение                               |
| --------------- | -------- | ---------------------------------------- |
| `--radius-sm`   | `4px`    | Бейджи, мелкие метки                     |
| `--radius-md`   | `8px`    | Чипы, инпуты, skeleton                   |
| `--radius-lg`   | `12px`   | Карточки, кнопки, search (унифицировано) |
| `--radius-xl`   | `16px`   | Модальные окна, крупные панели           |
| `--radius-full` | `9999px` | Круглые элементы (FAB, пилюли, аватарки) |

Все токены радиусов объявлены в [`src/web/static/app/css/style.css`](../src/web/static/app/css/style.css:65)

## 7. Тени

| Токен         | Тёмная тема                   | Светлая тема                   | Назначение        |
| ------------- | ----------------------------- | ------------------------------ | ----------------- |
| `--shadow-sm` | `0 1px 2px rgb(0,0,0 / 20%)`  | `0 1px 2px rgba(0,0,0, 0.04)`  | Лёгкая (hover)    |
| `--shadow-md` | `0 2px 8px rgb(0,0,0 / 30%)`  | `0 1px 3px rgba(0,0,0, 0.06)`  | Карточки          |
| `--shadow-lg` | `0 4px 16px rgb(0,0,0 / 40%)` | `0 4px 12px rgba(0,0,0, 0.10)` | Модалки, dropdown |

Тени объявлены в [`src/web/static/app/css/style.css`](../src/web/static/app/css/style.css:75)

> **Примечание:** `--shadow-card` (см. раздел 2) — синоним `--shadow-md`, оставлен для
> обратной совместимости. В новом коде использовать `--shadow-md`.

## 8. Анимации

| Токен                 | Значение    | Назначение                |
| --------------------- | ----------- | ------------------------- |
| `--transition-fast`   | `0.1s ease` | hover, active, focus      |
| `--transition-normal` | `0.2s ease` | Основные переходы         |
| `--transition-slow`   | `0.3s ease` | Модалки, раскрытие секций |

Объявлены в [`src/web/static/app/css/style.css`](../src/web/static/app/css/style.css:82)

## 9. Компонентная стратегия

Все компоненты используют атомарные токены напрямую, без промежуточных алиасов.

**Принцип:** компонент ссылается на семантический токен, а не создаёт
компонент-специфичную переменную.

```css
/* ✅ Правильно: атомарные токены напрямую */
.btn {
  padding: var(--space-sm) var(--space-lg);
  border-radius: var(--radius-lg);
  height: var(--size-control-md);
}

/* ❌ Неправильно: компонент-специфичная переменная */
.btn {
  padding: var(--btn-padding-y) var(--btn-padding-x);
}
```

**Запрещено** создание компонент-специфичных переменных (`--btn-padding-x`,
`--card-gap` и т.п.). Если компоненту нужен уникальный отступ — используется
ближайший подходящий токен из шкалы `--space-*`.

## 10. Соответствие старой системы → новой

Таблица миграции для перехода с Telegram-themed переменных на собственную
дизайн-систему.

| Старое имя                  | Новое имя                |
| --------------------------- | ------------------------ |
| `--tg-bg-color`             | `--color-bg-primary`     |
| `--tg-secondary-bg-color`   | `--color-bg-secondary`   |
| `--tg-text-color`           | `--color-text-primary`   |
| `--tg-hint-color`           | `--color-text-secondary` |
| `--tg-button-color`         | `--color-accent`         |
| `--tg-button-text-color`    | `--color-accent-text`    |
| `--tg-destructive-color`    | `--color-danger`         |
| `--tg-section-header-color` | `--color-accent`         |
| `--tg-subtitle-color`       | `--color-text-secondary` |
| `--tg-link-color`           | `--color-accent`         |
| `--card-radius`             | `--radius-lg`            |
| `--card-shadow`             | `--shadow-md`            |
| `--card-padding`            | `--space-lg`             |
| `--gap-xs..2xl`             | `--space-xs..4xl`        |
| `--font-sm..xl`             | `--font-xs..xl`          |

Миграция выполняется в [`src/web/static/app/css/style.css`](../src/web/static/app/css/style.css:1)

## 11. Файлы дизайн-лаборатории

Для визуального предпросмотра и ручной верификации токенов используются
следующие страницы дизайн-лаборатории:

| Страница    | Файл                                                                             | Назначение                                                  |
| ----------- | -------------------------------------------------------------------------------- | ----------------------------------------------------------- |
| Типографика | [`_design_lab/typography/index.html`](../../_design_lab/typography/index.html:1) | Предпросмотр всех размеров, жирности, line-height           |
| Размеры     | [`_design_lab/sizes/index.html`](../../_design_lab/sizes/index.html:1)           | Предпросмотр высот контролов, иконок, специфичных элементов |

Каждая страница дизайн-лаборатории подключает соответствующий
[`styles.css`](../../_design_lab/typography/styles.css:1), который
импортирует токены из основного [`style.css`](../src/web/static/app/css/style.css:1).
