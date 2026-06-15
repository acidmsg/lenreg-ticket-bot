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
import { escapeHtml } from '../utils/escape.js';

// ═══════════════════════════════════════════════════════════════
// Хелперы построения HTML (чистые функции, без замыканий)
// ═══════════════════════════════════════════════════════════════

/**
 * Строит HTML индикатора загрузки (спиннер).
 *
 * @returns {string}
 */
function buildLoadingHTML() {
  return `
    <div class="stepper-spinner">
      <span class="lucide-icon lucide-icon--spin">${lucideIcon('refresh-cw', 48)}</span>
    </div>`;
}

/**
 * Строит HTML списка элементов или пустого состояния.
 *
 * @param {Array} items — массив элементов шага
 * @param {Function} renderItem — функция рендеринга одного элемента
 * @returns {string}
 */
function buildItemsHTML(items, renderItem) {
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
      (item, index) => `
      <li class="list__item stepper-item${item._monitored ? ' stepper-item--monitored' : ''}" data-index="${index}">
        ${renderItem(item)}
      </li>
    `
    )
    .join('');

  return `<ul class="list">${itemsHtml}</ul>`;
}

/**
 * Строит HTML прогресс-бара (точки-индикаторы шагов).
 *
 * @param {Array} steps — массив шагов
 * @param {number} currentStep — индекс текущего шага (0-based)
 * @returns {string}
 */
function buildStepperProgress(steps, currentStep) {
  return steps
    .map((_, i) => {
      let cls = 'stepper__dot';
      if (i < currentStep) cls += ' stepper__dot--done';
      else if (i === currentStep) cls += ' stepper__dot--current';
      else cls += ' stepper__dot--future';
      return `<span class="${cls}"></span>`;
    })
    .join('');
}

/**
 * Строит HTML строки поиска.
 *
 * @param {string} placeholder
 * @returns {string}
 */
function buildSearchBarHTML(placeholder) {
  return `
    <div class="search-bar">
      <div class="search-bar__wrapper">
        <input
          type="text"
          class="search-bar__input"
          placeholder="${escapeHtml(placeholder)}"
          id="stepper-search"
          autocomplete="off"
        >
        <button type="button" class="search-bar__clear" id="stepper-search-clear" aria-label="Очистить">
          <span class="lucide-icon">${lucideIcon('x', 16)}</span>
        </button>
      </div>
    </div>
  `;
}

/**
 * Строит полную HTML-строку stepper'а (оболочку).
 *
 * @param {Array} steps — массив шагов
 * @param {number} currentStep — индекс текущего шага (0-based)
 * @param {object} opts — параметры отображения
 * @param {string} opts.displayTitle — заголовок шага
 * @param {string} opts.displayDesc — описание шага
 * @param {string|undefined} opts.searchPlaceholder — плейсхолдер для поля поиска
 * @param {string|null} opts.searchMode — режим поиска ('clinics'|'doctors'|null)
 * @param {string} opts.contentHTML — HTML-содержимое stepper__content
 * @param {boolean} opts.canGoBack — доступна ли кнопка «Назад»
 * @param {boolean} opts.isLastStep — последний ли шаг
 * @param {boolean} opts.isWidget — является ли шаг виджетом
 * @returns {string}
 */
