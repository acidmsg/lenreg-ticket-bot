# Спецификация: Компонент календаря для мини-приложения

> **Статус:** Architectural Spec (Design-Only)
> **Дата:** 2026-06-10
> **Версия:** 1.0.0

---

## 1. Обзор

Документ описывает архитектуру компонента выбора даты для Telegram Mini App (Vanilla JS SPA). Компонент состоит из трёх независимых строительных блоков:

- **`createCalendar()`** — календарь с навигацией по месяцам (фабрика).
- **`createDateInput()`** — поле ввода с маской `ДД.ММ.ГГГГ` и валидацией (фабрика).
- **`createDatePicker()`** — композитный виджет, связывающий календарь + поле ввода двунаправленно (фабрика).

Все три компонента используют только нативные DOM API, без внешних зависимостей.

---

## 2. Структура файлов

### 2.1 Новые файлы

| Файл                                                                                           | Назначение                                                             |
| ---------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| [`src/web/static/app/js/components/calendar.js`](src/web/static/app/js/components/calendar.js) | Фабрики: `createCalendar()`, `createDateInput()`, `createDatePicker()` |

### 2.2 Изменяемые файлы

#### Фронтенд

| Файл                                                                                         | Изменения                                                                                                                |
| -------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| [`src/web/static/app/js/components/stepper.js`](src/web/static/app/js/components/stepper.js) | Добавить поддержку `step.type === 'widget'`: показ кнопки «Далее», прямой рендеринг без списка, подавление авто-перехода |
| [`src/web/static/app/js/views/add.js`](src/web/static/app/js/views/add.js)                   | Вставить шаг «Выберите дату» в массив `steps`. Обновить индексы. Добавить дату на экран подтверждения и в POST           |
| [`src/web/static/app/css/style.css`](src/web/static/app/css/style.css)                       | Добавить блоки `.calendar`, `.date-input`, `.date-picker` (≈150 строк)                                                   |

#### Бэкенд (см. секцию 12 — поле `date` отсутствует на всех уровнях)

| Файл                                                                 | Изменения                                                                        |
| -------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| [`src/database/types.py`](src/database/types.py)                     | Добавить `date: str` в `MonitoringEntry` TypedDict                               |
| [`src/database/repo_monitoring.py`](src/database/repo_monitoring.py) | Добавить колонку `date` в SQL `INSERT OR REPLACE`, параметр `date` в метод       |
| [`src/database/database.py`](src/database/database.py)               | Пробросить параметр `date` в вызов `add_monitoring_entry()`                      |
| [`src/database/manager.py`](src/database/manager.py)                 | Добавить `date` в сигнатуру `toggle_monitoring()`, сохранять в `MonitoringEntry` |
| [`src/database/migrations.py`](src/database/migrations.py)           | Добавить миграцию: `ALTER TABLE user_monitoring ADD COLUMN date TEXT DEFAULT ''` |
| [`src/web/routers/user_api.py`](src/web/routers/user_api.py)         | Добавить `date: str` в `AddDoctorRequest`, пробросить в `toggle_monitoring()`    |
| [`src/handlers/common.py`](src/handlers/common.py)                   | Обновить вызов `toggle_monitoring()` — добавить `date=""`                        |
| [`src/handlers/mini_app.py`](src/handlers/mini_app.py)               | Обновить вызов `toggle_monitoring()` — добавить `date=""`                        |

---

## 3. Диаграмма взаимодействия компонентов

```mermaid
flowchart TD
    A[add.js: renderAddDoctor] --> B[createStepper]
    B --> C{step.type === 'widget'?}
    C -->|yes| D[renderItem → createDatePicker]
    C -->|no| E[renderItem → list items]
    D --> F[createCalendar]
    D --> G[createDateInput]
    F <-->|двунаправленная связь| G
    G -->|onChange| H[item.value.date = formattedDate]
    B -->|кнопка «Далее»| I[advanceStep: push stepData[0] to selections]
    I --> J[selections = [patient, dateItem, clinic?, doctor?]]
    J --> K[onComplete: читает selections[1].value.date]
```

---

## 4. API компонентов

### 4.1 `createCalendar(options)` — Календарь

Файл: [`src/web/static/app/js/components/calendar.js`](src/web/static/app/js/components/calendar.js)

#### Сигнатура

```js
/**
 * Создаёт экземпляр календаря и рендерит его в указанный контейнер.
 *
 * @param {object} options
 * @param {HTMLElement} options.container — DOM-элемент для рендеринга
 * @param {string} [options.value] — начальная дата в формате 'ДД.ММ.ГГГГ' (или 'YYYY-MM-DD' — см. внутренний формат)
 * @param {Function} [options.onChange] — колбэк при выборе даты: onChange(dateString)
 * @param {string} [options.min] — минимальная дата в формате 'YYYY-MM-DD' (включительно)
 * @param {string} [options.max] — максимальная дата в формате 'YYYY-MM-DD' (включительно)
 * @returns {object} управляющий объект
 */
export function createCalendar({ container, value, onChange, min, max }) { ... }
```

#### Возвращаемое значение

