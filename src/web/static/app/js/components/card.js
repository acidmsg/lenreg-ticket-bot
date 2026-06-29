/**
 * Компонент карточки врача / слота / бронирования.
 * Универсальный компонент для отображения информации в виде карточки.
 *
 * @module components/card
 */

import { lucideIcon } from "./icon.js";
import { escapeHtml } from "../utils/escape.js";

/**
 * Создаёт HTML карточки врача со списком отслеживающих пациентов.
 *
 * @param {object} options — параметры карточки
 * @param {string} options.doctorName — ФИО врача
 * @param {string} options.specialty — специальность
 * @param {string} options.clinicName — название клиники
 * @param {string} options.status — статус: 'slots_available', 'no_slots', 'checking'
 * @param {number} [options.freeTickets=0] — количество свободных слотов
 * @param {Array<{name: string, patientId: string, entryId: string}>} [options.patients=[]] — пациенты, отслеживающие врача
 * @returns {string} HTML-строка карточки врача
 */
export function createDoctorCard({
  doctorName,
  specialty,
  clinicName,
  status,
  freeTickets = 0,
  patients = [],
  monitoringId = "",
  isMonitored = false,
}) {
  const statusInfo = getStatusInfo(status, freeTickets);

  // Список пациентов с кнопками удаления
  // data-entry-id на карточке = entryId первого пациента (для навигации в слоты)
  const firstEntryId = patients.length > 0 ? patients[0].entryId : "";

  const patientsHtml =
    patients.length > 0
      ? `
      <ul class="monitoring-patients">
        ${patients
          .map(
            (p) => `
          <li class="monitoring-patient">
            <span class="monitoring-patient__icon">${lucideIcon("user", 16)}</span>
            <span class="monitoring-patient__name">${escapeHtml(p.name)}</span>
            <span
              class="monitoring-patient__delete"
              data-entry-id="${escapeHtml(p.entryId)}"
              data-patient-name="${escapeHtml(p.name)}"
              title="Удалить мониторинг для этого пациента"
              role="button"
              tabindex="0"
            >${lucideIcon("trash-2", 16)}</span>
          </li>`,
          )
          .join("")}
      </ul>`
      : "";

  // Индикатор отслеживания (зелёная точка/иконка)
  const monitoredIndicator = isMonitored
    ? `<span class="doctor-card__monitored-badge" title="Врач отслеживается">🔔</span>`
    : "";

  // CSS-класс для отслеживаемого врача
  const monitoredClass = isMonitored ? " doctor-card--monitored" : "";

  // Футер со статусом номерков — синхронизирован с заголовком (ориентируется на status)
  const footerHtml =
    status === "slots_available" && Number(freeTickets) > 0
      ? `<div class="card__footer card__footer--slots">
        <span class="lucide-icon">${lucideIcon("circle-check", 14)}</span>
        <span style="color: var(--status-available);">Есть номерки! (${freeTickets})</span>
      </div>`
      : `<div class="card__footer card__footer--noslots">
        <span class="lucide-icon">${lucideIcon("circle-x", 14)}</span>
        <span style="color: var(--color-danger); opacity: 0.7;">Номерков на данный момент нет</span>
      </div>`;

  return `
    <div class="card doctor-card${monitoredClass}" data-entry-id="${escapeHtml(firstEntryId)}">
      <div class="card__header">
        <div>
          <div class="card__title">${escapeHtml(doctorName)}</div>
          <div class="card__subtitle">${escapeHtml(specialty)}</div>
        </div>
        <div class="card__header-actions">
          ${monitoredIndicator}
          <button
            class="btn--refresh"
            data-monitoring-id="${escapeHtml(monitoringId)}"
            title="Проверить номерки"
            aria-label="Принудительная проверка номерков"
          >${lucideIcon("refresh-cw", 20)}</button>
          ${
            statusInfo.html
              ? `<span class="status ${statusInfo.class}${statusInfo.pulseClass ? " " + statusInfo.pulseClass : ""}">
            ${statusInfo.html}
          </span>`
              : ""
          }
        </div>
      </div>
      ${patientsHtml}
      <div class="card__meta"><span class="lucide-icon">${lucideIcon("hospital", 14)}</span> ${escapeHtml(clinicName)}</div>
      ${footerHtml}
    </div>
  `;
}

/**
 * Создаёт HTML карточки слота (группа по дате + время).
 *
 * @param {object} options — параметры слота
 * @param {string} options.date — дата в формате ДД.ММ.ГГГГ
 * @param {Array<{time: string, appointmentId: string}>} options.slots — слоты
 * @returns {string} HTML-строка группы слотов
 */