function buildStepperHTML(steps, currentStep, opts) {
  const {
    displayTitle,
    displayDesc,
    searchPlaceholder,
    searchMode,
    contentHTML,
    canGoBack,
    isLastStep,
    isWidget
  } = opts;

  const progressHtml = buildStepperProgress(steps, currentStep);

  const searchHtml =
    searchPlaceholder !== undefined
      ? buildSearchBarHTML(searchPlaceholder)
      : '';

  const clinicLinkHtml =
    searchMode === 'doctors'
      ? `<div class="stepper__alt-action">
          <button class="btn btn--secondary btn--sm stepper__clinic-btn" id="stepper-switch-clinics"><span class="lucide-icon">${lucideIcon('hospital', 14)}</span> Выбрать поликлинику</button>
        </div>`
      : '';

  const backButtonHtml = canGoBack
    ? `<button class="btn btn--secondary" id="stepper-back"><span class="lucide-icon">${lucideIcon('arrow-left', 16)}</span> Назад</button>`
    : `<button class="btn btn--danger" id="stepper-cancel"><span class="lucide-icon">${lucideIcon('x', 16)}</span> Отмена</button>`;

  const nextBtnClass = isLastStep || isWidget ? '' : ' stepper__btn--next';

  return `
    <div class="stepper">
      <div class="stepper__progress">${progressHtml}</div>
      <h2 class="stepper__title">${escapeHtml(displayTitle)}</h2>
      <p class="stepper__description">${displayDesc}</p>
      ${searchHtml}
      ${clinicLinkHtml}
      <div class="stepper__content" id="stepper-content">${contentHTML}</div>
      <div class="stepper__actions">
        ${backButtonHtml}
        <button class="btn btn--primary${nextBtnClass}" id="stepper-next"${isLastStep || isWidget ? '' : ' disabled'}>
          ${isLastStep ? `<span class="lucide-icon">${lucideIcon('check', 16)}</span> Готово` : `<span class="lucide-icon">${lucideIcon('arrow-right', 16)}</span> Далее`}
        </button>
      </div>
    </div>
  `;
}

// ═══════════════════════════════════════════════════════════════
// Хелперы привязки событий и обновления контента
// ═══════════════════════════════════════════════════════════════

/**
 * Привязывает обработчики кнопок навигации (Back, Cancel, Next, Switch Clinics).
 *
 * @param {HTMLElement} container — контейнер stepper'а
 * @param {object} state — объект состояния stepper'а
 */
function bindStepperNavigation(container, state) {
  const backBtn = document.getElementById('stepper-back');
  const cancelBtn = document.getElementById('stepper-cancel');
  const nextBtn = document.getElementById('stepper-next');

  if (backBtn) {
    backBtn.addEventListener('click', () => {
      // Если мы в режиме clinics (переключились с doctors) — возврат в doctors
      if (state._currentSearchMode === 'clinics' && state.currentStep === 1) {
        state._currentSearchMode = 'doctors';
        const clinicStep = state.steps[state.currentStep];
        clinicStep.searchMode = 'doctors';
        clinicStep.title = 'Поиск врача';
        clinicStep.description = `${lucideIcon('search', 14)} Начните вводить фамилию, имя или отчество врача`;
        clinicStep.searchPlaceholder = 'Фамилия, имя или отчество...';
        state.stepData = [];
        state.render();
        return;
      }
      // Обычная логика назад
      if (state.selections.length > 0) {
        const last = state.selections[state.selections.length - 1];
        if (last?._skipNext) {
          state.currentStep -= 2;
        } else {
          state.currentStep = Math.max(0, state.currentStep - 1);
        }
        state.selections.pop();
      }
      state.stepData = [];
      state.render();
    });
  }

  if (cancelBtn) {
    cancelBtn.addEventListener('click', () => {
      if (state.onCancel) {
        state.onCancel();
      }
    });
  }

  if (nextBtn) {
    nextBtn.addEventListener('click', () => {
      const isWidget = state.steps[state.currentStep].type === 'widget';
      if (isWidget) {
        state.advanceStep(0);
        return;
      }
      if (state.currentStep === state.steps.length - 1) {
        if (state.onComplete) {
          state.onComplete(state.selections);
        }
      }
    });
  }

  // Кнопка «Выбрать поликлинику» (только в doctors-режиме)
  const switchBtn = document.getElementById('stepper-switch-clinics');
  if (switchBtn) {
    switchBtn.addEventListener('click', () => {
      const step = state.steps[state.currentStep];
      state._currentSearchMode = 'clinics';
      step.searchMode = 'clinics';
      step.title = 'Выбор поликлиники';
      step.description = 'Выберите поликлинику из списка';
      if (typeof step.onSearchModeChange === 'function') {
        step.onSearchModeChange('clinics');
      }
      state.stepData = [];
      state.render();
    });
  }
}

/**
 * Обновляет содержимое stepper (список элементов, loading, empty state).
 *
 * @param {HTMLElement} container — контейнер stepper'а
 * @param {object} state — объект состояния stepper'а
 */