```js
{
  /** Установить выбранную дату (строка 'ДД.ММ.ГГГГ') */
  setValue: (dateString) => { ... },

  /** Получить текущую выбранную дату */
  getValue: () => 'ДД.ММ.ГГГГ' | null,

  /** Переключить на указанный месяц (1-12) и год */
  goToMonth: (year, month) => { ... },

  /** Уничтожить экземпляр (снять обработчики) */
  destroy: () => { ... }
}
```

#### Внутренний формат даты

Календарь хранит выбранную дату как строку `'YYYY-MM-DD'` (ISO-формат) внутри. Наружу через `onChange` и `getValue()` отдаёт `'ДД.ММ.ГГГГ'` (отображаемый формат). Параметр `value` принимает `'ДД.ММ.ГГГГ'`.

#### Структура HTML

```html
<div class="calendar">
  <div class="calendar__header">
    <button class="calendar__nav calendar__nav--prev" aria-label="Предыдущий месяц">
      <
    </button>
    <span class="calendar__month-label">Июнь 2026</span>
    <button class="calendar__nav calendar__nav--next" aria-label="Следующий месяц">
      >
    </button>
  </div>
  <div class="calendar__weekdays">
    <span>Пн</span><span>Вт</span><span>Ср</span><span>Чт</span><span>Пт</span
    ><span>Сб</span><span>Вс</span>
  </div>
  <div class="calendar__grid">
    <!-- 6 строк × 7 ячеек = 42 дня -->
    <button class="calendar__day calendar__day--other-month">28</button>
    <button class="calendar__day calendar__day--other-month">29</button>
    <button class="calendar__day calendar__day--other-month">30</button>
    <button class="calendar__day calendar__day--other-month">31</button>
    <button class="calendar__day">1</button>
    ...
    <button class="calendar__day calendar__day--today">10</button>
    ...
    <button class="calendar__day calendar__day--selected">15</button>
    ...
  </div>
</div>
```

#### CSS-классы ячеек

| Класс                          | Назначение                                   |
| ------------------------------ | -------------------------------------------- |
| `.calendar__day`               | Базовая ячейка дня                           |
| `.calendar__day--today`        | Сегодняшняя дата (обводка/подсветка)         |
| `.calendar__day--selected`     | Выбранная дата (фон `--tg-button-color`)     |
| `.calendar__day--other-month`  | Дни соседних месяцев (приглушённый цвет)     |
| `.calendar__day--disabled`     | Дата вне диапазона `[min, max]` (недоступна) |
| `.calendar__day:focus-visible` | Фокус клавиатуры (outline)                   |

#### Поведение

- При клике на день: обновить выбранную дату, вызвать `onChange(dateString)`.
- При `setValue(dateString)`: переключить месяц (если нужно), обновить выделение.
- При `goToMonth(year, month)`: перерисовать сетку дней для указанного месяца.
- Кнопки навигации: `←` предыдущий месяц, `→` следующий месяц. Не выходят за границы `[min, max]`.
- Клавиатурная навигация: Tab между кнопками дней, Enter/Space для выбора.
- Стрелки: ← → ↑ ↓ для перемещения между днями (на `document` через делегирование при фокусе внутри календаря).
- Мобильный-first: размер ячеек — минимум 40×40px (удобно для пальца).

---

### 4.2 `createDateInput(options)` — Поле ввода с маской

Файл: [`src/web/static/app/js/components/calendar.js`](src/web/static/app/js/components/calendar.js)

#### Сигнатура

```js
/**
 * Создаёт поле ввода с маской ДД.ММ.ГГГГ и валидацией.
 *
 * @param {object} options
 * @param {HTMLElement} options.container — DOM-элемент для рендеринга
 * @param {string} [options.value] — начальное значение в формате 'ДД.ММ.ГГГГ'
 * @param {Function} [options.onChange] — колбэк при изменении валидной даты: onChange(dateString)
 * @param {string} [options.placeholder] — плейсхолдер (по умолчанию 'ДД.ММ.ГГГГ')
 * @returns {object} управляющий объект
 */
export function createDateInput({ container, value, onChange, placeholder }) { ... }
```

#### Возвращаемое значение

```js
{
  /** Установить значение */
  setValue: (dateString) => { ... },

  /** Получить текущее значение */
  getValue: () => 'ДД.ММ.ГГГГ' | '',

  /** Сфокусировать поле ввода */
  focus: () => { ... },

  /** Показать ошибку валидации (красная обводка + текст под полем) */
  setError: (message) => { ... },

  /** Снять ошибку */
  clearError: () => { ... },

  /** Уничтожить экземпляр */
  destroy: () => { ... }
}
```

#### Структура HTML

```html
<div class="date-input">
  <input
    type="text"
    class="date-input__field"
    inputmode="numeric"
    placeholder="ДД.ММ.ГГГГ"
    maxlength="10"
    autocomplete="off"
  />
  <p class="date-input__error" hidden>Некорректная дата</p>
</div>
```

#### Маска (логика)

Реализуется через обработчик `input`:

- Разрешены только цифры.
- При вводе 2-й цифры дня → автоматически вставляется `.`.
- При вводе 2-й цифры месяца → автоматически вставляется `.`.
- При вводе 4-й цифры года → остановка.
- Backspace/Delete работают ожидаемо (удаление цифры, пропуск точки).
- Позиция курсора сохраняется корректно (через `setSelectionRange`).

