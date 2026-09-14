/**
 * Базовый компонент календаря Mini App на VanillaCalendar Pro v2.9.10.
 *
 * Единая точка создания экземпляров календаря. Конкретные сценарии
 * (дата рождения пациента, выбор слота) собираются фабриками-обёртками.
 *
 * Внимание: библиотека рендерит календарь в отдельный элемент
 * (в режиме `input: true` — в `document.body`), поэтому класс-модификатор
 * скоупа CSS навешивается на корневой элемент календаря, а не на статичную
 * обёртку в разметке формы.
 *
 * @module components/calendar
 */

/** Класс-модификатор контейнера календаря пациента (скоуп CSS). */
export const PATIENT_CALENDAR_MODIFIER = "calendar--patient";

/** Класс-модификатор контейнера календаря слотов (Этап 3). */
export const SLOTS_CALENDAR_MODIFIER = "calendar--slots";

/** Класс дня, на который есть свободные слоты (индикатор календаря слотов). */
export const SLOTS_DAY_AVAILABLE_CLASS = "slots-day--available";

/** Нижняя граница диапазона даты рождения. */
const PATIENT_BIRTHDATE_MIN = "1900-01-01";

/**
 * Форматирует дату в ISO-строку (YYYY-MM-DD) в локальной зоне.
 *
 * @param {Date} date — дата
 * @returns {string} дата в формате YYYY-MM-DD
 */
