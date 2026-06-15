/**
 * Экран списка отслеживаемых врачей (главный экран).
 * Отображает список врачей со статусом слотов.
 *
 * @module views/doctors
 */

import { apiGet, apiPost, apiDelete } from '../api.js';
import { isInTelegram } from '../auth.js';
import { createDoctorCard } from '../components/card.js';
import { escapeHtml } from '../utils/escape.js';
import { renderError } from '../utils/error.js';
import { refreshDoctorSlots } from '../utils/monitoring.js';
import { showConfirm } from '../utils/ui.js';
import { lucideIcon } from '../components/icon.js';
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
    renderError(container, error.message, 'Повторить', () =>
      renderDoctors(container)
    );
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
      <div class="empty-state__icon">${lucideIcon('stethoscope', 48)}</div>
      <p class="empty-state__text">
        Вы пока не отслеживаете ни одного врача.
        Добавьте первый мониторинг, чтобы получать уведомления о появлении свободных номерков.
      </p>
      <button class="btn btn--primary" id="empty-add-btn"><span class="lucide-icon">${lucideIcon('circle-plus', 16)}</span> Новый мониторинг</button>
    </div>
  `;
}

/**
 * Рендерит список карточек врачей, сгруппированных по doctor_id.
 *
 * @param {Array} doctors — массив врачей из API
 * @returns {string} HTML списка врачей
 */
function renderDoctorList(doctors) {
  // Группировка по doctor_id
  const grouped = {};
  doctors.forEach((doctor) => {
    if (!grouped[doctor.doctor_id]) {
      grouped[doctor.doctor_id] = {
        doctorName: extractDoctorName(doctor) || 'Неизвестный врач',
        specialty: doctor.specialty || '—',
        clinicName: doctor.clinic_name || '—',
        clinicId: doctor.clinic_id || '',
        status: doctor.status || 'checking',
        freeTickets: doctor.free_tickets || 0,
        patients: []
      };
    }
    grouped[doctor.doctor_id].patients.push({
      name: doctor.patient_name || '',
      patientId: doctor.patient_id || '',
      entryId: doctor.monitoring_id || ''
    });
  });

  const cards = Object.values(grouped)
    .map((group) => {
      // monitoringId — от первого пациента в группе
      const monitoringId =
        group.patients.length > 0 ? group.patients[0].entryId : '';
      return createDoctorCard({
        doctorName: group.doctorName,
        specialty: group.specialty,
        clinicName: group.clinicName,
        status: group.status,
        freeTickets: group.freeTickets,
        patients: group.patients,
        monitoringId: monitoringId
      });
    })
    .join('');

  return `<div class="doctors-list">${cards}</div>`;
}

/**
 * Асинхронный обработчик нажатия на кнопку принудительной проверки слотов.
 *
 * @param {HTMLElement} btn — кнопка refresh
 */
async function handleDoctorRefresh(btn) {
  const monitoringId = btn.getAttribute('data-monitoring-id');
  if (!monitoringId) return;

  // Показываем анимацию загрузки
  btn.classList.add('btn--refresh--loading');

  try {
    const result = await refreshDoctorSlots(monitoringId);

    // Только toast-уведомление, без изменения DOM
    const total = result.total || 0;
    if (window.showToast) {
      if (total > 0) {
        window.showToast('Талоны найдены: ' + total);
      } else {
        window.showToast('Талоны не найдены');
      }
    } else if (isInTelegram()) {
      // Fallback: toast-модуль ещё не загружен — используем Telegram alert
      window.Telegram.WebApp.showPopup({
        title: 'Проверка номерков',
        message: total > 0 ? 'Талоны найдены: ' + total : 'Талоны не найдены',
        buttons: [{ type: 'ok' }]
      });
    }

    // Тактильный отклик
    if (window.Telegram?.WebApp?.HapticFeedback) {
      window.Telegram.WebApp.HapticFeedback.notificationOccurred('success');
    }
  } catch (error) {
    // Показываем ошибку
    if (isInTelegram()) {
      window.Telegram.WebApp.showAlert(`Ошибка проверки: ${error.message}`);
    } else {
      alert(`Ошибка проверки: ${error.message}`);
    }
  } finally {
    btn.classList.remove('btn--refresh--loading');
  }
}

/**
 * Асинхронный обработчик нажатия на кнопку удаления пациента из карточки врача.
 *
 * @param {HTMLElement} btn — кнопка удаления
 * @param {HTMLElement} container — контейнер для перерендера
 */
async function handleDoctorDelete(btn, container) {
  btn.blur(); // убираем :active/:focus после клика (мобильное залипание)
  const entryId = btn.getAttribute('data-entry-id');
  const patientName = btn.getAttribute('data-patient-name') || 'этого пациента';

  // Тактильный отклик перед показом диалога
  if (window.Telegram?.WebApp?.HapticFeedback) {
    window.Telegram.WebApp.HapticFeedback.impactOccurred('medium');
  }

  const confirmed = await showConfirm(
    `Удалить мониторинг для пациента «${patientName}»?`
  );

  if (!confirmed) return;

  try {
    await apiDelete(`/doctors/${encodeURIComponent(entryId)}`);

    // Тактильный отклик
    if (isInTelegram()) {
      window.Telegram.WebApp.HapticFeedback.notificationOccurred('success');
    }

    // Перезагружаем список
    await renderDoctors(container);
  } catch (error) {
    if (isInTelegram()) {
      window.Telegram.WebApp.showAlert(`Ошибка при удалении: ${error.message}`);
    } else {
      alert(`Ошибка при удалении: ${error.message}`);
    }
  }
}

/**
 * Привязывает обработчик клика по карточке врача → открытие слотов.
 *
 * @param {HTMLElement} container — контейнер со списком
 * @param {Array} doctors — массив врачей
 */
function bindDoctorCardClick(container, doctors) {
  container.querySelectorAll('.doctor-card').forEach((card) => {
    card.addEventListener('click', (e) => {
      // Не реагируем на клики по кнопкам удаления пациентов и кнопке обновления
      if (e.target.closest('.monitoring-patient__delete')) return;
      if (e.target.closest('.btn--refresh')) return;

      const entryId = card.getAttribute('data-entry-id');
      if (!entryId) return;

      // Находим пациентов для этой карточки
      const patients = findPatientsForCard(card, doctors);
      navigate('slots', { monitoringId: entryId, patients });
    });
  });
}

/**
 * Привязывает обработчики кнопок принудительной проверки слотов.
 *
 * @param {HTMLElement} container — контейнер со списком
 */
function bindDoctorRefreshButtons(container) {
  container.querySelectorAll('.btn--refresh').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      handleDoctorRefresh(btn);
    });
  });
}

/**
 * Привязывает обработчики кнопок удаления пациентов из карточек врачей.
 *
 * @param {HTMLElement} container — контейнер со списком
 */
function bindDoctorDeleteButtons(container) {
  container.querySelectorAll('.monitoring-patient__delete').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      handleDoctorDelete(btn, container);
    });
  });
}

/**
 * Привязывает обработчики событий для списка врачей.
 *
 * @param {HTMLElement} container — контейнер со списком
 * @param {Array} doctors — массив врачей
 */
function bindDoctorEvents(container, doctors) {
  bindDoctorCardClick(container, doctors);
  bindDoctorRefreshButtons(container);
  bindDoctorDeleteButtons(container);
}

/**
 * Находит пациентов для карточки врача по номеру карточки в DOM.
 *
 * @param {HTMLElement} card — DOM-элемент карточки врача
 * @param {Array} doctors — массив врачей из API
 * @returns {Array<{name: string, patientId: string, entryId: string}>}
 */
function findPatientsForCard(card, doctors) {
  const cardIndex = Array.from(card.parentElement.children).indexOf(card);

  // Группируем врачей так же, как в renderDoctorList
  const grouped = {};
  doctors.forEach((doctor) => {
    if (!grouped[doctor.doctor_id]) {
      grouped[doctor.doctor_id] = { patients: [] };
    }
    grouped[doctor.doctor_id].patients.push({
      name: doctor.patient_name || '',
      patientId: doctor.patient_id || '',
      entryId: doctor.monitoring_id || ''
    });
  });

  const groups = Object.values(grouped);
  if (cardIndex >= 0 && cardIndex < groups.length) {
    return groups[cardIndex].patients;
  }
  return [];
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
 * Извлекает строковое имя врача из поля name, которое может быть объектом.
 *
 * NOTE: Локальная версия отличается от utils/doctor.js (Фаза 2, Шаг 4).
 * utils/doctor.js принимает name напрямую + fallback-параметр.
 * Здесь принимается doctor-объект, извлекается doctor.name,
 * fallback — doctor.doctor_name. Унификация требует изменения сигнатур вызовов.
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