#### Валидация (при полном вводе 10 символов)

- День: 01–31.
- Месяц: 01–12.
- Год: 1900–2099 (не «из прошлого» — это бизнес-правило на уровне `createDatePicker`, не здесь).
- Проверка на реальность даты: `new Date(year, month-1, day)` — месяц должен совпадать (защита от 31 февраля).
- При ошибке: красная обводка (`--tg-destructive-color`), текст ошибки под полем.
- При успехе: вызов `onChange(dateString)`.

---

### 4.3 `createDatePicker(options)` — Композитный виджет

Файл: [`src/web/static/app/js/components/calendar.js`](src/web/static/app/js/components/calendar.js)

#### Сигнатура

```js
/**
 * Создаёт композитный виджет: календарь + поле ввода с двунаправленной связью.
 *
 * @param {object} options
 * @param {HTMLElement} options.container — DOM-элемент для рендеринга
 * @param {string} [options.value] — начальная дата в формате 'ДД.ММ.ГГГГ'
 * @param {Function} [options.onChange] — колбэк при изменении даты: onChange(dateString)
 * @param {string} [options.min] — минимальная дата 'YYYY-MM-DD'
 * @param {string} [options.max] — максимальная дата 'YYYY-MM-DD'
 * @returns {object} управляющий объект
 */
export function createDatePicker({ container, value, onChange, min, max }) { ... }
```

#### Возвращаемое значение

```js
{
  /** Получить текущую дату */
  getValue: () => 'ДД.ММ.ГГГГ' | null,

  /** Установить дату */
  setValue: (dateString) => { ... },

  /** Сфокусировать поле ввода */
  focus: () => { ... },

  /** Уничтожить виджет */
  destroy: () => { ... }
}
```

#### Внутреннее устройство

```js
export function createDatePicker({ container, value, onChange, min, max }) {
  // Рендерим контейнеры
  container.innerHTML = `
    <div class="date-picker">
      <div class="date-picker__input" id="dp-input-container"></div>
      <div class="date-picker__calendar" id="dp-calendar-container"></div>
    </div>
  `;

  const inputContainer = container.querySelector('#dp-input-container');
  const calendarContainer = container.querySelector('#dp-calendar-container');

  // Двунаправленная связь:
  // 1. Календарь → Инпут: calendar.onChange → input.setValue()
  // 2. Инпут → Календарь: input.onChange → calendar.setValue() + calendar.goToMonth()

  const calendar = createCalendar({
    container: calendarContainer,
    value,
    onChange: (dateStr) => {
      input.setValue(dateStr);
      if (onChange) onChange(dateStr);
    },
    min,
    max
  });

  const input = createDateInput({
    container: inputContainer,
    value,
    placeholder: 'ДД.ММ.ГГГГ',
    onChange: (dateStr) => {
      calendar.setValue(dateStr);
      // Переключить календарь на месяц выбранной даты
      const [d, m, y] = dateStr.split('.');
      calendar.goToMonth(parseInt(y, 10), parseInt(m, 10));
      if (onChange) onChange(dateStr);
    }
  });

  return {
    getValue: () => input.getValue(),
    setValue: (dateStr) => {
      input.setValue(dateStr);
      calendar.setValue(dateStr);
    },
    focus: () => input.focus(),
    destroy: () => {
      calendar.destroy();
      input.destroy();
    }
  };
}
```

---

## 5. Схема данных в степпере

### 5.1 Формат даты в `selections`

Дата хранится как элемент `selections` на позиции 1 (после пациента):

```js
selections = [
  { value: { patient_id: ..., fio: '...' }, label: 'Иванов И.И.' },  // [0] пациент
  { value: { date: '15.06.2026' }, label: '' },                       // [1] дата
  { value: { clinic_id: ..., name: '...' }, label: '...' },           // [2] клиника (или врач при _skipNext)
  { value: { doctor_id: ..., name: '...' }, label: '...' }            // [3] врач (может отсутствовать при _skipNext)
]
```

### 5.2 Индексы после вставки шага даты

| До (current)        | После (new)         | Содержимое             |
| ------------------- | ------------------- | ---------------------- |
| `[0]` пациент       | `[0]` пациент       | Без изменений          |
| —                   | `[1]` дата          | **Новый шаг**          |
| `[1]` клиника/поиск | `[2]` клиника/поиск | Индексы сдвинуты на +1 |
| `[2]` врач          | `[3]` врач          | Индексы сдвинуты на +1 |
| `[3]` подтверждение | `[4]` подтверждение | Индексы сдвинуты на +1 |

### 5.3 Передача даты в `onComplete`

```js
onComplete: async (selections) => {
  const patient = selections[0]?.value;
  const dateSelection = selections[1]?.value;      // { date: '15.06.2026' }
  const selectedDate = dateSelection?.date || '';

  // Далее — логика клиники/врача со сдвигом индексов на +1
  let clinic, doctor;
  if (selections.length >= 4 && !selections[2]?._skipNext) {
    clinic = selections[2]?.value;
    doctor = selections[3]?.value;
  } else {
    doctor = selections[2]?.value;
    clinic = { clinic_id: doctor?.clinic_id || '', ... };
  }

  // POST /api/user/doctors/add — добавить поле date
  await apiPost('/doctors/add', {
    clinic_id: clinic?.clinic_id || ...,
    specialty_id: doctor?.specialty_id || '',
    doctor_id: doctor?.doctor_id || ...,
    patient_id: patient?.patient_id || ...,
    doctor_name: extractDoctorName(doctor) || '',
    specialty_name: doctor?.specialty_name || '',
    date: selectedDate   // <-- НОВОЕ ПОЛЕ
  });
}
```

