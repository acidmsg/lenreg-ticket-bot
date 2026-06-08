/**
 * Компонент пошагового выбора (stepper).
 * Универсальный компонент для многошаговых форм.
 *
 * При клике на элемент списка (кроме последнего шага подтверждения)
 * происходит автоматический переход к следующему шагу.
 * Кнопка «Далее» скрыта через CSS (класс .stepper__btn--next).
 *
 * @module components/stepper
 */

import { lucideIcon } from './icon.js';

/**
 * Создаёт экземпляр stepper и рендерит его в контейнер.
 *
 * @param {object} options — параметры stepper
 * @param {HTMLElement} options.container — DOM-элемент для рендеринга
 * @param {Array<{title: string, description: string, loadData: Function, renderItem: Function, searchPlaceholder?: string}>} options.steps — массив шагов
 * @param {Function} options.onComplete — колбэк при завершении (вызывается с выбранными значениями)
 * @param {Function} [options.onCancel] — колбэк при отмене
 * @returns {object} объект управления stepper
 */
export function createStepper({ container, steps, onComplete, onCancel }) {
  /** Текущий индекс шага (0-based) */
  let currentStep = 0;

  /** Массив выбранных значений: [{ value, label }] */
  const selections = [];

  /** Данные текущего шага */
  let stepData = [];

  /** Флаг загрузки */
  let isLoading = false;

  /** Счётчик загрузок для предотвращения гонки */
  let _loadId = 0;

  /** Текущий режим поиска (null | 'clinics' | 'doctors') */
  let _currentSearchMode = null;

  /** Таймер debounce для API-поиска */
  let _searchDebounce = null;

  /** Флаг: данные шага были загружены хотя бы раз */
  let _dataLoaded = false;

  /**
   * Переходит к следующему шагу, сохраняя выбранный элемент.
   *
   * @param {number} selectedIndex — индекс выбранного элемента в stepData
   */
  function advanceStep(selectedIndex) {
    const selectedItem = stepData[selectedIndex];
    selections.push(selectedItem);
    if (selectedItem._skipNext) {
      currentStep += 2;
    } else {
      currentStep++;
    }
    stepData = [];
    render();
  }

  /**
   * Рендерит текущее состояние stepper.
   */
  function render() {
    if (currentStep >= steps.length) {
      container.innerHTML = '';
      if (onComplete) {
        onComplete(selections);
      }
      return;
    }

    // Сброс pending debounce при переходе на другой шаг
    if (_searchDebounce) {
      clearTimeout(_searchDebounce);
      _searchDebounce = null;
    }
    _dataLoaded = false;

    const step = steps[currentStep];

    if (step.searchMode !== undefined) {
      _currentSearchMode = step.searchMode;
    } else {
      _currentSearchMode = null;
    }

    // Динамические заголовки ТОЛЬКО для шага clinic (currentStep === 1).
    let displayTitle = step.title;
    let displayDesc = step.description;
    if (currentStep === 1 && _currentSearchMode !== null) {
      const isClinicMode = _currentSearchMode === 'clinics';
      displayTitle = isClinicMode ? 'Выбор поликлиники' : 'Поиск врача';
      displayDesc = isClinicMode
        ? 'Выберите поликлинику из списка'
        : `${lucideIcon('search', 14)} Начните вводить фамилию, имя или отчество врача`;
    }

    const dotsHTML = steps
      .map((_, i) => {
        let cls = 'stepper__dot';
        if (i < currentStep) cls += ' stepper__dot--done';
        else if (i === currentStep) cls += ' stepper__dot--current';
        else cls += ' stepper__dot--future';
        return `<span class="${cls}"></span>`;
      })
      .join('');

    const progressHtml = dotsHTML;

    const searchHtml =
      step.searchPlaceholder !== undefined
        ? `
        <div class="search-bar">
          <div class="search-bar__wrapper">
            <input
              type="text"
              class="search-bar__input"
              placeholder="${escapeHtml(step.searchPlaceholder)}"
              id="stepper-search"
              autocomplete="off"
            >
            <button type="button" class="search-bar__clear" id="stepper-search-clear" aria-label="Очистить">
              <span class="lucide-icon">${lucideIcon('x', 16)}</span>
            </button>
          </div>
        </div>
      `
        : '';

    // Кнопка «Выбрать поликлинику» в режиме поиска врачей
    const clinicLinkHtml =
      _currentSearchMode === 'doctors'
        ? `<div class="stepper__alt-action">
            <button class="btn btn--secondary btn--sm stepper__clinic-btn" id="stepper-switch-clinics"><span class="lucide-icon">${lucideIcon('hospital', 14)}</span> Выбрать поликлинику</button>
          </div>`
        : '';

    const canGoBack = currentStep > 0;
    const backButtonHtml = canGoBack
      ? `<button class="btn btn--secondary" id="stepper-back"><span class="lucide-icon">${lucideIcon('arrow-left', 16)}</span> Назад</button>`
      : `<button class="btn btn--danger" id="stepper-cancel"><span class="lucide-icon">${lucideIcon('x', 16)}</span> Отмена</button>`;

    const isLastStep = currentStep === steps.length - 1;
    const nextBtnClass = isLastStep ? '' : ' stepper__btn--next';

    container.innerHTML = `
      <div class="stepper">
        <div class="stepper__progress">${progressHtml}</div>
        <h2 class="stepper__title">${escapeHtml(displayTitle)}</h2>
        <p class="stepper__description">${displayDesc}</p>
        ${searchHtml}
        ${clinicLinkHtml}
        <div class="stepper__content" id="stepper-content">
          ${isLoading || (!_dataLoaded && stepData.length === 0) ? renderLoading() : renderItems(stepData, step.renderItem, isLastStep)}
        </div>
        <div class="stepper__actions">
          ${backButtonHtml}
          <button class="btn btn--primary${nextBtnClass}" id="stepper-next"${isLastStep ? '' : ' disabled'}>
            ${isLastStep ? `<span class="lucide-icon">${lucideIcon('check', 16)}</span> Готово` : `<span class="lucide-icon">${lucideIcon('arrow-right', 16)}</span> Далее`}
          </button>
        </div>
      </div>
    `;

    bindEvents(step);
    loadStepData(step);
  }

  function renderLoading() {
    return `
      <div class="stepper-spinner">
        <span class="lucide-icon lucide-icon--spin">${lucideIcon('loader-circle', 24)}</span>
        <span class="stepper-spinner__text">Загрузка...</span>
      </div>
    `;
  }

  function renderItems(items, renderItem, isLastStep = false) {
    if (!items || items.length === 0) {
      return `
        <div class="empty-state">
          <div class="empty-state__icon">${lucideIcon('circle-slash', 48)}</div>
          <p class="empty-state__text">Ничего не найдено</p>
        </div>
      `;
    }

    const itemsHtml = items
      .map(
        (item, idx) => `
        <li class="list__item stepper-item${item._monitored ? ' stepper-item--monitored' : ''}" data-index="${idx}">
          ${renderItem(item)}
        </li>
      `
      )
      .join('');

    return `<ul class="list">${itemsHtml}</ul>`;
  }

  function bindEvents(step) {
    const backBtn = document.getElementById('stepper-back');
    const cancelBtn = document.getElementById('stepper-cancel');
    const nextBtn = document.getElementById('stepper-next');

    if (backBtn) {
      backBtn.addEventListener('click', () => {
        // Если мы в режиме clinics (переключились с doctors) — возврат в doctors
        if (_currentSearchMode === 'clinics' && currentStep === 1) {
          _currentSearchMode = 'doctors';
          const clinicStep = steps[currentStep];
          clinicStep.searchMode = 'doctors';
          clinicStep.title = 'Поиск врача';
          clinicStep.description = `${lucideIcon('search', 14)} Начните вводить фамилию, имя или отчество врача`;
          clinicStep.searchPlaceholder = 'Фамилия, имя или отчество...';
          stepData = [];
          render();
          return;
        }
        // Обычная логика назад
        if (selections.length > 0) {
          const last = selections[selections.length - 1];
          if (last?._skipNext) {
            currentStep -= 2;
          } else {
            currentStep = Math.max(0, currentStep - 1);
          }
          selections.pop();
        }
        stepData = [];
        render();
      });
    }

    if (cancelBtn) {
      cancelBtn.addEventListener('click', () => {
        if (onCancel) {
          onCancel();
        }
      });
    }

    if (nextBtn) {
      nextBtn.addEventListener('click', () => {
        if (currentStep === steps.length - 1) {
          if (onComplete) {
            onComplete(selections);
          }
        }
      });
    }

    // Кнопка «Выбрать поликлинику» (только в doctors-режиме)
    const switchBtn = document.getElementById('stepper-switch-clinics');
    if (switchBtn) {
      switchBtn.addEventListener('click', () => {
        _currentSearchMode = 'clinics';
        step.searchMode = 'clinics';
        // Обновляем заголовки шага для clinics-режима
        step.title = 'Выбор поликлиники';
        step.description = 'Выберите поликлинику из списка';
        // Уведомляем родительский код о смене режима
        if (typeof step.onSearchModeChange === 'function') {
          step.onSearchModeChange('clinics');
        }
        stepData = [];
        render();
      });
    }
  }

  /**
   * Загружает данные для текущего шага.
   */
  async function loadStepData(step) {
    const loadId = ++_loadId;
    isLoading = true;
    try {
      stepData = await step.loadData(selections);
    } catch (error) {
      if (loadId !== _loadId) return;
      stepData = [];
      showError(error.message || 'Ошибка загрузки данных');
      return;
    } finally {
      if (loadId === _loadId) {
        isLoading = false;
        _dataLoaded = true;
      }
    }
    if (loadId !== _loadId) return;
    updateContent();
  }

  /**
   * Обновляет содержимое stepper (список элементов).
   */
  function updateContent() {
    const contentEl = document.getElementById('stepper-content');
    if (!contentEl) return;

    const isLastStep = currentStep === steps.length - 1;

    if (isLoading) {
      contentEl.innerHTML = renderLoading();
      return;
    }

    // Плейсхолдер при пустом поиске в режиме глобального поиска врачей
    if (_currentSearchMode === 'doctors' && stepData.length === 0) {
      const searchInput = document.getElementById('stepper-search');
      const searchQuery = searchInput ? searchInput.value.trim() : '';
      if (searchQuery === '') {
        contentEl.innerHTML = `
          <div class="empty-state">
            <div class="empty-state__icon">${lucideIcon('search', 48)}</div>
            <p class="empty-state__text">Начните вводить фамилию, имя или отчество врача</p>
          </div>
        `;
        setupSearchListener();
        return;
      }
    }

    contentEl.innerHTML = renderItems(
      stepData,
      steps[currentStep].renderItem,
      isLastStep
    );

    if (isLastStep) return;

    const items = container.querySelectorAll('.stepper-item');
    items.forEach((item) => {
      item.addEventListener('click', () => {
        const idx = parseInt(item.getAttribute('data-index'), 10);
        if (!isNaN(idx) && stepData[idx]) {
          if (stepData[idx]._monitored) {
            showToast('Этот врач уже отслеживается');
            return;
          }
          items.forEach((i) => i.classList.remove('stepper-item--selected'));
          item.classList.add('stepper-item--selected');
          advanceStep(idx);
        }
      });
    });

    if (
      stepData.length === 1 &&
      items.length === 1 &&
      _currentSearchMode !== 'doctors'
    ) {
      items[0].classList.add('stepper-item--selected');
      setTimeout(() => {
        if (currentStep < steps.length - 1 && stepData.length === 1) {
          advanceStep(0);
        }
      }, 200);
    }

    setupSearchListener();
  }

  /**
   * Настраивает обработчик поля поиска.
   * Использует oninput (не addEventListener) — автоматически заменяет старый обработчик.
   */
  function setupSearchListener() {
    const searchInput = document.getElementById('stepper-search');
    if (!searchInput) return;

    const clearBtn = document.getElementById('stepper-search-clear');
    if (clearBtn) {
      clearBtn.style.display = searchInput.value.trim() ? 'flex' : 'none';
      clearBtn.onclick = () => {
        searchInput.value = '';
        searchInput.focus();
        searchInput.dispatchEvent(new Event('input'));
      };
    }

    const step = steps[currentStep];
    const isDoctorMode =
      _currentSearchMode === 'doctors' && step.searchMode !== undefined;

    // Таймер автоподсказки: через 3 секунды бездействия показать подсказку.
    // Только на шаге clinic (индекс 1) в режиме doctors.
    let hintTimer = setTimeout(() => {
      if (currentStep !== 1 || _currentSearchMode !== 'doctors') return;
      const input = document.getElementById('stepper-search');
      if (input && input.value.trim() === '') {
        const hintEl = document.getElementById('stepper-hint');
        if (!hintEl) {
          const contentEl = document.getElementById('stepper-content');
          if (contentEl) {
            const hint = document.createElement('div');
            hint.id = 'stepper-hint';
            hint.className = 'stepper-hint';
            hint.innerHTML =
              '<p class="stepper-hint__text">Не знаете врача? Выберите поликлинику, чтобы увидеть список врачей в учреждении.</p>';
            contentEl.parentNode.insertBefore(hint, contentEl);
          }
        }
      }
    }, 3000);

    // oninput заменяет предыдущий обработчик автоматически
    searchInput.oninput = (e) => {
      // При вводе — скрыть подсказку
      clearTimeout(hintTimer);
      const hintEl = document.getElementById('stepper-hint');
      if (hintEl) hintEl.remove();

      const query = e.target.value;

      // Показать/скрыть кнопку очистки
      if (clearBtn) {
        clearBtn.style.display = query ? 'flex' : 'none';
      }

      // Скрыть/показать кнопку «Выбрать поликлинику»
      const clinicBtn = document.getElementById('stepper-switch-clinics');
      if (clinicBtn) {
        clinicBtn.style.display = query.trim() ? 'none' : '';
      }

      if (isDoctorMode) {
        // API-поиск с debounce 400ms
        if (_searchDebounce) clearTimeout(_searchDebounce);

        _searchDebounce = setTimeout(() => {
          if (query.length >= 2) {
            const input = document.getElementById('stepper-search');
            if (input) input.value = query;
            loadStepData(steps[currentStep]);
          } else if (query.length === 0) {
            stepData = [];
            updateContent();
          }
        }, 400);
      } else {
        // Клиентская фильтрация
        const q = query.toLowerCase();
        container.querySelectorAll('.stepper-item').forEach((item) => {
          const text = item.textContent.toLowerCase();
          item.style.display = text.includes(q) ? '' : 'none';
        });
      }
    };
  }

  function showError(message) {
    const contentEl = document.getElementById('stepper-content');
    if (!contentEl) return;

    contentEl.innerHTML = `
      <div class="error-state">
        <p class="error-state__text">${escapeHtml(message)}</p>
        <button class="btn btn--primary" id="stepper-retry"><span class="lucide-icon">${lucideIcon('refresh-cw', 16)}</span> Повторить</button>
      </div>
    `;

    const retryBtn = document.getElementById('stepper-retry');
    if (retryBtn) {
      retryBtn.addEventListener('click', () => {
        loadStepData(steps[currentStep]);
      });
    }
  }

  render();

  return {
    goToStep: (index) => {
      currentStep = Math.max(0, Math.min(index, steps.length));
      selections.length = Math.min(selections.length, currentStep);
      stepData = [];
      render();
    },
    reset: () => {
      currentStep = 0;
      selections.length = 0;
      stepData = [];
      render();
    }
  };
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = String(text);
  return div.innerHTML;
}
