/**
 * Экран управления пациентами.
 * Просмотр списка пациентов и добавление нового пациента.
 *
 * @module views/patients
 */

import { apiGet, apiPost } from '../api.js';
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
 * Рендерит список пациентов и кнопку добавления.
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
        <button class="btn btn--primary" id="patient-add-btn"><span class="lucide-icon">${lucideIcon('circle-plus', 18)}</span> Добавить пациента</button>
      </div>
      <div id="patient-form-container"></div>
    `;
  }

  const items = patients
    .map(
      (p) => `
      <li class="list__item">
        <div class="list__item-content">
          <div class="list__item-title">${escapeHtml(p.fio || 'Пациент')}</div>
          ${p.bday ? `<div class="list__item-subtitle"><span class="lucide-icon">${lucideIcon('calendar', 14)}</span> ${escapeHtml(p.bday)}</div>` : ''}
          ${p.alias ? `<div class="list__item-subtitle"><span class="lucide-icon">${lucideIcon('tag', 14)}</span> ${escapeHtml(p.alias)}</div>` : ''}
        </div>
      </li>
    `
    )
    .join('');

  return `
    <ul class="list">${items}</ul>
    <div class="mt-md text-center">
      <button class="btn btn--primary" id="patient-add-btn"><span class="lucide-icon">${lucideIcon('circle-plus', 18)}</span> Добавить пациента</button>
    </div>
    <div id="patient-form-container"></div>
  `;
}

/**
 * Рендерит форму добавления пациента.
 *
 * @returns {string} HTML формы
 */
function renderAddForm() {
  return `
    <div class="card mt-md" id="patient-add-form">
      <div class="card__title mb-md">Новый пациент</div>
      <form id="patient-form" autocomplete="off">
        <div class="mb-md">
          <label class="card__subtitle" for="patient-fio">ФИО</label>
          <input
            type="text"
            id="patient-fio"
            class="search-bar__input"
            placeholder="Фамилия Имя Отчество"
            required
            autocomplete="off"
          >
        </div>
        <div class="mb-md">
          <label class="card__subtitle" for="patient-bday">Дата рождения</label>
          <input
            type="text"
            id="patient-bday"
            class="search-bar__input"
            placeholder="ДД.ММ.ГГГГ"
            required
            autocomplete="off"
          >
        </div>
        <div class="card__actions">
          <button type="submit" class="btn btn--primary" id="patient-submit-btn">
            <span class="lucide-icon">${lucideIcon('check', 16)}</span> Добавить
          </button>
          <button type="button" class="btn btn--secondary" id="patient-cancel-btn">
            <span class="lucide-icon">${lucideIcon('x', 16)}</span> Отмена
          </button>
        </div>
      </form>
      <div id="patient-form-error" class="hidden mt-md" style="color: var(--tg-destructive-color); font-size: var(--font-sm);"></div>
    </div>
  `;
}

/**
 * Привязывает обработчики событий.
 *
 * @param {HTMLElement} container — контейнер
 */
function bindEvents(container) {
  const addBtn = container.querySelector('#patient-add-btn');
  if (addBtn) {
    addBtn.addEventListener('click', () => {
      const formContainer = container.querySelector('#patient-form-container');
      if (formContainer) {
        const existingForm = formContainer.querySelector('#patient-add-form');
        if (existingForm) {
          // Форма уже открыта — скрываем
          existingForm.remove();
          return;
        }
        formContainer.innerHTML = renderAddForm();
        bindFormEvents(formContainer);
      }
    });
  }

  // Повторная привязка после программного клика
  const formContainer = container.querySelector('#patient-form-container');
  if (formContainer) {
    const existingForm = formContainer.querySelector('#patient-add-form');
    if (existingForm) {
      bindFormEvents(formContainer);
    }
  }
}

/**
 * Привязывает обработчики формы добавления пациента.
 *
 * @param {HTMLElement} formContainer — контейнер с формой
 */
function bindFormEvents(formContainer) {
  const form = formContainer.querySelector('#patient-form');
  const cancelBtn = formContainer.querySelector('#patient-cancel-btn');
  const errorEl = formContainer.querySelector('#patient-form-error');

  if (cancelBtn) {
    cancelBtn.addEventListener('click', () => {
      const addForm = formContainer.querySelector('#patient-add-form');
      if (addForm) addForm.remove();
    });
  }

  if (form) {
    form.addEventListener('submit', async (e) => {
      e.preventDefault();

      const fioInput = form.querySelector('#patient-fio');
      const bdayInput = form.querySelector('#patient-bday');
      const submitBtn = form.querySelector('#patient-submit-btn');

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

      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = `<span class="lucide-icon">${lucideIcon('loader-circle', 16)}</span> Поиск...`;
      }
      hideFormError(errorEl);

      try {
        const result = await apiPost('/patients/add', {
          full_name,
          birth_date
        });

        // Тактильный отклик
        if (isInTelegram()) {
          window.Telegram.WebApp.HapticFeedback.notificationOccurred('success');
        }

        // Закрываем форму и перезагружаем список
        const addForm = formContainer.querySelector('#patient-add-form');
        if (addForm) addForm.remove();

        // Перезагружаем экран пациентов
        const container = formContainer.closest('#patients-content');
        if (container) {
          await renderPatients(container);
        }
      } catch (error) {
        showFormError(errorEl, error.message);
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.innerHTML = `<span class="lucide-icon">${lucideIcon('check', 16)}</span> Добавить`;
        }
      }
    });
  }
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
      <button class="btn btn--primary" id="patients-retry-btn"><span class="lucide-icon">${lucideIcon('refresh-cw', 18)}</span> Повторить</button>
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