---

## 6. Модификации степпера

Файл: [`src/web/static/app/js/components/stepper.js`](src/web/static/app/js/components/stepper.js)

### 6.1 Новое свойство шага: `type`

Добавить поддержку `step.type`:

| Значение                                 | Поведение                                                                                       |
| ---------------------------------------- | ----------------------------------------------------------------------------------------------- |
| `'list'` (по умолчанию, если не указано) | Текущее поведение: список элементов, выбор кликом, авто-переход                                 |
| `'widget'`                               | Кастомный виджет: `renderItem` рендерится напрямую, кнопка «Далее» видна, авто-переход подавлен |

### 6.2 Изменения в `render()`

Строка `149` (вычисление `nextBtnClass`):

```js
// БЫЛО:
const isLastStep = currentStep === steps.length - 1;
const nextBtnClass = isLastStep ? '' : ' stepper__btn--next';

// СТАЛО:
const isWidget = step.type === 'widget';
const isLastStep = currentStep === steps.length - 1;
const nextBtnClass = isLastStep || isWidget ? '' : ' stepper__btn--next';
```

Кнопка «Далее» на widget-шаге:

```js
// БЫЛО:
<button class="btn btn--primary${nextBtnClass}" id="stepper-next"${isLastStep ? '' : ' disabled'}>

// СТАЛО (для widget шага кнопка enabled):
<button class="btn btn--primary${nextBtnClass}" id="stepper-next"${(isLastStep || isWidget) ? '' : ' disabled'}>
```

### 6.3 Изменения в `updateContent()`

После строки `308` (`const isLastStep = ...`), добавить:

```js
// Widget-шаг: рендерим напрямую, не как список
const isWidget = steps[currentStep].type === 'widget';
if (isWidget && stepData.length > 0) {
  contentEl.innerHTML = steps[currentStep].renderItem(stepData[0]);
  setupSearchListener();
  return;
}
```

Та же проверка `isWidget` в начале `updateContent()` (перед остальной логикой).

### 6.4 Подавление авто-перехода для widget

Строка `353` (авто-переход при единственном элементе):

```js
// БЫЛО:
if (
  stepData.length === 1 &&
  items.length === 1 &&
  _currentSearchMode !== 'doctors'
) {

// СТАЛО:
const isWidget = steps[currentStep].type === 'widget';
if (
  stepData.length === 1 &&
  items.length === 1 &&
  _currentSearchMode !== 'doctors' &&
  !isWidget
) {
```

### 6.5 Обработчик кнопки «Далее» для widget

В `bindEvents()`, в существующем обработчике `nextBtn` (`click`):

```js
if (nextBtn) {
  nextBtn.addEventListener('click', () => {
    const isWidget = steps[currentStep].type === 'widget';
    if (isWidget) {
      // Для widget: выбранное значение уже в stepData[0] (изменено виджетом)
      advanceStep(0);
      return;
    }
    if (currentStep === steps.length - 1) {
      if (onComplete) {
        onComplete(selections);
      }
    }
  });
}
```

### 6.6 Обработчик «Назад» для widget

Текущий обработчик кнопки «Назад» (`backBtn`) уже корректно обрабатывает возврат (pop из selections, уменьшение currentStep). Дополнительных изменений не требуется, так как widget-шаг не добавляет особой логики возврата.

---

## 7. Интеграция в [`add.js`](src/web/static/app/js/views/add.js)

### 7.1 Новый шаг (вставка после пациента)

```js
const steps = [
  {
    // [0] Пациент — без изменений
    title: 'Выберите пациента',
    description: 'Для кого отслеживать врача?',
    loadData: loadPatients,
    renderItem: renderPatientItem
  },
  {
    // [1] НОВЫЙ ШАГ: Выбор даты
    type: 'widget',
    title: 'Выберите дату',
    description: 'На какую дату искать приём?',
    loadData: async (selections) => {
      // selectedDate — переменная в замыкании renderAddDoctor
      return [{ value: { date: selectedDate || '' }, label: '' }];
    },
    renderItem: (item) => {
      return renderDatePickerWidget(item);
    }
  },
  {
    // [2] Клиника / Поиск врача (бывший [1])
    // ... без изменений, но индексы selections сдвинуты на +1
    title: 'Поиск врача'
    // ... все loadData(selections) теперь читают selections[0] для пациента
    // ... и selections[2] (было selections[1]) для клиники
  },
  {
    // [3] Врач (бывший [2])
    // ... без изменений, но индексы сдвинуты
  },
  {
    // [4] Подтверждение (бывший [3])
    // ... добавить отображение даты
  }
];
```

### 7.2 Функция `renderDatePickerWidget(item)`

Добавляется в [`add.js`](src/web/static/app/js/views/add.js) (или импортируется из `calendar.js`):

