/**
 * Экран просмотра свободных слотов для отслеживаемого врача.
 * Слоты группируются по датам.
 *
 * @module views/slots
 */

import { apiGet } from '../api.js';
import { isInTelegram } from '../auth.js';
import { createSlotCard } from '../components/card.js';

/**
 * Рендерит экран слотов в указанный контейнер.
 *
 * @param {HTMLElement} container — DOM-элемент для рендеринга
 * @param {object|null} params — параметры маршрута ({ monitoringId })
 */
export async function renderSlots(container, params) {
  if (!container) return;

  const monitoringId = params?.monitoringId;
  if (!monitoringId) {
    container.innerHTML = renderError('Не указан ID отслеживания.');
    return;
  }

  // Показываем спиннер загрузки
  container.innerHTML = renderLoading();

  try {
    const data = await apiGet(
      `/slots?monitoring_id=${encodeURIComponent(monitoringId)}`
    );

    container.innerHTML = renderSlotInfo(data);

    const slots = data.slots || [];
    if (slots.length === 0) {
      container.innerHTML += renderNoSlots();
      return;
    }

    container.innerHTML += renderSlotList(slots);
  } catch (error) {
    container.innerHTML = renderError(error.message);
    bindErrorEvents(container, params);
  }
}

/**
 * Рендерит спиннер загрузки.
 *
 * @returns {string} HTML спиннера
 */
function renderLoading() {
  return `
    <div class="spinner">
      <div class="spinner__icon"></div>
    </div>
  `;
}

/**
 * Рендерит информационный блок о враче (заголовок экрана слотов).
 *
 * @param {object} data — данные ответа API
 * @returns {string} HTML информации
 */
function renderSlotInfo(data) {
  const doctorName = extractDoctorName(data) || 'Врач';
  const specialty = data.specialty || '';
  const clinicName = data.clinic_name || '';
  const total = data.total || 0;

  return `
    <div class="mb-md">
      <div style="font-size: var(--font-lg); font-weight: 600; margin-bottom: 4px;">
        ${escapeHtml(doctorName)}
      </div>
      ${specialty ? `<div class="card__subtitle">${escapeHtml(specialty)}</div>` : ''}
      ${clinicName ? `<div class="card__meta">🏥 ${escapeHtml(clinicName)}</div>` : ''}
      ${total > 0 ? `<div class="status status--available mt-md">🟢 Найдено слотов: ${total}</div>` : ''}
    </div>
  `;
}

/**
 * Рендерит сообщение об отсутствии слотов.
 *
 * @returns {string} HTML
 */
function renderNoSlots() {
  return `
    <div class="empty-state" style="padding-top: 20px;">
      <div class="empty-state__icon">📅</div>
      <p class="empty-state__text">
        На данный момент свободных слотов нет.
        Мы уведомим вас, когда они появятся.
      </p>
    </div>
  `;
}

/**
 * Рендерит список слотов, сгруппированных по датам.
 *
 * @param {Array} slots — массив слотов [{ date, time, clinic_id }]
 * @returns {string} HTML списка слотов
 */
function renderSlotList(slots) {
  // Группируем слоты по дате
  const grouped = {};
  slots.forEach((slot) => {
    const date = slot.date || '—';
    if (!grouped[date]) {
      grouped[date] = [];
    }
    grouped[date].push(slot.time || '—');
  });

  // Сортируем даты
  const sortedDates = Object.keys(grouped).sort();

  const groupsHtml = sortedDates
    .map((date) => createSlotCard({ date, times: grouped[date] }))
    .join('');

  return `
    ${groupsHtml}
    <p class="text-center mt-md" style="color: var(--tg-hint-color); font-size: var(--font-sm);">
      Для записи на приём откройте сайт zdrav.lenreg.ru
    </p>
  `;
}

/**
 * Рендерит сообщение об ошибке.
 *
 * @param {string} message — текст ошибки
 * @returns {string} HTML ошибки
 */
function renderError(message) {
  return `
    <div class="error-state">
      <div class="empty-state__icon">⚠️</div>
      <p class="error-state__text">${escapeHtml(message)}</p>
      <button class="btn btn--primary" id="slots-retry-btn">🔄 Повторить</button>
    </div>
  `;
}

/**
 * Привязывает обработчик кнопки «Повторить».
 *
 * @param {HTMLElement} container — контейнер
 * @param {object|null} params — параметры маршрута
 */
function bindErrorEvents(container, params) {
  const retryBtn = container.querySelector('#slots-retry-btn');
  if (retryBtn) {
    retryBtn.addEventListener('click', () => {
      renderSlots(container, params);
    });
  }
}

/**
 * Извлекает строковое имя врача из поля name, которое может быть объектом.
 *
 * @param {object} doctor — объект врача из API
 * @returns {string} строковое представление имени врача
 */
function extractDoctorName(doctor) {
  const name = doctor.name;
  if (!name) return String(doctor.doctor_name || '');

  // Если name — строка, возвращаем как есть
  if (typeof name === 'string') return name;

  // Если name — объект (например, {first_name: "...", last_name: "..."}),
  // пробуем собрать строку из известных полей
  if (typeof name === 'object' && name !== null) {
    const parts = [];
    if (name.last_name) parts.push(name.last_name);
    if (name.first_name) parts.push(name.first_name);
    if (name.middle_name) parts.push(name.middle_name);
    if (parts.length > 0) return parts.join(' ');
    // Если не удалось извлечь — используем doctor_name как fallback
    return String(doctor.doctor_name || name);
  }

  return String(name);
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
