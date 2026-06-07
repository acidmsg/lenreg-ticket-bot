/**
 * Экран просмотра свободных слотов для отслеживаемого врача.
 * Слоты группируются по датам.
 *
 * @module views/slots
 */

import { apiGet, apiPost, apiDelete } from '../api.js';
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

    // Собираем итоговый HTML: информация о враче + пациенты + слоты
    let html = renderSlotInfo(data, monitoringId);

    // Блок пациентов (пришёл через params из doctors.js)
    const patients = params?.patients;
    if (patients && patients.length > 0) {
      html += renderPatientsBlock(patients);
    }

    const slots = data.slots || [];
    if (slots.length === 0) {
      html += renderNoSlots();
    } else {
      html += renderSlotList(slots);
    }

    container.innerHTML = html;

    // Привязываем обработчики (удаление пациентов + кнопка 🔄)
    bindSlotEvents(container, patients || [], params);
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
function renderSlotInfo(data, monitoringId) {
  const doctorName = extractDoctorName(data) || 'Врач';
  const specialty = data.specialty || '';
  const clinicName = data.clinic_name || '';
  const total = data.total || 0;

  return `
    <div class="mb-md">
      <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
        <span style="font-size: var(--font-lg); font-weight: 600;">
          ${escapeHtml(doctorName)}
        </span>
        <button
          class="btn--refresh"
          id="slots-refresh-btn"
          data-monitoring-id="${escapeHtml(monitoringId || '')}"
          title="Проверить слоты"
          aria-label="Принудительная проверка слотов"
        >🔄</button>
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
 * Рендерит блок пациентов, отслеживающих врача.
 *
 * @param {Array<{name: string, patientId: string, entryId: string}>} patients — список пациентов
 * @returns {string} HTML блока пациентов
 */
function renderPatientsBlock(patients) {
  const patientsHtml = patients
    .map(
      (p) => `
      <li class="monitoring-patient">
        <span class="monitoring-patient__icon">👤</span>
        <span class="monitoring-patient__name">${escapeHtml(p.name)}</span>
        <button
          class="monitoring-patient__delete"
          data-entry-id="${escapeHtml(p.entryId)}"
          data-patient-name="${escapeHtml(p.name)}"
          title="Удалить мониторинг для этого пациента"
        >🗑</button>
      </li>`
    )
    .join('');

  return `
    <div class="slots-patients">
      <div class="monitoring-patients__title">👤 Пациенты:</div>
      <ul class="monitoring-patients">
        ${patientsHtml}
      </ul>
    </div>
  `;
}

/**
 * Привязывает обработчики событий на экране слотов.
 *
 * @param {HTMLElement} container — контейнер
 * @param {Array} patients — список пациентов
 */
function bindSlotEvents(container, patients, params) {
  // Кнопка принудительной проверки слотов 🔄
  const refreshBtn = container.querySelector('#slots-refresh-btn');
  if (refreshBtn) {
    refreshBtn.addEventListener('click', async (e) => {
      e.stopPropagation();
      const monId = refreshBtn.getAttribute('data-monitoring-id');
      if (!monId) return;

      // Показываем анимацию загрузки
      refreshBtn.classList.add('btn--refresh--loading');

      try {
        const result = await apiPost('/doctors/check', {
          monitoring_id: monId
        });

        const total = result.total || 0;

        // Только toast-уведомление, без перерисовки слотов
        if (window.showToast) {
          if (total > 0) {
            window.showToast('Талоны найдены: ' + total);
          } else {
            window.showToast('Талоны не найдены');
          }
        } else if (isInTelegram()) {
          // Fallback: toast-модуль ещё не загружен — используем Telegram alert
          window.Telegram.WebApp.showPopup({
            title: 'Проверка слотов',
            message:
              total > 0 ? 'Талоны найдены: ' + total : 'Талоны не найдены',
            buttons: [{ type: 'ok' }]
          });
        }

        // Тактильный отклик
        if (window.Telegram?.WebApp?.HapticFeedback) {
          window.Telegram.WebApp.HapticFeedback.notificationOccurred('success');
        }
      } catch (error) {
        if (isInTelegram()) {
          window.Telegram.WebApp.showAlert(`Ошибка проверки: ${error.message}`);
        } else {
          alert(`Ошибка проверки: ${error.message}`);
        }
      } finally {
        refreshBtn.classList.remove('btn--refresh--loading');
      }
    });
  }

  // Кнопки удаления пациентов
  container.querySelectorAll('.monitoring-patient__delete').forEach((btn) => {
    btn.addEventListener('click', async (e) => {
      e.stopPropagation();
      btn.blur(); // убираем :active/:focus после клика (мобильное залипание)
      const entryId = btn.getAttribute('data-entry-id');
      const patientName =
        btn.getAttribute('data-patient-name') || 'этого пациента';

      // Тактильный отклик перед показом диалога
      if (window.Telegram?.WebApp?.HapticFeedback) {
        window.Telegram.WebApp.HapticFeedback.impactOccurred('medium');
      }

      let confirmed = false;
      if (isInTelegram()) {
        confirmed = await new Promise((resolve) => {
          window.Telegram.WebApp.showConfirm(
            `Удалить мониторинг для пациента «${patientName}»?`,
            (result) => resolve(result)
          );
        });
      } else {
        confirmed = confirm(
          `Удалить мониторинг для пациента «${patientName}»?`
        );
      }

      if (!confirmed) return;

      try {
        await apiDelete(`/doctors/${encodeURIComponent(entryId)}`);

        if (isInTelegram()) {
          window.Telegram.WebApp.HapticFeedback.notificationOccurred('success');
        }

        // Удаляем пациента из списка и перерендериваем секцию
        const updatedPatients = patients.filter((p) => p.entryId !== entryId);
        const patientsBlock = container.querySelector('.slots-patients');
        if (patientsBlock) {
          if (updatedPatients.length === 0) {
            patientsBlock.remove();
          } else {
            patientsBlock.outerHTML = renderPatientsBlock(updatedPatients);
            // Обновляем массив patients в замыкании через перепривязку
            patients.length = 0;
            updatedPatients.forEach((p) => patients.push(p));
            bindSlotEvents(container, patients, params);
          }
        }
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
