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

  /** Текущий режим поиска (null | 'clinics' | 'doctors') */
  let _currentSearchMode = null;

  /** Таймер debounce для API-поиска */
  let _searchDebounce = null;

  /**
   * Переходит к следующему шагу, сохраняя выбранный элемент.
   *
   * @param {number} selectedIndex — индекс выбранного элемента в stepData
   */
  function advanceStep(selectedIndex) {
    const selectedItem = stepData[selectedIndex];
    selections.push(selectedItem);
    currentStep++;
    stepData = [];
    render();
  }

  /**
   * Рендерит текущее состояние stepper.
   */
  function render() {
    if (currentStep >= steps.length) {
      // Все шаги пройдены — вызываем onComplete
      container.innerHTML = '';
      if (onComplete) {
        onComplete(selections);
      }
      return;
    }

    const step = steps[currentStep];

    // Инициализируем режим поиска из конфига шага
    if (step.searchMode !== undefined) {
      _currentSearchMode = step.searchMode;
    } else {
      _currentSearchMode = null;
    }

    // Пиксельные точки — визуальный индикатор шагов
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

    // Переключатель режимов поиска (если задан в конфиге шага)
    const modeSwitcherHtml =
      step.searchMode !== undefined ? renderModeSwitcher(step.searchMode) : '';

    const searchHtml = step.searchPlaceholder
      ? `
        <div class="search-bar">
          <input
            type="text"
            class="search-bar__input"
            placeholder="${escapeHtml(step.searchPlaceholder)}"
            id="stepper-search"
            autocomplete="off"
          >
        </div>
      `
      : '';

    const canGoBack = currentStep > 0;
    const backButtonHtml = canGoBack
      ? `<button class="btn btn--secondary" id="stepper-back">← Назад</button>`
      : `<button class="btn btn--danger" id="stepper-cancel">✕ Отмена</button>`;

    const isLastStep = currentStep === steps.length - 1;
    // На не-последних шагах кнопка «Далее» скрыта через CSS-класс .stepper__btn--next
    const nextBtnClass = isLastStep ? '' : ' stepper__btn--next';

    container.innerHTML = `
      <div class="stepper">
        <div class="stepper__progress">${progressHtml}</div>
        <h2 class="stepper__title">${escapeHtml(step.title)}</h2>
        <p class="stepper__description">${escapeHtml(step.description)}</p>
        ${modeSwitcherHtml}
        ${searchHtml}
        <div class="stepper__content" id="stepper-content">
          ${isLoading ? renderLoading() : renderItems(stepData, step.renderItem, isLastStep)}
        </div>
        <div class="stepper__actions">
          ${backButtonHtml}
          <button class="btn btn--primary${nextBtnClass}" id="stepper-next"${isLastStep ? '' : ' disabled'}>
            ${isLastStep ? '✓ Готово' : 'Далее →'}
          </button>
        </div>
      </div>
    `;

    bindEvents(step);
    loadStepData(step);
  }

  /**
   * Рендерит индикатор загрузки.
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
   * Рендерит список элементов.
   *
   * @param {Array} items — данные для рендеринга
   * @param {Function} renderItem — функция рендеринга одного элемента
   * @param {boolean} [isLastStep=false] — является ли текущий шаг последним (подтверждение)
   * @returns {string} HTML списка
   */
  function renderItems(items, renderItem, isLastStep = false) {
    if (!items || items.length === 0) {
      return `
        <div class="empty-state">
          <div class="empty-state__icon">📭</div>
          <p class="empty-state__text">Ничего не найдено</p>
        </div>
      `;
    }

    // Для шага подтверждения рендерим без списка и без кликабельных стилей
    if (isLastStep) {
      return items
        .map(
          (item) => `
        <div class="stepper-confirm">
          ${renderItem(item)}
        </div>
      `
        )
        .join('');
    }

    const itemsHtml = items
      .map(
        (item, index) => `
        <li class="list__item stepper-item" data-index="${index}">
          ${renderItem(item)}
        </li>
      `
      )
      .join('');

    return `<ul class="list">${itemsHtml}</ul>`;
  }

  /**
   * Привязывает обработчики событий.
   *
   * @param {object} step — текущий шаг
   */
  function bindEvents(step) {
    // Кнопка «Назад»
    const backBtn = document.getElementById('stepper-back');
    if (backBtn) {
      backBtn.addEventListener('click', () => {
        if (currentStep > 0) {
          currentStep--;
          selections.pop();
          stepData = [];
          render();
        }
      });
    }

    // Кнопка «Отмена»
    const cancelBtn = document.getElementById('stepper-cancel');
    if (cancelBtn) {
      cancelBtn.addEventListener('click', () => {
        if (onCancel) {
          onCancel();
        }
      });
    }

    // Кнопка «Готово» (только на последнем шаге)
    const nextBtn = document.getElementById('stepper-next');
    if (nextBtn) {
      const isLastStep = currentStep === steps.length - 1;
      if (isLastStep) {
        nextBtn.addEventListener('click', () => {
          let selectedIndex = getSelectedIndex();

          // Для последнего шага (подтверждение) — всегда берём первый (и единственный) элемент
          if (selectedIndex === null && stepData.length === 1) {
            selectedIndex = 0;
          }

          if (selectedIndex === null) return;

          const selectedItem = stepData[selectedIndex];
          selections.push(selectedItem);
          currentStep++;
          stepData = [];
          render();
        });
      }
      // Для не-последних шагов кнопка скрыта CSS и не требует обработчика
    }

    // Выбор элемента списка — автопереход на следующий шаг
    const isLastStep = currentStep === steps.length - 1;
    const items = container.querySelectorAll('.stepper-item');
    items.forEach((item) => {
      item.addEventListener('click', () => {
        // Снимаем выделение со всех
        items.forEach((i) => i.classList.remove('stepper-item--selected'));
        // Выделяем текущий
        item.classList.add('stepper-item--selected');

        // Автопереход для всех шагов кроме последнего (подтверждение)
        if (!isLastStep) {
          const idx = parseInt(item.getAttribute('data-index'), 10);
          if (!isNaN(idx) && stepData[idx]) {
            advanceStep(idx);
          }
          return;
        }

        // На последнем шаге — активируем кнопку «Готово»
        const next = document.getElementById('stepper-next');
        if (next) {
          next.disabled = false;
        }
      });
    });

    // Поиск/фильтрация
    const searchInput = document.getElementById('stepper-search');
    if (searchInput) {
      searchInput.addEventListener('input', (e) => {
        const query = e.target.value.toLowerCase();
        const allItems = container.querySelectorAll('.stepper-item');
        allItems.forEach((item) => {
          const text = item.textContent.toLowerCase();
          item.style.display = text.includes(query) ? '' : 'none';
        });
      });
    }

    // Переключатель режимов поиска (клиники / врачи)
    const modeBtns = container.querySelectorAll('.search-mode-btn');
    if (modeBtns.length > 0 && step.onSearchModeChange) {
      modeBtns.forEach((btn) => {
        btn.addEventListener('click', () => {
          const mode = btn.dataset.mode;
          if (!mode) return;

          // Обновляем визуальное состояние кнопок
          modeBtns.forEach((b) =>
            b.classList.remove('search-mode-btn--active')
          );
          btn.classList.add('search-mode-btn--active');

          // Уведомляем внешний код о смене режима
          step.onSearchModeChange(mode);

          // Обновляем placeholder строки поиска
          const searchInputEl = document.getElementById('stepper-search');
          if (searchInputEl) {
            searchInputEl.placeholder =
              mode === 'doctors'
                ? 'Поиск по имени врача...'
                : step.searchPlaceholder || 'Поиск по названию...';
            searchInputEl.value = '';
          }

          // Перезагружаем данные для нового режима
          loadStepData(step);
        });
      });
    }
  }

  /**
   * Возвращает индекс выбранного элемента.
   *
   * @returns {number|null} индекс или null, если ничего не выбрано
   */
  function getSelectedIndex() {
    const selected = container.querySelector('.stepper-item--selected');
    if (!selected) return null;
    const index = selected.getAttribute('data-index');
    return index !== null ? parseInt(index, 10) : null;
  }

  /**
   * Загружает данные для текущего шага.
   *
   * @param {object} step — конфигурация шага
   */
  async function loadStepData(step) {
    if (!step.loadData) {
      stepData = [];
      updateContent();
      return;
    }

    isLoading = true;
    updateContent();

    try {
      stepData = await step.loadData(selections);
    } catch (error) {
      stepData = [];
      showError(error.message || 'Ошибка загрузки данных');
      return;
    } finally {
      isLoading = false;
    }

    updateContent();
  }

  /**
   * Обновляет содержимое stepper (список элементов).
   */
  function updateContent() {
    const contentEl = document.getElementById('stepper-content');
    if (!contentEl) return;

    const step = steps[currentStep];
    const isLastStep = currentStep === steps.length - 1;

    if (isLoading) {
      contentEl.innerHTML = renderLoading();
    } else {
      contentEl.innerHTML = renderItems(stepData, step.renderItem, isLastStep);

      // Для шага подтверждения не привязываем события выбора
      if (isLastStep) {
        // Поиск на шаге подтверждения не нужен
        return;
      }

      // Перепривязываем события после обновления контента
      const items = container.querySelectorAll('.stepper-item');
      items.forEach((item) => {
        item.addEventListener('click', () => {
          items.forEach((i) => i.classList.remove('stepper-item--selected'));
          item.classList.add('stepper-item--selected');

          // Автопереход при клике (кроме последнего шага — сюда не попадаем)
          const idx = parseInt(item.getAttribute('data-index'), 10);
          if (!isNaN(idx) && stepData[idx]) {
            advanceStep(idx);
          }
        });
      });

      // Авто-выбор, если на шаге только один элемент (кроме последнего шага)
      if (stepData.length === 1 && items.length === 1) {
        items[0].classList.add('stepper-item--selected');
        // Автопереход с небольшой задержкой для визуального отклика
        setTimeout(() => {
          // Проверяем, что мы всё ещё на том же шаге (не ушли назад/вперёд)
          if (currentStep < steps.length - 1 && stepData.length === 1) {
            advanceStep(0);
          }
        }, 200);
      }

      const searchInput = document.getElementById('stepper-search');
      if (searchInput) {
        const step = steps[currentStep];

        if (_currentSearchMode === 'doctors' && step.searchMode !== undefined) {
          // API-поиск с debounce 400ms для глобального поиска врачей
          searchInput.addEventListener('input', (e) => {
            const query = e.target.value;

            if (_searchDebounce) {
              clearTimeout(_searchDebounce);
            }

            _searchDebounce = setTimeout(() => {
              if (query.length >= 2 || query.length === 0) {
                loadStepData(step);
              }
            }, 400);
          });
        } else {
          // Клиентская фильтрация (обычный режим)
          searchInput.addEventListener('input', (e) => {
            const query = e.target.value.toLowerCase();
            container.querySelectorAll('.stepper-item').forEach((item) => {
              const text = item.textContent.toLowerCase();
              item.style.display = text.includes(query) ? '' : 'none';
            });
          });
        }
      }
    }
  }

  /**
   * Показывает сообщение об ошибке.
   *
   * @param {string} message — текст ошибки
   */
  function showError(message) {
    const contentEl = document.getElementById('stepper-content');
    if (!contentEl) return;

    contentEl.innerHTML = `
      <div class="error-state">
        <p class="error-state__text">${escapeHtml(message)}</p>
        <button class="btn btn--primary" id="stepper-retry">🔄 Повторить</button>
      </div>
    `;

    const retryBtn = document.getElementById('stepper-retry');
    if (retryBtn) {
      retryBtn.addEventListener('click', () => {
        loadStepData(steps[currentStep]);
      });
    }
  }

  // Запуск рендеринга
  render();

  // Возвращаем объект управления
  return {
    /** Перейти к указанному шагу */
    goToStep: (index) => {
      currentStep = Math.max(0, Math.min(index, steps.length));
      selections.length = Math.min(selections.length, currentStep);
      stepData = [];
      render();
    },
    /** Сбросить stepper */
    reset: () => {
      currentStep = 0;
      selections.length = 0;
      stepData = [];
      render();
    }
  };
}

/**
 * Рендерит переключатель режимов поиска (клиники / врачи).
 *
 * @param {string} mode — текущий режим ('clinics' или 'doctors')
 * @returns {string} HTML переключателя
 */
function renderModeSwitcher(mode) {
  return `
    <div class="search-mode-switcher">
      <button class="search-mode-btn ${mode === 'clinics' ? 'search-mode-btn--active' : ''}"
              data-mode="clinics">🏥 Клиники</button>
      <button class="search-mode-btn ${mode === 'doctors' ? 'search-mode-btn--active' : ''}"
              data-mode="doctors">👨‍⚕️ Врачи</button>
    </div>
  `;
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