export function createSlotCard({ date, slots, clinicId = "" }) {
  const formattedDate = formatDate(date);
  const timeChips = slots
    .map(
      (s) =>
        `<button class="slot-chip slot-chip--clickable" data-slot-date="${escapeHtml(date)}" data-slot-time="${escapeHtml(s.time)}" data-appointment-id="${escapeHtml(s.appointmentId)}" data-clinic-id="${escapeHtml(clinicId)}">${escapeHtml(s.time)}</button>`,
    )
    .join("");

  return `
    <div class="slot-group">
      <div class="slot-group__date">${formattedDate}</div>
      <div class="slot-group__times">${timeChips}</div>
    </div>
  `;
}

/**
 * Создаёт HTML карточки бронирования для экрана «Мои записи».
 *
 * @param {object} booking — данные бронирования из API (GET /api/user/bookings)
 * @param {string} booking.booking_id — ID бронирования
 * @param {string} booking.doctor_name — ФИО врача
 * @param {string} booking.specialty — специальность
 * @param {string} booking.clinic_name — название клиники
 * @param {string} booking.date — дата приёма (ДД.ММ.ГГГГ)
 * @param {string} booking.time — время приёма (ЧЧ:ММ)
 * @param {string} booking.patient_name — имя пациента
 * @param {boolean} booking.is_archived — признак архива
 * @returns {string} HTML-строка карточки бронирования
 */
export function createBookingCard(booking) {
  const bookingId = escapeHtml(booking.booking_id || "");
  const doctorName = escapeHtml(booking.doctor_name || "—");
  const specialty = escapeHtml(booking.specialty || "");
  const clinicName = escapeHtml(booking.clinic_name || "—");
  const date = escapeHtml(booking.date || "");
  const time = escapeHtml(booking.time || "");
  const patientName = escapeHtml(booking.patient_name || "");

  const specialtyLine = specialty
    ? `<div class="booking-card__specialty"><span class="lucide-icon">${lucideIcon("stethoscope", 14)}</span> ${specialty}</div>`
    : "";

  const dateTimeLine = date
    ? `<div class="booking-card__datetime"><span class="lucide-icon">${lucideIcon("calendar", 14)}</span> ${date} в ${time}</div>`
    : "";

  const patientLine = patientName
    ? `<div class="booking-card__patient"><span class="lucide-icon">${lucideIcon("user", 14)}</span> Пациент: ${patientName}</div>`
    : "";

  return `
    <div class="card booking-card" data-booking-id="${bookingId}">
      <div class="booking-card__header">
        <span class="lucide-icon">${lucideIcon("user-round", 18)}</span>
        <span class="booking-card__doctor">${doctorName}</span>
      </div>
      ${specialtyLine}
      <div class="booking-card__clinic"><span class="lucide-icon">${lucideIcon("hospital", 14)}</span> ${clinicName}</div>
      ${dateTimeLine}
      ${patientLine}
      <div class="booking-card__actions">
        <button class="btn btn--sm btn--primary booking-export-btn" data-booking-id="${bookingId}" data-format="png" title="Сохранить карточку">
          <span class="lucide-icon">${lucideIcon("download", 14)}</span> Сохранить
        </button>
        <button class="btn btn--sm btn--outline booking-export-btn" data-booking-id="${bookingId}" data-format="ics" title="Добавить в календарь">
          <span class="lucide-icon">${lucideIcon("calendar-plus", 14)}</span> В календарь
        </button>
      </div>
    </div>
  `;
}

/**
 * Возвращает информацию о статусе для отображения.
 *
 * @param {string} status — статус ('slots_available', 'no_slots', 'checking')
 * @param {number} freeTickets — количество свободных слотов
 * @returns {{ class: string, html: string, pulseClass?: string }}
 */
function getStatusInfo(status, freeTickets) {
  // Все статусы показывают одинаково: зелёная мигающая точка + «мониторинг».
  // Информация о наличии/отсутствии номерков — только в футере карточки.
  return {
    class: "status--checking",
    html: `<span class="status__dot status__dot--active status__pulse"></span>
      <span class="status__label">мониторинг</span>`,
    pulseClass: "status__pulse",
  };
}

/**
 * Форматирует дату из YYYY-MM-DD в читаемый вид (ДД.ММ.ГГГГ).
 *
 * @param {string} dateStr — дата в формате YYYY-MM-DD
 * @returns {string} отформатированная дата
 */
function formatDate(dateStr) {
  const parts = dateStr.split("-");
  if (parts.length !== 3) return dateStr;
  const [year, month, day] = parts;
  const months = [
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
  ];
  const monthIndex = parseInt(month, 10) - 1;
  const monthName = months[monthIndex] || month;
  return `${parseInt(day, 10)} ${monthName} ${year}`;
}
