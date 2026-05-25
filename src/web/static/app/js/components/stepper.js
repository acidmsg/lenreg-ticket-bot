/**
 * Компонент пошагового выбора (stepper).
 * Универсальный компонент для многошаговых форм.
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

    const progressHtml = steps
      .map((_, i) => {
        let dotClass = 'stepper__step-dot';
        if (i < currentStep) {
          dotClass += ' stepper__step-dot--completed';
        } else if (i === currentStep) {
          dotClass += ' stepper__step-dot--active';
        }
        return `<div class="${dotClass}"></div>`;
      })
      .join('');

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

    container.innerHTML = `
      <div class="stepper">
        <div class="stepper__progress">${progressHtml}</div>
        <h2 class="stepper__title">${escapeHtml(step.title)}</h2>
        <p class="stepper__description">${escapeHtml(step.description)}</p>
        ${searchHtml}
        <div class="stepper__content" id="stepper-content">
          ${isLoading ? renderLoading() : renderItems(stepData, step.renderItem)}
        </div>
        <div class="stepper__actions">
          ${backButtonHtml}
          <button class="btn btn--primary" id="stepper-next" disabled>
            ${currentStep === steps.length - 1 ? '✓ Готово' : 'Далее →'}
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
   * @returns {string} HTML списка
   */
  function renderItems(items, renderItem) {
    if (!items || items.length === 0) {
      return `
        <div class="empty-state">
          <div class="empty-state__icon">📭</div>
          <p class="empty-state__text">Ничего не найдено</p>
        </div>
      `;
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

    // Кнопка «Далее»
    const nextBtn = document.getElementById('stepper-next');
    if (nextBtn) {
      nextBtn.addEventListener('click', () => {
        const selectedIndex = getSelectedIndex();
        if (selectedIndex === null) return;

        const selectedItem = stepData[selectedIndex];
        selections.push(selectedItem);
        currentStep++;
        stepData = [];
        render();
      });
    }

    // Выбор элемента списка
    const items = container.querySelectorAll('.stepper-item');
    items.forEach((item) => {
      item.addEventListener('click', () => {
        // Снимаем выделение со всех
        items.forEach((i) => i.classList.remove('stepper-item--selected'));
        // Выделяем текущий
        item.classList.add('stepper-item--selected');

        // Активируем кнопку «Далее»
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
      stepData = await step.loadData();
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
    if (isLoading) {
      contentEl.innerHTML = renderLoading();
    } else {
      contentEl.innerHTML = renderItems(stepData, step.renderItem);
      // Перепривязываем события после обновления контента
      const items = container.querySelectorAll('.stepper-item');
      items.forEach((item) => {
        item.addEventListener('click', () => {
          items.forEach((i) => i.classList.remove('stepper-item--selected'));
          item.classList.add('stepper-item--selected');
          const next = document.getElementById('stepper-next');
          if (next) next.disabled = false;
        });
      });

      const searchInput = document.getElementById('stepper-search');
      if (searchInput) {
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