```js
import { createDatePicker } from '../components/calendar.js';

function renderDatePickerWidget(item) {
  // Уникальный id контейнера (чтобы не пересекаться при перерендере)
  const containerId = 'date-picker-widget';

  // Возвращаем HTML с контейнером; инициализация через setTimeout
  // (степпер сначала вставит HTML, потом мы найдём контейнер)
  setTimeout(() => {
    const container = document.getElementById(containerId);
    if (!container) return;

    const picker = createDatePicker({
      container,
      value: item.value?.date || '',
      onChange: (dateStr) => {
        // Мутируем item.value — степпер прочитает его при advanceStep
        item.value.date = dateStr;
        // Сохраняем в замыкание для восстановления при возврате
        selectedDate = dateStr;
      },
      min: getTodayISO(), // Нельзя выбрать дату в прошлом
      max: getMaxDateISO() // Например, +3 месяца
    });

    picker.focus();
  }, 0);

  return `<div class="date-picker" id="${containerId}"></div>`;
}
```

### 7.3 Переменная `selectedDate` в замыкании

В `renderAddDoctor(container)`:

```js
// Существующие переменные:
let selectedPatient = null;
let selectedClinic = null;
let selectedDoctor = null;

// НОВАЯ:
let selectedDate = '';
```

### 7.4 Обновление индексов в существующих функциях

**`loadClinics(selections)`, `loadDoctors(selections)`, `searchDoctorsGlobally(selections)`:**

- Пациент: `selections[0]` (без изменений).
- Клиника (для `loadDoctors`): `selections[2]?.value` (было `selections[1]`).
- Шаг подтверждения: `selections[2]` — клиника/врач (было `selections[1]`), `selections[3]` — врач (было `selections[2]`).

**`renderConfirmation(item)`:**
Добавить строку с датой:

```js
// Внутри confirm-card__details, после пациента:
<div class="confirm-label">
  <span class="lucide-icon">${lucideIcon('calendar', 14)}</span> Дата приёма
</div>
<div class="confirm-value">${escapeHtml(item.date || 'Не выбрана')}</div>
```

При этом `item` для подтверждения должно содержать `date`. В `loadData` шага подтверждения:

```js
loadData: async (selections) => {
  const patient = selections[0]?.value || {};
  const dateSelection = selections[1]?.value || {};
  let clinic, doctor;
  if (selections.length >= 4 && !selections[2]?._skipNext) {
    doctor = selections[3]?.value || {};
    clinic = selections[2]?.value || {};
  } else {
    doctor = selections[2]?.value || {};
    clinic = { name: doctor?.clinic_name || '', ... };
  }

  return [{
    _confirm: true,
    patient,
    date: dateSelection.date || '',
    clinic,
    doctor,
    _skipNext: selections[2]?._skipNext
  }];
},
```

### 7.5 `onComplete` — добавление даты в POST

```js
onComplete: async (selections) => {
  const patient = selections[0]?.value;
  const dateSelection = selections[1]?.value; // { date: '15.06.2026' }
  const selectedDate = dateSelection?.date || '';

  let clinic, doctor;
  if (selections.length >= 4 && !selections[2]?._skipNext) {
    clinic = selections[2]?.value;
    doctor = selections[3]?.value;
  } else {
    doctor = selections[2]?.value;
    clinic = {
      clinic_id: doctor?.clinic_id || '',
      short_name: doctor?.clinic_name || '',
      name: doctor?.clinic_name || ''
    };
  }

  // ... существующая логика ...

  await apiPost('/doctors/add', {
    clinic_id: clinic?.clinic_id || clinic?.id || String(clinic || ''),
    specialty_id: doctor?.specialty_id || '',
    doctor_id: doctor?.doctor_id || doctor?.id || String(doctor || ''),
    patient_id: patient?.patient_id || patient?.id || String(patient || ''),
    doctor_name: extractDoctorName(doctor) || '',
    specialty_name: doctor?.specialty_name || '',
    date: selectedDate // <-- НОВОЕ ПОЛЕ
  });
};
```

---

## 8. CSS-архитектура

Файл: [`src/web/static/app/css/style.css`](src/web/static/app/css/style.css) — добавить в конец.

### 8.1 Новые CSS-переменные (добавить в `:root`)

```css
:root {
  /* ... существующие переменные ... */

  /* Календарь */
  --calendar-day-size: 40px;
  --calendar-gap: 4px;
  --calendar-today-border: #09b653;
  --calendar-other-month: #4a5568;
  --calendar-weekday: #6a7a8a;
}
```

Альтернативно, использовать существующие переменные:

- `--tg-bg-color` — фон календаря.
- `--tg-secondary-bg-color` — фон ячеек дней (не выбранных).
- `--tg-button-color` — фон выбранного дня.
- `--tg-button-text-color` — текст выбранного дня.
- `--tg-hint-color` — дни соседних месяцев.
- `--tg-destructive-color` — ошибка валидации.
- `--card-radius` — скругление ячеек.
- `--card-padding` — отступы внутри виджета.

### 8.2 Блок `.calendar`