function toIsoDate(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

/**
 * Возвращает сегодняшнюю дату в формате YYYY-MM-DD (локальная зона).
 *
 * @returns {string} дата в формате ISO (YYYY-MM-DD)
 */
function getTodayIso() {
  return toIsoDate(new Date());
}

/**
 * Разбирает ISO-дату (YYYY-MM-DD) в объект Date (локальная зона).
 *
 * @param {string} iso — дата в формате YYYY-MM-DD
 * @returns {Date} объект даты
 */
function parseIsoDate(iso) {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(year, month - 1, day);
}

/**
 * Приводит селектор либо DOM-элемент к элементу.
 *
 * @param {string|HTMLElement|null} target — селектор или элемент
 * @returns {HTMLElement|null} найденный элемент либо null
 */
function resolveElement(target) {
  if (!target) return null;
  if (typeof target === "string") return document.querySelector(target);
  return target instanceof HTMLElement ? target : null;
}

/**
 * Создаёт экземпляр VanillaCalendar Pro.
 *
 * @param {string|HTMLElement} containerSelector — селектор или элемент
 *   (при `input: true` — поле ввода, иначе контейнер календаря)
 * @param {object} [options] — параметры календаря
 * @param {boolean} [options.input=false] — режим календаря на поле ввода
 * @param {string|HTMLElement|null} [options.inputElement=null] — явное поле ввода
 *   (альтернатива `containerSelector` в режиме `input: true`)
 * @param {{min?: string, max?: string, disablePast?: boolean}|null} [options.range=null] — диапазон дат
 * @param {Function|null} [options.onSelect=null] — колбэк выбора дня `(date, self, event)`
 * @param {string} [options.theme='dark'] — тема оформления VanillaCalendar
 * @param {string|null} [options.modifierClass=null] — класс-модификатор скоупа CSS
 * @param {string} [options.selectionDay='single'] — режим выбора дней
 * @param {object} [options.actions={}] — дополнительные обработчики VanillaCalendar
 * @returns {VanillaCalendar|null} экземпляр календаря либо null, если элемент не найден
 */
export function createCalendar(containerSelector, options = {}) {
  const {
    input = false,
    inputElement = null,
    range = null,
    onSelect = null,
    theme = "dark",
    modifierClass = null,
    selectionDay = "single",
    actions = {},
  } = options;

  const root = resolveElement(inputElement || containerSelector);
  if (!root) return null;

  const calendar = new VanillaCalendar(root, {
    input,
    settings: {
      lang: "ru",
      selection: { day: selectionDay },
      visibility: { theme },
      ...(range ? { range } : {}),
    },
    actions: {
      // Блокируем выбор дат, отключённых библиотекой (за пределами range).
      // VanillaCalendar Pro v2.9.10 не проверяет dayBtnDisabled в обработчике
      // клика — только добавляет CSS-класс. Сбрасываем selectedDates до
      // changeToInput, чтобы дата вне диапазона не попала в поле ввода.
      clickDay(event, self) {
        const target = event.target;
        if (
          target instanceof HTMLElement &&
          target.classList.contains(self.CSSClasses.dayBtnDisabled)
        ) {
          self.selectedDates = [];
        }
        if (actions.clickDay) actions.clickDay(event, self);
      },
      changeToInput(event, self) {
        if (onSelect) onSelect(self.selectedDates[0] || null, self, event);
        if (actions.changeToInput) actions.changeToInput(event, self);
      },
    },
  });

  calendar.init();

  if (modifierClass && calendar.HTMLElement) {
    calendar.HTMLElement.classList.add(modifierClass);
  }

  return calendar;
}

/**
 * Создаёт календарь даты рождения пациента.
 *
 * Диапазон: 1900-01-01 … сегодня. Значение поля ввода — в формате ДД.ММ.ГГГГ.
 *
 * @param {string|HTMLElement} inputSelector — поле ввода даты рождения
 * @param {Function|null} [onSelect=null] — дополнительный колбэк выбора
 * @returns {VanillaCalendar|null} экземпляр календаря
 */
export function createPatientCalendar(inputSelector, onSelect = null) {
  return createCalendar(inputSelector, {
    input: true,
    modifierClass: PATIENT_CALENDAR_MODIFIER,
    range: {
      min: PATIENT_BIRTHDATE_MIN,
      max: getTodayIso(),
      disablePast: false,
    },
    onSelect(date, self) {
      if (!date) return;

      const [year, month, day] = date.split("-");
      self.HTMLInputElement.value = `${day}.${month}.${year}`;
      // Флаг предотвращает обратную синхронизацию (маска → календарь)
      // при программной установке значения из календаря
      self.HTMLInputElement._fromCalendar = true;
      self.hide();

      if (onSelect) onSelect(date, self);
    },
  });
}

/**
 * Находит кнопку дня среди аргументов обработчика `actions.getDays`.
 *
 * Сигнатура `getDays` в VanillaCalendar Pro v2.9.10:
 * `(dayNumber, dateISO, dayCell, dayButton, self)`. Кнопка определяется
 * по классу, а не по позиции, чтобы не зависеть от порядка аргументов.
 *
 * @param {Array} args — аргументы обработчика
 * @returns {HTMLButtonElement|null} кнопка дня либо null
 */
function findDayButton(args) {
  return (
    args.find(
      (arg) =>
        arg instanceof HTMLElement &&
        arg.classList.contains("vanilla-calendar-day__btn"),
    ) || null
  );
}

/**
 * Собирает ISO-даты диапазона, на которые нет слотов.
 *
 * @param {string} minIso — нижняя граница (YYYY-MM-DD)
 * @param {string} maxIso — верхняя граница (YYYY-MM-DD)
 * @param {Set<string>} slotDateSet — множество дат со слотами
 * @returns {string[]} список недоступных дат
 */
function collectDisabledDates(minIso, maxIso, slotDateSet) {
  const disabled = [];
  const cursor = parseIsoDate(minIso);
  const end = parseIsoDate(maxIso);
  while (cursor <= end) {
    const iso = toIsoDate(cursor);
    if (!slotDateSet.has(iso)) disabled.push(iso);
    cursor.setDate(cursor.getDate() + 1);
  }
  return disabled;
}

/**
 * Создаёт календарь слотов для записи (Этап 3, T-08).
 *
 * Per-day состояния: дни со слотами помечаются классом
 * `slots-day--available` (индикатор точки/кольца), дни без слотов и
 * прошедшие — недоступны. Диапазон ограничен сегодняшней датой и
 * последней датой со слотами, поэтому навигация не выходит за пределы
 * доступных данных.
 *
 * @param {string|HTMLElement} containerSelector — контейнер календаря
 * @param {object} [options] — параметры календаря
 * @param {string} [options.min] — нижняя граница диапазона (по умолчанию — сегодня)
 * @param {string|null} [options.max=null] — верхняя граница диапазона (YYYY-MM-DD)
 * @param {string[]} [options.slotDates=[]] — ISO-даты, на которые есть слоты
 * @param {Object<string, number>} [options.slotCounts={}] — количество слотов по датам
 * @param {string|null} [options.selectedDate=null] — предвыбранная дата
 * @param {Function|null} [options.onSelect=null] — колбэк выбора дня `(date, self, event)`
 * @param {string} [options.modifierClass] — класс-модификатор скоупа CSS
 * @returns {VanillaCalendar|null} экземпляр календаря
 */
export function createSlotsCalendar(containerSelector, options = {}) {
  const {
    min = getTodayIso(),
    max = null,
    slotDates = [],
    slotCounts = {},
    selectedDate = null,
    onSelect = null,
    modifierClass = SLOTS_CALENDAR_MODIFIER,
  } = options;

  const slotDateSet = new Set(slotDates);
  const futureSlotDates = slotDates.filter((iso) => iso >= min).sort();
  const rangeMax = max || futureSlotDates[futureSlotDates.length - 1] || min;
  const disabledDates = collectDisabledDates(min, rangeMax, slotDateSet);
  const initialDate =
    selectedDate && slotDateSet.has(selectedDate)
      ? selectedDate
      : futureSlotDates[0] || null;

  const calendar = createCalendar(containerSelector, {
    modifierClass,
    range: {
      min,
      max: rangeMax,
      disablePast: false,
      // Дни без слотов → недоступны (штатный механизм range.disabled).
      disabled: disabledDates,
    },
    actions: {
      // Пометка дней со слотами. VanillaCalendar Pro v2.9.10 не имеет
      // опции `modifiers`, поэтому используется штатный хук `actions.getDays`.
      getDays(...args) {
        const button = findDayButton(args);
        const iso = button?.dataset.calendarDay;
        if (!button || !iso || iso < min || iso > rangeMax) return;
        if (!slotDateSet.has(iso)) return;
        button.classList.add(SLOTS_DAY_AVAILABLE_CLASS);
        const count = slotCounts[iso];
        if (count) button.dataset.slotCount = String(count);
      },
      // В контейнерном режиме `changeToInput` не вызывается — выбор даты
      // пробрасывается через `clickDay` (selectedDates уже обновлён библиотекой).
      clickDay(event, self) {
        if (onSelect) onSelect(self.selectedDates[0] || null, self, event);
      },
    },
  });

  if (!calendar) return null;

  if (initialDate) {
    calendar.selectedDates = [initialDate];
    calendar.selectedYear = Number(initialDate.slice(0, 4));
    calendar.selectedMonth = Number(initialDate.slice(5, 7)) - 1;
    calendar.update();
  }

  return calendar;
}
