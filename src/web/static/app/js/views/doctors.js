/**
 * Экран списка отслеживаемых врачей (главный экран).
 * Отображает список врачей со статусом слотов.
 *
 * @module views/doctors
 */

import { apiGet, apiDelete } from '../api.js';
import { isInTelegram } from '../auth.js';
import { createDoctorCard } from '../components/card.js';
import { navigate } from '../app.js';

/**
 * Рендерит главный экран в указанный контейнер.
 *
 * @param {HTMLElement} container — DOM-элемент для рендеринга
 */
export async function renderDoctors(container) {
  if (!container) return;

  // Показываем скелетон загрузки
  container.innerHTML = renderSkeletons();

  try {
    const data = await apiGet('/doctors');
    const doctors = data.doctors || [];

    if (doctors.length === 0) {
      container.innerHTML = renderEmpty();
      bindEmptyEvents(container);
      return;
    }

    container.innerHTML = renderDoctorList(doctors);
    bindDoctorEvents(container, doctors);
  } catch (error) {
    container.innerHTML = renderError(error.message);
    bindErrorEvents(container);
  }
}

/**
 * Рендерит скелетоны загрузки (3 карточки).
 *
 * @returns {string} HTML скелетонов
 */
function renderSkeletons() {
  let html = '';
  for (let i = 0; i < 3; i++) {
    html += `
      <div class="card skeleton--card">
        <div class="skeleton skeleton--title"></div>
        <div class="skeleton skeleton--text" style="width: 40%;"></div>
        <div class="skeleton skeleton--text" style="width: 70%;"></div>
        <div style="display: flex; gap: 8px; margin-top: 12px;">
          <div class="skeleton skeleton--chip"></div>
          <div class="skeleton skeleton--chip"></div>
        </div>
      </div>
    `;
  }
  return html;
}

/**
 * Рендерит пустое состояние.
 *
 * @returns {string} HTML пустого состояния
 */
function renderEmpty() {
  return `
    <div class="empty-state">
      <div class="empty-state__icon">👨‍⚕️</div>
      <p class="empty-state__text">
        Вы пока не отслеживаете ни одного врача.
        Добавьте первый мониторинг, чтобы получать уведомления о появлении свободных слотов.
      </p>
      <button class="btn btn--primary" id="empty-add-btn">➕ Новый мониторинг</button>
    </div>
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
      <button class="btn btn--primary" id="error-retry-btn">🔄 Повторить</button>
    </div>
  `;
}

/**
 * Рендерит список карточек врачей.
 *
 * @param {Array} doctors — массив врачей из API
 * @returns {string} HTML списка врачей
 */
function renderDoctorList(doctors) {
  const cards = doctors
    .map((doc) =>
      createDoctorCard({
        doctorName: extractDoctorName(doc) || 'Неизвестный врач',
        specialty: doc.specialty || '—',
        clinicName: doc.clinic_name || '—',
        status: doc.status || 'checking',
        freeTickets: doc.free_tickets || 0,
        monitoringId: doc.monitoring_id || ''
      })
    )
    .join('');

  return `<div class="doctors-list">${cards}</div>`;
}

/**
 * Привязывает обработчики событий для списка врачей.
 *
 * @param {HTMLElement} container — контейнер со списком
 * @param {Array} doctors — массив врачей
 */
function bindDoctorEvents(container, doctors) {
  // Кнопки «Слоты»
  container.querySelectorAll('.card-btn-slots').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const monitoringId = btn.getAttribute('data-monitoring-id');
      if (monitoringId) {
        navigate('slots', { monitoringId });
      }
    });
  });

  // Кнопки «Удалить»
  container.querySelectorAll('.card-btn-delete').forEach((btn) => {
    btn.addEventListener('click', async (e) => {
      e.stopPropagation();
      const monitoringId = btn.getAttribute('data-monitoring-id');

      // Находим врача для получения имени
      const doctor = doctors.find((d) => d.monitoring_id === monitoringId);
      const doctorName = doctor ? extractDoctorName(doctor) : 'этого врача';

      // Подтверждение удаления
      let confirmed = false;
      if (isInTelegram()) {
        confirmed = await new Promise((resolve) => {
          window.Telegram.WebApp.showConfirm(
            `Удалить врача «${doctorName}» из мониторинга?`,
            (result) => resolve(result)
          );
        });
      } else {
        confirmed = confirm(`Удалить врача «${doctorName}» из мониторинга?`);
      }

      if (!confirmed) return;

      try {
        await apiDelete(`/doctors/${encodeURIComponent(monitoringId)}`);

        // Тактильный отклик
        if (isInTelegram()) {
          window.Telegram.WebApp.HapticFeedback.notificationOccurred('success');
        }

        // Отправляем данные боту
        if (isInTelegram()) {
          window.Telegram.WebApp.sendData(
            JSON.stringify({
              action: 'doctor_removed',
              doctor_name: doctorName
            })
          );
        }

        // Перезагружаем список
        await renderDoctors(container);
      } catch (error) {
        if (isInTelegram()) {
          window.Telegram.WebApp.showAlert(
            `Ошибка при удалении: ${error.message}`
          );
        } else {
          alert(`Ошибка при удалении: ${error.message}`);
        }
      }
    });
  });
}

/**
 * Привязывает обработчики для пустого состояния.
 *
 * @param {HTMLElement} container — контейнер
 */
function bindEmptyEvents(container) {
  const addBtn = container.querySelector('#empty-add-btn');
  if (addBtn) {
    addBtn.addEventListener('click', () => {
      navigate('add');
    });
  }
}

/**
 * Привязывает обработчики для состояния ошибки.
 *
 * @param {HTMLElement} container — контейнер
 */
function bindErrorEvents(container) {
  const retryBtn = container.querySelector('#error-retry-btn');
  if (retryBtn) {
    retryBtn.addEventListener('click', () => {
      renderDoctors(container);
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