```css
/* === Календарь === */
.calendar {
  width: 100%;
  max-width: 320px;
  margin: 0 auto;
}

.calendar__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--gap-md);
}

.calendar__nav {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: none;
  border-radius: 8px;
  background-color: var(--tg-secondary-bg-color);
  color: var(--tg-text-color);
  font-size: 18px;
  cursor: pointer;
  transition: opacity 0.15s;
}

.calendar__nav:disabled {
  opacity: 0.3;
  cursor: default;
}

.calendar__nav:focus-visible {
  outline: 2px solid var(--tg-button-color);
  outline-offset: 1px;
}

.calendar__month-label {
  font-size: var(--font-md);
  font-weight: 600;
  color: var(--tg-text-color);
  text-transform: capitalize;
}

.calendar__weekdays {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: var(--calendar-gap);
  margin-bottom: var(--gap-sm);
  text-align: center;
}

.calendar__weekdays span {
  font-size: var(--font-sm);
  color: var(--calendar-weekday);
  font-weight: 500;
  padding: 4px 0;
}

.calendar__grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: var(--calendar-gap);
}

.calendar__day {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  aspect-ratio: 1;
  min-width: var(--calendar-day-size);
  min-height: var(--calendar-day-size);
  border: 1px solid transparent;
  border-radius: 8px;
  background-color: var(--tg-secondary-bg-color);
  color: var(--tg-text-color);
  font-size: var(--font-sm);
  font-weight: 500;
  cursor: pointer;
  transition:
    background-color 0.15s,
    border-color 0.15s;
}

.calendar__day:hover:not(.calendar__day--selected):not(.calendar__day--disabled) {
  background-color: rgb(9 182 83 / 18%);
}

.calendar__day:focus-visible {
  outline: 2px solid var(--tg-button-color);
  outline-offset: 1px;
}

.calendar__day--today {
  border-color: var(--calendar-today-border);
}

.calendar__day--selected {
  background-color: var(--tg-button-color);
  color: var(--tg-button-text-color);
  font-weight: 600;
}

.calendar__day--other-month {
  color: var(--calendar-other-month);
  background-color: transparent;
  border-color: transparent;
}

.calendar__day--disabled {
  opacity: 0.35;
  cursor: default;
  color: var(--tg-hint-color);
}
```

### 8.3 Блок `.date-input`

```css
/* === Поле ввода даты === */
.date-input {
  width: 100%;
  margin-bottom: var(--gap-lg);
}

.date-input__field {
  width: 100%;
  padding: var(--gap-md) var(--card-padding);
  border-radius: var(--card-radius);
  border: 1px solid rgb(0 0 0 / 12%);
  background-color: var(--tg-secondary-bg-color);
  color: var(--tg-text-color);
  font-size: var(--font-lg);
  font-family: inherit;
  text-align: center;
  letter-spacing: 2px;
  transition: border-color 0.2s;
}

.date-input__field::placeholder {
  color: var(--tg-hint-color);
  letter-spacing: 0;
}

.date-input__field:focus {
  outline: none;
  border-color: var(--tg-button-color);
}

.date-input__field--error {
  border-color: var(--tg-destructive-color);
}

.date-input__error {
  color: var(--tg-destructive-color);
  font-size: var(--font-sm);
  margin-top: var(--gap-xs);
  text-align: center;
}

.date-input__error[hidden] {
  display: none;
}
```

### 8.4 Блок `.date-picker`

```css
/* === Виджет выбора даты (композит) === */
.date-picker {
  width: 100%;
  padding: var(--card-padding);
}
```

---

## 9. Утилитные функции в [`calendar.js`](src/web/static/app/js/components/calendar.js)

```js
/**
 * Форматирует Date → 'ДД.ММ.ГГГГ'.
 * @param {Date} date
 * @returns {string}
 */
function formatDate(date) { ... }

/**
 * Парсит 'ДД.ММ.ГГГГ' → { day, month, year }.
 * @param {string} str
 * @returns {{ day: number, month: number, year: number } | null}
 */
function parseDate(str) { ... }

/**
 * Возвращает 'YYYY-MM-DD' (ISO) для сегодняшней даты.
 * @returns {string}
 */
function getTodayISO() { ... }

/**
 * Проверяет, находится ли 'YYYY-MM-DD' в диапазоне [min, max].
 * @param {string} dateISO
 * @param {string} [minISO]
 * @param {string} [maxISO]
 * @returns {boolean}
 */
function isDateInRange(dateISO, minISO, maxISO) { ... }

/**
 * Возвращает массив из 42 дней (6 недель × 7 дней) для календарной сетки.
 * @param {number} year
 * @param {number} month — 1-based (1-12)
 * @returns {Array<{ day: number, month: number, year: number, isCurrentMonth: boolean, iso: string }>}
 */
function getCalendarDays(year, month) { ... }

/**
 * Возвращает названия дней недели (краткие, Пн-Вс).
 * @returns {string[]}
 */
function getWeekdayNames() { ... }

/**
 * Возвращает название месяца на русском.
 * @param {number} month — 1-based
 * @returns {string}
 */
function getMonthName(month) { ... }
```

---

## 10. План тестирования

### 10.1 Unit-тесты (design lab)

Создать страницу в `_design_lab/calendar/index.html` для ручного тестирования компонентов изолированно:

- Тест календаря: навигация по месяцам, выбор даты, today, disabled days.
- Тест поля ввода: маска, валидация, граничные случаи (31 февраля, пустой ввод).
- Тест виджета: двунаправленная связь, смена даты в календаре → инпут и наоборот.

### 10.2 Интеграционное тестирование

После интеграции в степпер проверить:

1. **Прямой проход:** пациент → дата → клиника → врач → подтверждение. Дата отображается на подтверждении.
2. **Возврат и изменение:** на шаге клиники нажать «Назад» → изменить дату → «Далее» → новая дата сохранена.
3. **Сброс степпера:** `reset()` → календарь сбрасывается.
4. **Граничные случаи:**
   - Минимальная дата (сегодня) — нельзя выбрать вчера.
   - Максимальная дата (+3 месяца) — нельзя выбрать дальше.
   - 29 февраля в високосный/невисокосный год.
   - Ввод некорректной даты → ошибка, кнопка «Далее» заблокирована.
5. **Клавиатурная навигация:** Tab/Enter на календаре, стрелки.
6. **Мобильный вид:** календарь не вылезает за границы на узких экранах (320px).

### 10.3 Бэкенд: проверка сохранения `date`

После реализации бэкенд-изменений (секция 12):

- Вызвать `POST /api/user/doctors/add` с полем `date: "15.06.2026"`.
- Проверить через `GET /api/user/doctors?patient_id=...`, что запись содержит `date`.
- Проверить SQLite напрямую: `SELECT date FROM user_monitoring WHERE uid = ...`.

---

## 11. Сводка изменений (Checklist для Code Mode)

### Новые файлы

- [ ] [`src/web/static/app/js/components/calendar.js`](src/web/static/app/js/components/calendar.js) — `createCalendar()`, `createDateInput()`, `createDatePicker()` + утилиты.
- [ ] [`_design_lab/calendar/index.html`](_design_lab/calendar/index.html) — страница для изолированного тестирования.

### Изменяемые файлы — Фронтенд

- [ ] [`src/web/static/app/js/components/stepper.js`](src/web/static/app/js/components/stepper.js):
  - `step.type === 'widget'` в `render()` — показать кнопку «Далее», enabled.
  - `step.type === 'widget'` в `updateContent()` — прямой рендеринг, не список.
  - `step.type === 'widget'` в авто-переходе — подавить.
  - `step.type === 'widget'` в `bindEvents()` — обработчик кнопки «Далее» → `advanceStep(0)`.
- [ ] [`src/web/static/app/js/views/add.js`](src/web/static/app/js/views/add.js):
  - Добавить `import { createDatePicker } from '../components/calendar.js'`.
  - Добавить `let selectedDate = ''`.
  - Вставить новый шаг `type: 'widget'` в `steps` после пациента.
  - Сдвинуть индексы в `loadData` для клиники/врача/подтверждения.
  - Обновить `renderConfirmation` — добавить строку с датой.
  - Обновить `onComplete` — читать `selections[1]`, добавить `date` в POST.
- [ ] [`src/web/static/app/css/style.css`](src/web/static/app/css/style.css):
  - Добавить CSS-переменные для календаря (5 новых в `:root`).
  - Добавить блок `.calendar` (≈120 строк).
  - Добавить блок `.date-input` (≈50 строк).
  - Добавить блок `.date-picker` (≈5 строк).

### Изменяемые файлы — Бэкенд

- [ ] [`src/database/types.py`](src/database/types.py:32) — добавить `date: str` в `MonitoringEntry`.
- [ ] [`src/database/repo_monitoring.py`](src/database/repo_monitoring.py:36) — добавить параметр `date: str`, колонку `date` в SQL.
- [ ] [`src/database/database.py`](src/database/database.py:134) — пробросить `date` в вызов `self.monitoring.add_monitoring_entry()`.
- [ ] [`src/database/migrations.py`](src/database/migrations.py) — новая миграция: `ALTER TABLE user_monitoring ADD COLUMN date TEXT DEFAULT ''`.
- [ ] [`src/database/manager.py`](src/database/manager.py:258) — добавить `date: str` в сигнатуру `toggle_monitoring()`, сохранять в `MonitoringEntry`.
- [ ] [`src/web/routers/user_api.py`](src/web/routers/user_api.py:54) — добавить `date: str = Field(default="")` в `AddDoctorRequest`, пробросить в `toggle_monitoring()`.
- [ ] [`src/handlers/common.py`](src/handlers/common.py:750) — обновить вызов `toggle_monitoring()` → добавить `date=""`.
- [ ] [`src/handlers/mini_app.py`](src/handlers/mini_app.py:103) — обновить вызов `toggle_monitoring()` → добавить `date=""`.

---

## 12. Результат аудита бэкенда: поле `date` отсутствует

Проведён аудит кодовой базы. Поле `date` **полностью отсутствует** на всех уровнях бэкенда:

| Уровень           | Файл                                                    | Строка                                   | Текущее состояние                                                              |
| ----------------- | ------------------------------------------------------- | ---------------------------------------- | ------------------------------------------------------------------------------ |
| Pydantic-модель   | [`user_api.py`](src/web/routers/user_api.py)            | [54](src/web/routers/user_api.py:54)     | `AddDoctorRequest` — нет поля `date`                                           |
| TypedDict         | [`types.py`](src/database/types.py)                     | [32](src/database/types.py:32)           | `MonitoringEntry` — только `name`, `clinic_id`, `specialty`                    |
| SQL-таблица       | [`repo_monitoring.py`](src/database/repo_monitoring.py) | [47](src/database/repo_monitoring.py:47) | Колонки: `uid, p_id, d_id, name, clinic_id, specialty`                         |
| Manager           | [`manager.py`](src/database/manager.py)                 | [258](src/database/manager.py:258)       | `toggle_monitoring(uid, p_id, d_id, d_name, clinic_id, d_spec)` — 6 параметров |
| Telegram-хендлер  | [`common.py`](src/handlers/common.py)                   | [750](src/handlers/common.py:750)        | Вызов без `date`                                                               |
| Mini App fallback | [`mini_app.py`](src/handlers/mini_app.py)               | [103](src/handlers/mini_app.py:103)      | Вызов без `date`                                                               |

### Необходимые изменения (детально)

#### 12.1 [`types.py`](src/database/types.py:32) — TypedDict

```python
class MonitoringEntry(TypedDict):
    name: str
    clinic_id: str
    specialty: str
    date: str          # <-- ДОБАВИТЬ
```

#### 12.2 [`repo_monitoring.py`](src/database/repo_monitoring.py:36) — SQL + метод

```python
async def add_monitoring_entry(
    self, uid: str, p_id: str, d_id: str,
    name: str, clinic_id: str, specialty: str,
    date: str = "",     # <-- ДОБАВИТЬ параметр
) -> None:
    await self._c.execute(
        """INSERT OR REPLACE INTO user_monitoring
           (uid, p_id, d_id, name, clinic_id, specialty, date)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",       # <-- +1 placeholder
        (uid, p_id, d_id, name, clinic_id, specialty, date),
    )
```

Также обновить `get_monitoring()` (строка 30-32) — добавить `"date": row["date"]` в возвращаемый словарь.

#### 12.3 [`database.py`](src/database/database.py:134) — проброс

```python
async def add_monitoring_entry(
    self, uid: str, p_id: str, d_id: str,
    name: str, clinic_id: str, specialty: str,
    date: str = "",     # <-- ДОБАВИТЬ
) -> None:
    return await self.monitoring.add_monitoring_entry(
        uid, p_id, d_id, name, clinic_id, specialty, date
    )
```

#### 12.4 [`migrations.py`](src/database/migrations.py) — миграция

Добавить новую версию миграции:

```python
{
    "version": <NEXT_VERSION>,
    "description": "Добавление колонки date в user_monitoring",
    "sql": "ALTER TABLE user_monitoring ADD COLUMN date TEXT DEFAULT '';"
}
```

#### 12.5 [`manager.py`](src/database/manager.py:258) — сигнатура + сохранение

```python
async def toggle_monitoring(
    self, uid: str, p_id: str, d_id: str,
    d_name: str, clinic_id: str, d_spec: str,
    date: str = "",     # <-- ДОБАВИТЬ
) -> None:
    # ...
    else:
        mon_entry: MonitoringEntry = {
            "name": d_name,
            "clinic_id": clinic_id,
            "specialty": d_spec,
            "date": date,           # <-- ДОБАВИТЬ
        }
        # ...
        await self._db.add_monitoring_entry(
            uid=uid, p_id=p_id, d_id=d_id,
            name=d_name, clinic_id=clinic_id,
            specialty=d_spec, date=date,    # <-- ДОБАВИТЬ date
        )
```

#### 12.6 [`user_api.py`](src/web/routers/user_api.py:54) — Pydantic + вызов

```python
class AddDoctorRequest(BaseModel):
    clinic_id: str = Field(...)
    specialty_id: str = Field(default="")
    doctor_id: str = Field(...)
    patient_id: str = Field(...)
    doctor_name: str = Field(default="")
    specialty_name: str = Field(default="")
    date: str = Field(default="")       # <-- ДОБАВИТЬ
```

В обработчике (строка 285):

```python
await db.toggle_monitoring(
    uid=telegram_id,
    p_id=body.patient_id,
    d_id=body.doctor_id,
    d_name=doctor_name,
    clinic_id=body.clinic_id,
    d_spec=specialty_name,
    date=body.date,         # <-- ДОБАВИТЬ
)
```

#### 12.7 [`common.py`](src/handlers/common.py:750) и [`mini_app.py`](src/handlers/mini_app.py:103)

Добавить `date=""` во все существующие вызовы `toggle_monitoring()` (сохраняя обратную совместимость — параметр со значением по умолчанию).

---

## 13. Уточнённые проектные решения

На основании анализа кодовой базы:

1. **Диапазон дат:** `min = сегодня` (ISO), `max = сегодня + 3 месяца`. Ограничение только на фронте (календарь), бэкенд не валидирует.
2. **Поле `date` в API:** требует полной сквозной доработки бэкенда (см. секцию 12). Все 8 файлов бэкенда включены в скоуп.
3. **Авто-переход:** пользователь обязан нажать «Далее». Авто-переход не применяется для widget-шагов.
4. **Сброс даты при смене пациента:** дата НЕ сбрасывается. Если пользователь вернулся и поменял пациента — дата сохраняется. Это самое простое и интуитивное поведение.
