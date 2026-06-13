/**
 * Экран управления пациентами.
 * Просмотр списка пациентов, добавление (отдельный экран) и удаление.
 *
 * @module views/patients
 */

import { apiGet, apiPost, apiDelete } from '../api.js';
import { isInTelegram } from '../auth.js';
import { lucideIcon } from '../components/icon.js';
import { navigate } from '../app.js';

/**
 * Рендерит экран пациентов в указанный контейнер.
 *
 * @param {HTMLElement} container — DOM-элемент для рендеринга
 */
export async function renderPatients(container) {
  if (!container) return;

  // Показываем спиннер загрузки
  container.innerHTML = `
    <div class="spinner">
      <div class="spinner__icon"></div>
    </div>
  `;

  try {
    const data = await apiGet('/patients');
    const patients = data.patients || [];

    container.innerHTML = renderPatientList(patients);
    bindEvents(container);
  } catch (error) {
    container.innerHTML = renderError(error.message);
    bindErrorEvents(container);
  }
}

/**
 * Рендерит форму добавления пациента на отдельном экране.
 * Использует Telegram MainButton для отправки.
 *
 * @param {HTMLElement} container — DOM-элемент для рендеринга
 */
export function renderPatientAddForm(container) {
  if (!container) return;

  container.innerHTML = `
    <div class="patient-add-form">
      <form id="patient-form" autocomplete="off">
        <div class="mb-md">
          <label class="form__label" for="patient-fio">Фамилия Имя Отчество</label>
          <input
            type="text"
            id="patient-fio"
            class="form__input"
            placeholder="Иванов Пётр Иванович"
            required
            autocomplete="off"
          >
        </div>
        <div class="mb-md">
          <label class="form__label" for="patient-bday">Дата рождения</label>
          <input
            type="text"
            id="patient-bday"
            class="form__input"
            placeholder="ДД.ММ.ГГГГ"
            autocomplete="off"
          >
        </div>
      </form>
      <div id="patient-form-error" class="hidden mt-md" style="color: var(--tg-destructive-color); font-size: var(--font-sm);"></div>
      <div class="fab-group">
        <button class="btn btn--secondary btn--sm" id="patient-add-back">← Назад</button>
        <button class="fab" id="patient-add-submit">Добавить</button>
      </div>
    </div>
  `;

  const errorEl = container.querySelector('#patient-form-error');

  // Инициализируем календарь на поле ввода даты
  const bdayInput = container.querySelector('#patient-bday');
  if (bdayInput) {
    const calendar = new VanillaCalendar(bdayInput, {
      input: true,
      settings: {
        lang: 'ru',
        selection: {
          day: 'single'
        },
        visibility: {
          theme: 'dark'
        }
      }
    });
    calendar.init();
  }

  // Кнопка «Назад»
  const backBtn = container.querySelector('#patient-add-back');
  if (backBtn) {
    backBtn.addEventListener('click', () => {
      navigate('patients');
    });
  }

  // Кнопка «Добавить» (отправка формы)
  const submitBtn = container.querySelector('#patient-add-submit');
  if (submitBtn) {
    submitBtn.addEventListener('click', async () => {
      const fioInput = container.querySelector('#patient-fio');
      const full_name = fioInput?.value?.trim() || '';
      const birth_date = bdayInput?.value?.trim() || '';

      // Простая валидация
      const parts = full_name.split(/\s+/).filter(Boolean);
      if (parts.length !== 3) {
        showFormError(
          errorEl,
          'ФИО должно состоять из трёх слов: Фамилия Имя Отчество'
        );
        return;
      }

      if (!/^\d{2}\.\d{2}\.\d{4}$/.test(birth_date)) {
        showFormError(
          errorEl,
          'Дата рождения должна быть в формате ДД.ММ.ГГГГ'
        );
        return;
      }

      hideFormError(errorEl);

      try {
        await apiPost('/patients/add', { full_name, birth_date });

        // Тактильный отклик (если доступен)
        if (isInTelegram() && window.Telegram.WebApp?.HapticFeedback) {
          window.Telegram.WebApp.HapticFeedback.notificationOccurred('success');
        }

        // Возвращаемся на экран пациентов
        navigate('patients');
      } catch (error) {
        showFormError(errorEl, error.message);
      }
    });
  }
}

/**
 * Рендерит список пациентов и кнопку добавления (без inline-формы).
 *
 * @param {Array} patients — массив пациентов
 * @returns {string} HTML
 */