function updateStepperContent(container, state) {
  const contentEl = document.getElementById('stepper-content');
  if (!contentEl) return;

  const isLastStep = state.currentStep === state.steps.length - 1;
  const currentStepDef = state.steps[state.currentStep];

  // Widget-шаг: рендерим напрямую, не как список
  const isWidget = currentStepDef.type === 'widget';
  if (isWidget && state.stepData.length > 0) {
    contentEl.innerHTML = currentStepDef.renderItem(state.stepData[0]);
    setupStepperSearch(container, state);
    return;
  }

  if (state.isLoading) {
    contentEl.innerHTML = buildLoadingHTML();
    return;
  }

  // Плейсхолдер при пустом поиске в режиме глобального поиска врачей
  if (state._currentSearchMode === 'doctors' && state.stepData.length === 0) {
    const searchInput = document.getElementById('stepper-search');
    const searchQuery = searchInput ? searchInput.value.trim() : '';
    if (searchQuery === '') {
      contentEl.innerHTML = `
        <div class="empty-state">
          <div class="empty-state__icon">${lucideIcon('search', 48)}</div>
          <p class="empty-state__text">Начните вводить фамилию, имя или отчество врача</p>
        </div>
      `;
      setupStepperSearch(container, state);
      return;
    }
  }

  contentEl.innerHTML = buildItemsHTML(
    state.stepData,
    currentStepDef.renderItem
  );

  if (isLastStep) return;

  const items = container.querySelectorAll('.stepper-item');
  items.forEach((item) => {
    item.addEventListener('click', () => {
      const index = parseInt(item.getAttribute('data-index'), 10);
      if (!isNaN(index) && state.stepData[index]) {
        if (state.stepData[index]._monitored) {
          // showToast вызывается глобально (определён в toast.js)
          if (typeof showToast === 'function') {
            showToast('Этот врач уже отслеживается');
          }
          return;
        }
        items.forEach((i) => i.classList.remove('stepper-item--selected'));
        item.classList.add('stepper-item--selected');
        state.advanceStep(index);
      }
    });
  });

  const isWidgetAuto = currentStepDef.type === 'widget';
  if (
    state.stepData.length === 1 &&
    items.length === 1 &&
    state._currentSearchMode !== 'doctors' &&
    !isWidgetAuto
  ) {
    items[0].classList.add('stepper-item--selected');
    setTimeout(() => {
      if (
        state.currentStep < state.steps.length - 1 &&
        state.stepData.length === 1
      ) {
        state.advanceStep(0);
      }
    }, 200);
  }

  setupStepperSearch(container, state);
}

/**
 * Настраивает обработчик поля поиска с debounce.
 *
 * @param {HTMLElement} container — контейнер stepper'а
 * @param {object} state — объект состояния stepper'а
 */
function setupStepperSearch(container, state) {
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

  const step = state.steps[state.currentStep];
  const isDoctorMode =
    state._currentSearchMode === 'doctors' && step.searchMode !== undefined;

  // Таймер автоподсказки: через 3 секунды бездействия показать подсказку.
  let hintTimer = setTimeout(() => {
    if (state.currentStep !== 1 || state._currentSearchMode !== 'doctors')
      return;
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
      if (state._searchDebounce) clearTimeout(state._searchDebounce);

      state._searchDebounce = setTimeout(() => {
        if (query.length >= 2) {
          const input = document.getElementById('stepper-search');
          if (input) input.value = query;
          state.loadStepData(state.steps[state.currentStep]);
        } else if (query.length === 0) {
          state.stepData = [];
          updateStepperContent(container, state);
        }
      }, 400);
    } else {
      // Клиентская фильтрация
      container.querySelectorAll('.stepper-item').forEach((item) => {
        const text = item.textContent.toLowerCase();
        item.style.display = text.includes(query.toLowerCase()) ? '' : 'none';
      });
    }
  };
}

