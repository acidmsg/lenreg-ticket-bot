/**
 * Компонент карточки врача / слота.
 * Универсальный компонент для отображения информации в виде карточки.
 *
 * @module components/card
 */

import { lucideIcon } from './icon.js';

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
  monitoringId = ''
}) {
  const statusInfo = getStatusInfo(status, freeTickets);

  // Список пациентов с кнопками удаления
  // data-entry-id на карточке = entryId первого пациента (для навигации в слоты)
  const firstEntryId = patients.length > 0 ? patients[0].entryId : '';

  const patientsHtml =
    patients.length > 0
      ? `
      <ul class="monitoring-patients">
        ${patients
          .map(
            (p) => `
          <li class="monitoring-patient">
            <span class="monitoring-patient__icon">${lucideIcon('user', 16)}</span>
            <span class="monitoring-patient__name">${escapeHtml(p.name)}</span>
            <span
              class="monitoring-patient__delete"
              data-entry-id="${escapeHtml(p.entryId)}"
              data-patient-name="${escapeHtml(p.name)}"
              title="Удалить мониторинг для этого пациента"
              role="button"
              tabindex="0"
            >${lucideIcon('trash-2', 16)}</span>
          </li>`
          )
          .join('')}
      </ul>`
      : '';

  // Футер со статусом номерков — синхронизирован с заголовком (ориентируется на status)
  const footerHtml =
    status === 'slots_available' && Number(freeTickets) > 0
      ? `<div class="card__footer card__footer--slots">
        <span class="lucide-icon">${lucideIcon('circle-check', 14)}</span>
        <span style="color: var(--status-available);">Есть номерки! (${freeTickets})</span>
      </div>`
      : `<div class="card__footer card__footer--noslots">
        <span class="lucide-icon">${lucideIcon('circle-x', 14)}</span>
        <span style="color: var(--color-danger); opacity: 0.7;">Номерков на данный момент нет</span>
      </div>`;

  return `
    <div class="card doctor-card" data-entry-id="${escapeHtml(firstEntryId)}">
      <div class="card__header">
        <div>
          <div class="card__title">${escapeHtml(doctorName)}</div>
          <div class="card__subtitle">${escapeHtml(specialty)}</div>
        </div>
        <div class="card__header-actions">
          <button
            class="btn--refresh"
            data-monitoring-id="${escapeHtml(monitoringId)}"
            title="Проверить номерки"
            aria-label="Принудительная проверка номерков"
          >${lucideIcon('refresh-cw', 20)}</button>
          ${
            statusInfo.html
              ? `<span class="status ${statusInfo.class}${statusInfo.pulseClass ? ' ' + statusInfo.pulseClass : ''}">
            ${statusInfo.html}
          </span>`
              : ''
          }
        </div>
      </div>
      ${patientsHtml}
      <div class="card__meta"><span class="lucide-icon">${lucideIcon('hospital', 14)}</span> ${escapeHtml(clinicName)}</div>
      ${footerHtml}
    </div>
  `;
}

/**
 * Создаёт HTML карточки слота (группа по дате + время).
 *
 * @param {object} options — параметры слота
 * @param {string} options.date — дата в формате YYYY-MM-DD
 * @param {string[]} options.times — список времени
 * @returns {string} HTML-строка группы слотов
 */
export function createSlotCard({ date, times }) {
  const formattedDate = formatDate(date);
  const timeChips = times
    .map((time) => `<span class="slot-chip">${escapeHtml(time)}</span>`)
    .join('');

  return `
    <div class="slot-group">
      <div class="slot-group__date">${formattedDate}</div>
      <div class="slot-group__times">${timeChips}</div>
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
    class: 'status--checking',
    html: `<span class="status__dot status__dot--active status__pulse"></span>
      <span class="status__label">мониторинг</span>`,
    pulseClass: 'status__pulse'
  };
}

/**
 * Форматирует дату из YYYY-MM-DD в читаемый вид (ДД.ММ.ГГГГ).
 *
 * @param {string} dateStr — дата в формате YYYY-MM-DD
 * @returns {string} отформатированная дата
 */
function formatDate(dateStr) {
  const parts = dateStr.split('-');
  if (parts.length !== 3) return dateStr;
  const [year, month, day] = parts;
  const months = [
    'января',
    'февраля',
    'марта',
    'апреля',
    'мая',
    'июня',
    'июля',
    'августа',
    'сентября',
    'октября',
    'ноября',
    'декабря'
  ];
  const monthIndex = parseInt(month, 10) - 1;
  const monthName = months[monthIndex] || month;
  return `${parseInt(day, 10)} ${monthName} ${year}`;
}

/**
 * Экранирует HTML-символы.
 *
 * @param {string} text — исходный текст
 * @returns {string} экранированный текст
 */
function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = String(text);
  return div.innerHTML;
}
