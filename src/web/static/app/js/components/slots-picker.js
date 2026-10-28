/**
 * Переиспользуемый компонент выбора свободного слота.
 *
 * Выделен из экрана слотов (`views/slots.js`), чтобы один и тот же UI
 * (календарь + панель выбранной даты + чипы времени) использовался на экране
 * слотов, на шаге подтверждения мастера и в карточке врача — без копирования
 * разметки.
 *
 * Компонент не знает про бронирование: наружу отдаётся выбранный слот
 * `{ date, time, appointmentId, clinicId }` через колбэк.
 *
 * @module components/slots-picker
 */

import { createSlotCard } from "./card.js";

/**
 * Группирует слоты по датам, сохраняя время и данные для бронирования.
 *
 * @param {Array} slots — слоты `[{ date, time, appointment_id, clinic_id }]`
 * @param {string} [fallbackClinicId=""] — ID клиники по умолчанию
 * @returns {Object<string, Array<{time: string, appointmentId: string, clinicId: string}>>}
 *   карта «дата → слоты»
 */
/** Дни недели для ленты дат. */
const WEEKDAYS = ["вс", "пн", "вт", "ср", "чт", "пт", "сб"];

export function groupSlotsByDate(slots, fallbackClinicId = "") {
  const grouped = {};
  (slots || []).forEach((slot) => {
    const date = slot.date || "";
    if (!date) return;
    if (!grouped[date]) grouped[date] = [];
    grouped[date].push({
      time: slot.time || "—",
      appointmentId: slot.appointment_id || slot.slot_id || "",
      clinicId: slot.clinic_id || fallbackClinicId || "",
    });
  });
  return grouped;
}

/**
 * Рендерит гибридную раскладку: календарь + панель слотов выбранной даты.
 *
 * @param {string} [rootId="slots"] — префикс идентификаторов (для нескольких
 *   экземпляров компонента на странице)
 * @returns {string} HTML раскладки
 */
export function renderSlotsPickerLayout(rootId = "slots") {
  return `
    <div class="slots-layout">
      <div class="day-strip" id="${rootId}-calendar" role="tablist" aria-label="Дни с номерами"></div>
      <div class="slots-layout__panel" id="${rootId}-panel"></div>
    </div>
  `;
}

/**
 * Рендерит слоты выбранной даты для панели.
 *
 * @param {Object} grouped — карта «дата → слоты»
 * @param {string} date — выбранная дата (YYYY-MM-DD)
 * @returns {string} HTML панели
 */
export function renderSlotsPanel(grouped, date) {
  const daySlots = grouped[date] || [];
  if (date && daySlots.length > 0) {
    return createSlotCard({ date, slots: daySlots });
  }
  return `
    <div class="slots-panel__empty">
      На выбранную дату свободных номерков нет
    </div>
  `;
}

/**
 * Рендерит плоский список слотов по датам (fallback без календаря).
 *
 * @param {Array} slots — массив слотов
 * @param {string} [fallbackClinicId=""] — ID клиники по умолчанию
 * @returns {string} HTML списка слотов
 */
export function renderSlotList(slots, fallbackClinicId = "") {
  const grouped = groupSlotsByDate(slots, fallbackClinicId);
  const sortedDates = Object.keys(grouped).sort();

  const groupsHtml = sortedDates
    .map((date) => createSlotCard({ date, slots: grouped[date] }))
    .join("");

  return `
    ${groupsHtml}
    <p class="text-center mt-md" style="color: var(--color-text-secondary); font-size: var(--font-sm);">
      Выберите удобное время для записи
    </p>
  `;
}

/**
 * Привязывает обработчики кликов по чипам времени.
 *
 * @param {HTMLElement} root — корень, внутри которого ищутся чипы
 * @param {Function} onSelect — колбэк выбора слота
 */
export function bindSlotsPickerChips(root, onSelect) {
  root.querySelectorAll(".slot-chip--clickable").forEach((chip) => {
    chip.addEventListener("click", () => {
      onSelect(
        {
          date: chip.getAttribute("data-slot-date") || "",
          time: chip.getAttribute("data-slot-time") || "",
          appointmentId: chip.getAttribute("data-appointment-id") || "",
          clinicId: chip.getAttribute("data-clinic-id") || "",
        },
        chip,
      );
    });
  });
}

/**
 * Инициализирует календарь и панель выбранной даты.
 *
 * @param {HTMLElement} root — корень компонента
 * @param {object} options — параметры
 * @param {Array} options.slots — массив слотов
 * @param {Function} options.onSelect — колбэк выбора слота
 * @param {string} [options.rootId="slots"] — префикс идентификаторов
 * @param {string} [options.fallbackClinicId=""] — ID клиники по умолчанию
 * @returns {boolean} true, если календарь инициализирован
 */
export function initSlotsPicker(
  root,
  { slots, onSelect, rootId = "slots", fallbackClinicId = "", onDayChange = null },
) {
  const stripEl = root.querySelector(`#${rootId}-calendar`);
  const panelEl = root.querySelector(`#${rootId}-panel`);
  if (!stripEl || !panelEl) return false;

  const grouped = groupSlotsByDate(slots, fallbackClinicId);
  const dates = Object.keys(grouped).sort();
  if (dates.length === 0) return false;

  let selectedDate = dates[0];

  const render = () => {
    stripEl.innerHTML = dates
      .map((date) => {
        const parts = date.split("-");
        const dt = new Date(
          Number(parts[0]),
          Number(parts[1]) - 1,
          Number(parts[2]),
        );
        const weekday = WEEKDAYS[dt.getDay()] || "";
        const day = String(dt.getDate());
        const count = grouped[date].length;
        const active = date === selectedDate ? " day-chip--active" : "";
        return `<button type="button" class="day-chip${active}" data-date="${date}" aria-pressed="${date === selectedDate}">
          <span class="day-chip__weekday">${weekday}</span>
          <span class="day-chip__day">${day}</span>
          <span class="day-chip__count">${count}</span>
        </button>`;
      })
      .join("");

    panelEl.innerHTML = renderSlotsPanel(grouped, selectedDate);
    panelEl.classList.add("slots-layout__panel--open");
    bindSlotsPickerChips(panelEl, onSelect);
  };

  stripEl.addEventListener("click", (event) => {
    const chip = event.target.closest(".day-chip");
    if (!chip) return;
    if (typeof onDayChange === "function") onDayChange();
    selectedDate = chip.getAttribute("data-date") || selectedDate;
    render();
  });

  render();
  return true;
}