// ═══════════════════════════════════════════════════════════════
// Фабрика createStepper
// ═══════════════════════════════════════════════════════════════

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
  // ── Объект состояния (все мутабельные данные) ──
  const state = {
    currentStep: 0,
    selections: [],
    stepData: [],
    isLoading: false,
    _loadId: 0,
    _currentSearchMode: null,
    _searchDebounce: null,
    _dataLoaded: false,
    // Ссылки на неизменяемые параметры фабрики
    steps,
    onComplete,
    onCancel,
    container
  };

  /**
   * Переходит к следующему шагу, сохраняя выбранный элемент.
   *
   * @param {number} selectedIndex — индекс выбранного элемента в stepData
   */
  function advanceStep(selectedIndex) {
    const selectedItem = state.stepData[selectedIndex];
    state.selections.push(selectedItem);
    if (selectedItem._skipNext) {
      state.currentStep += 2;
    } else {
      state.currentStep++;
    }
    state.stepData = [];
    render();
  }

  /**
   * Рендерит текущее состояние stepper.
   */
  function render() {
    if (state.currentStep >= steps.length) {
      container.innerHTML = '';
      if (onComplete) {
        onComplete(state.selections);
      }
      return;
    }

    // Сброс pending debounce при переходе на другой шаг
    if (state._searchDebounce) {
      clearTimeout(state._searchDebounce);
      state._searchDebounce = null;
    }
    state._dataLoaded = false;

    const step = steps[state.currentStep];

    if (step.searchMode !== undefined) {
      state._currentSearchMode = step.searchMode;
    } else {
      state._currentSearchMode = null;
    }

    // Динамические заголовки ТОЛЬКО для шага clinic (currentStep === 1)
    let displayTitle = step.title;
    let displayDesc = step.description;
    if (state.currentStep === 1 && state._currentSearchMode !== null) {
      const isClinicMode = state._currentSearchMode === 'clinics';
      displayTitle = isClinicMode ? 'Выбор поликлиники' : 'Поиск врача';
      displayDesc = isClinicMode
        ? 'Выберите поликлинику из списка'
        : `${lucideIcon('search', 14)} Начните вводить фамилию, имя или отчество врача`;
    }

    const isLastStep = state.currentStep === steps.length - 1;
    const isWidget = step.type === 'widget';

    // Определяем HTML-содержимое контентной области
    const contentHTML =
      state.isLoading || (!state._dataLoaded && state.stepData.length === 0)
        ? buildLoadingHTML()
        : buildItemsHTML(state.stepData, step.renderItem);

    container.innerHTML = buildStepperHTML(steps, state.currentStep, {
      displayTitle,
      displayDesc,
      searchPlaceholder: step.searchPlaceholder,
      searchMode: state._currentSearchMode,
      contentHTML,
      canGoBack: state.currentStep > 0,
      isLastStep,
      isWidget
    });

    bindStepperNavigation(container, state);
    loadStepData(step);
  }

  /**
   * Загружает данные для текущего шага.
   *
   * @param {object} step — определение шага
   */
  async function loadStepData(step) {
    const loadId = ++state._loadId;
    state.isLoading = true;
    try {
      state.stepData = await step.loadData(state.selections);
    } catch (error) {
      if (loadId !== state._loadId) return;
      state.stepData = [];
      showError(error.message || 'Ошибка загрузки данных');
      return;
    } finally {
      if (loadId === state._loadId) {
        state.isLoading = false;
        state._dataLoaded = true;
      }
    }
    if (loadId !== state._loadId) return;
    updateStepperContent(container, state);
  }

  /**
   * Показывает сообщение об ошибке с кнопкой «Повторить».
   *
   * @param {string} message — текст ошибки
   */
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
        loadStepData(steps[state.currentStep]);
      });
    }
  }

  // Привязываем методы к state для доступа из внешних хелперов
  state.render = render;
  state.advanceStep = advanceStep;
  state.loadStepData = loadStepData;

  // Первичный рендеринг
  render();

  // ── Публичный API ──
  return {
    /**
     * Перейти к указанному шагу.
     *
     * @param {number} index — индекс шага (0-based)
     */
    goToStep(index) {
      state.currentStep = Math.max(0, Math.min(index, steps.length));
      state.selections.length = Math.min(
        state.selections.length,
        state.currentStep
      );
      state.stepData = [];
      render();
    },

    /**
     * Сбросить stepper к начальному состоянию.
     */
    reset() {
      state.currentStep = 0;
      state.selections.length = 0;
      state.stepData = [];
      render();
    }
  };
}
