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

import { createSlotsCalendar } from "./calendar.js";
import { createSlotCard } from "./card.js";

/**
 * Группирует слоты по датам, сохраняя время и данные для бронирования.
 *
 * @param {Array} slots — слоты `[{ date, time, appointment_id, clinic_id }]`
 * @param {string} [fallbackClinicId=""] — ID клиники по умолчанию
 * @returns {Object<string, Array<{time: string, appointmentId: string, clinicId: string}>>}
 *   карта «дата → слоты»
 */
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
      <div class="slots-layout__calendar" id="${rootId}-calendar"></div>
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
      onSelect({
        date: chip.getAttribute("data-slot-date") || "",
        time: chip.getAttribute("data-slot-time") || "",
        appointmentId: chip.getAttribute("data-appointment-id") || "",
        clinicId: chip.getAttribute("data-clinic-id") || "",
      });
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
  { slots, onSelect, rootId = "slots", fallbackClinicId = "" },
) {
  if (typeof VanillaCalendar !== "function") return false;

  const calendarEl = root.querySelector(`#${rootId}-calendar`);
  const panelEl = root.querySelector(`#${rootId}-panel`);
  if (!calendarEl || !panelEl) return false;

  const grouped = groupSlotsByDate(slots, fallbackClinicId);
  const dates = Object.keys(grouped).sort();
  if (dates.length === 0) return false;

  const slotCounts = {};
  dates.forEach((date) => {
    slotCounts[date] = grouped[date].length;
  });

  const renderPanel = (date) => {
    // Клик по недоступной дате сбрасывает selectedDates в null —
    // панель при этом не трогаем, чтобы не терять текущий выбор.
    if (!date) return;
    panelEl.innerHTML = renderSlotsPanel(grouped, date);
    panelEl.classList.add("slots-layout__panel--open");
    bindSlotsPickerChips(panelEl, onSelect);
  };

  const calendar = createSlotsCalendar(calendarEl, {
    slotDates: dates,
    slotCounts,
    onSelect: renderPanel,
  });
  if (!calendar) return false;

  renderPanel(calendar.selectedDates[0] || dates[0]);
  return true;
}