function renderPatientList(patients) {
  if (patients.length === 0) {
    return `
      <div class="empty-state">
        <div class="empty-state__icon">${lucideIcon('user', 48)}</div>
        <p class="empty-state__text">
          У вас пока нет добавленных пациентов.
          Добавьте пациента, чтобы начать отслеживать врачей.
        </p>
        <button class="btn btn--primary" id="patient-add-btn"><span class="lucide-icon">${lucideIcon('circle-plus', 16)}</span> Добавить пациента</button>
      </div>
    `;
  }

  const items = patients
    .map(
      (p) => `
      <li class="patient-card" data-patient-id="${escapeHtml(p.patient_id)}">
        <div class="patient-card__info">
          <div class="patient-card__name">${escapeHtml(p.fio || 'Без имени')}</div>
          ${p.bday ? `<div class="patient-card__bday">${escapeHtml(p.bday)}</div>` : ''}
          ${p.alias ? `<div class="patient-card__alias">${escapeHtml(p.alias)}</div>` : ''}
        </div>
        <button class="patient-card__delete" data-patient-id="${escapeHtml(p.patient_id)}" aria-label="Удалить пациента">
          ${lucideIcon('trash-2', 18)}
        </button>
      </li>
    `
    )
    .join('');

  return `
    <ul class="list">${items}</ul>
    <div class="mt-md text-center">
      <button class="btn btn--primary" id="patient-add-btn"><span class="lucide-icon">${lucideIcon('circle-plus', 16)}</span> Добавить пациента</button>
    </div>
  `;
}

/**
 * Привязывает обработчики событий для списка пациентов.
 *
 * @param {HTMLElement} container — контейнер
 */
function bindEvents(container) {
  const addBtn = container.querySelector('#patient-add-btn');
  if (addBtn) {
    addBtn.addEventListener('click', () => {
      navigate('patient-add');
    });
  }

  // Обработчики кнопок удаления пациента
  container.querySelectorAll('.patient-card__delete').forEach((btn) => {
    btn.addEventListener('click', async (e) => {
      e.stopPropagation();
      const patientId = btn.dataset.patientId;
      const confirmed = await showConfirm(
        'Удалить пациента из списка отслеживаемых?'
      );
      if (confirmed) {
        try {
          await apiDelete(`/patients/${patientId}`);
          // Перезагружаем список пациентов
          const patientsContainer = container.closest('#patients-content');
          if (patientsContainer) {
            await renderPatients(patientsContainer);
          }
        } catch (error) {
          if (window.showToast) {
            window.showToast(error.message, 'error');
          } else {
            alert(error.message);
          }
        }
      }
    });
  });
}

/**
 * Показывает диалог подтверждения.
 * Использует Telegram.WebApp.showConfirm если доступен, иначе confirm().
 *
 * @param {string} message — текст подтверждения
 * @returns {Promise<boolean>}
 */
function showConfirm(message) {
  if (isInTelegram() && window.Telegram.WebApp.showConfirm) {
    return new Promise((resolve) => {
      window.Telegram.WebApp.showConfirm(message, (confirmed) => {
        resolve(confirmed);
      });
    });
  }
  return Promise.resolve(confirm(message));
}

/**
 * Показывает ошибку формы.
 *
 * @param {HTMLElement|null} el — элемент ошибки
 * @param {string} message — текст ошибки
 */
function showFormError(el, message) {
  if (!el) return;
  el.textContent = message;
  el.classList.remove('hidden');
}

/**
 * Скрывает ошибку формы.
 *
 * @param {HTMLElement|null} el — элемент ошибки
 */
function hideFormError(el) {
  if (!el) return;
  el.classList.add('hidden');
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
      <div class="empty-state__icon">${lucideIcon('triangle-alert', 48)}</div>
      <p class="error-state__text">${escapeHtml(message)}</p>
      <button class="btn btn--primary" id="patients-retry-btn"><span class="lucide-icon">${lucideIcon('refresh-cw', 16)}</span> Повторить</button>
    </div>
  `;
}

/**
 * Привязывает обработчики для состояния ошибки.
 *
 * @param {HTMLElement} container — контейнер
 */
function bindErrorEvents(container) {
  const retryBtn = container.querySelector('#patients-retry-btn');
  if (retryBtn) {
    retryBtn.addEventListener('click', () => {
      renderPatients(container);
    });
  }
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
