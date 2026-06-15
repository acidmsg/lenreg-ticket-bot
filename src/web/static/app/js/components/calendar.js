/**
 * Компоненты календаря для Telegram Mini App.
 *
 * Три независимые фабрики:
 *   - createCalendar()   — календарь с навигацией по месяцам
 *   - createDateInput()  — поле ввода с маской ДД.ММ.ГГГГ и валидацией
 *   - createDatePicker() — композитный виджет (календарь + поле ввода)
 *
 * Внутренний формат даты: 'YYYY-MM-DD' (ISO).
 * Внешний формат (getValue/onChange): 'ДД.ММ.ГГГГ'.
 *
 * @module components/calendar
 */

// ============================================================
// Утилитные функции
// ============================================================

/**
 * Форматирует Date → 'ДД.ММ.ГГГГ'.
 *
 * @param {Date} date
 * @returns {string}
 */
function formatDate(date) {
  const d = String(date.getDate()).padStart(2, '0');
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const y = date.getFullYear();
  return `${d}.${m}.${y}`;
}

/**
 * Парсит 'ДД.ММ.ГГГГ' → { day, month, year }.
 *
 * @param {string} str
 * @returns {{ day: number, month: number, year: number } | null}
 */
function parseDate(dateString) {
  if (!dateString || typeof dateString !== 'string') return null;
  const parts = dateString.split('.');
  if (parts.length !== 3) return null;
  const day = parseInt(parts[0], 10);
  const month = parseInt(parts[1], 10);
  const year = parseInt(parts[2], 10);
  if (isNaN(day) || isNaN(month) || isNaN(year)) return null;
  return { day, month, year };
}

/**
 * Конвертирует 'ДД.ММ.ГГГГ' → 'YYYY-MM-DD'.
 *
 * @param {string} displayStr
 * @returns {string | null}
 */
function displayToISO(displayStr) {
  const parsed = parseDate(displayStr);
  if (!parsed) return null;
  return `${parsed.year}-${String(parsed.month).padStart(2, '0')}-${String(parsed.day).padStart(2, '0')}`;
}

/**
 * Конвертирует 'YYYY-MM-DD' → 'ДД.ММ.ГГГГ'.
 *
 * @param {string} isoStr
 * @returns {string}
 */
function isoToDisplay(isoStr) {
  if (!isoStr) return '';
  const parts = isoStr.split('-');
  if (parts.length !== 3) return '';
  return `${parts[2]}.${parts[1]}.${parts[0]}`;
}

/**
 * Возвращает 'YYYY-MM-DD' (ISO) для сегодняшней даты.
 *
 * @returns {string}
 */
function getTodayISO() {
  const now = new Date();
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, '0');
  const d = String(now.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

/**
 * Проверяет, находится ли 'YYYY-MM-DD' в диапазоне [minISO, maxISO].
 *
 * @param {string} dateISO
 * @param {string} [minISO]
 * @param {string} [maxISO]
 * @returns {boolean}
 */
function isDateInRange(dateISO, minISO, maxISO) {
  if (minISO && dateISO < minISO) return false;
  if (maxISO && dateISO > maxISO) return false;
  return true;
}

/**
 * Проверяет, является ли дата ('YYYY-MM-DD') реальной.
 *
 * @param {string} dateISO
 * @returns {boolean}
 */
function isValidDate(dateISO) {
  const parts = dateISO.split('-');
  if (parts.length !== 3) return false;
  const y = parseInt(parts[0], 10);
  const m = parseInt(parts[1], 10);
  const d = parseInt(parts[2], 10);
  const date = new Date(y, m - 1, d);
  return (
    date.getFullYear() === y &&
    date.getMonth() === m - 1 &&
    date.getDate() === d
  );
}

/**
 * Возвращает массив из 42 дней (6 недель × 7 дней) для календарной сетки.
 *
 * @param {number} year
 * @param {number} month — 1-based (1-12)
 * @returns {Array<{ day: number, month: number, year: number, isCurrentMonth: boolean, iso: string }>}
 */
function getCalendarDays(year, month) {
  const firstDay = new Date(year, month - 1, 1);
  let startDow = firstDay.getDay() - 1;
  if (startDow < 0) startDow = 6;

  const startDate = new Date(year, month - 1, 1 - startDow);

  const days = [];
  for (let i = 0; i < 42; i++) {
    const d = new Date(startDate);
    d.setDate(startDate.getDate() + i);
    const dy = d.getFullYear();
    const dm = d.getMonth() + 1;
    const dd = d.getDate();
    days.push({
      day: dd,
      month: dm,
      year: dy,
      isCurrentMonth: dm === month && dy === year,
      iso: `${dy}-${String(dm).padStart(2, '0')}-${String(dd).padStart(2, '0')}`
    });
  }
  return days;
}

/**
 * Возвращает названия дней недели (краткие, Пн-Вс).
 *
 * @returns {string[]}
 */
function getWeekdayNames() {
  return ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];
}

/**
 * Возвращает название месяца на русском.
 *
 * @param {number} month — 1-based
 * @returns {string}
 */
function getMonthName(month) {
  const names = [
    'Январь',
    'Февраль',
    'Март',
    'Апрель',
    'Май',
    'Июнь',
    'Июль',
    'Август',
    'Сентябрь',
    'Октябрь',
    'Ноябрь',
    'Декабрь'
  ];
  return names[month - 1] || '';
}

/**
 * Возвращает краткое название месяца (3 буквы).
 *
 * @param {number} month — 1-based
 * @returns {string}
 */
function getShortMonthName(month) {
  const names = [
    'Янв',
    'Фев',
    'Мар',
    'Апр',
    'Май',
    'Июн',
    'Июл',
    'Авг',
    'Сен',
    'Окт',
    'Ноя',
    'Дек'
  ];
  return names[month - 1] || '';
}

/**
 * Рендерит попап выбора месяца/года.
 *
 * @param {HTMLElement} container — DOM-элемент для рендеринга попапа
 * @param {number} currentYear — текущий год просмотра
 * @param {number} currentMonth — текущий месяц просмотра (1-based)
 * @param {Function} onSelect — колбэк onSelect(year, month)
 */
function renderMonthPicker(container, currentYear, currentMonth, onSelect) {
  let pickerYear = currentYear;

  function render() {
    container.innerHTML = `
      <div class="calendar__month-picker__year-row">
        <button type="button" class="calendar__month-picker__year-nav" data-action="prev" aria-label="Предыдущий год">&laquo;</button>
        <span class="calendar__month-picker__year">${pickerYear}</span>
        <button type="button" class="calendar__month-picker__year-nav" data-action="next" aria-label="Следующий год">&raquo;</button>
      </div>
      <div class="calendar__month-picker__grid">
        ${Array.from({ length: 12 }, (_, i) => {
          const m = i + 1;
          const isSelected = m === currentMonth && pickerYear === currentYear;
          return `<button type="button" class="calendar__month-picker__month${isSelected ? ' calendar__month-picker__month--selected' : ''}" data-month="${m}">${getShortMonthName(m)}</button>`;
        }).join('')}
      </div>
    `;

    container
      .querySelectorAll('.calendar__month-picker__year-nav')
      .forEach((btn) => {
        btn.addEventListener('click', () => {
          const action = btn.dataset.action;
          pickerYear += action === 'prev' ? -1 : 1;
          render();
        });
      });

    container
      .querySelectorAll('.calendar__month-picker__month')
      .forEach((btn) => {
        btn.addEventListener('click', () => {
          const month = parseInt(btn.dataset.month, 10);
          onSelect(pickerYear, month);
        });
      });
  }

  render();
  container.hidden = false;
}

// ============================================================
// Хелперы для createCalendar
// ============================================================

/**
 * Строит HTML-строку сетки дней календаря.
 *
 * @param {Array} days — массив дней из getCalendarDays()
 * @param {string} todayISO — ISO-строка сегодняшней даты
 * @param {string|null} selectedISO — ISO-строка выбранной даты
 * @param {string} [min] — минимальная дата 'YYYY-MM-DD'
 * @param {string} [max] — максимальная дата 'YYYY-MM-DD'
 * @returns {string}
 */
function buildCalendarGridHTML(days, todayISO, selectedISO, min, max) {
  return days
    .map((d) => {
      let cssClass = 'calendar__day';
      if (!d.isCurrentMonth) cssClass += ' calendar__day--other-month';
      if (d.iso === todayISO) cssClass += ' calendar__day--today';
      if (d.iso === selectedISO) cssClass += ' calendar__day--selected';
      if (!isDateInRange(d.iso, min, max))
        cssClass += ' calendar__day--disabled';

      const disabled = !isDateInRange(d.iso, min, max);
      return `<button class="${cssClass}" type="button" data-iso="${d.iso}"${disabled ? ' disabled' : ''} aria-label="${d.day} ${getMonthName(d.month)} ${d.year}">${d.day}</button>`;
    })
    .join('');
}

/**
 * Проверяет, можно ли перейти к указанному месяцу с учётом [min, max].
 *
 * @param {number} year
 * @param {number} month — 1-based
 * @param {string} [min] — минимальная дата 'YYYY-MM-DD'
 * @param {string} [max] — максимальная дата 'YYYY-MM-DD'
 * @returns {boolean}
 */
function canNavigateToMonth(year, month, min, max) {
  const firstDay = `${year}-${String(month).padStart(2, '0')}-01`;
  const lastDayDate = new Date(year, month, 0);
  const lastDay = `${year}-${String(month).padStart(2, '0')}-${String(lastDayDate.getDate()).padStart(2, '0')}`;

  if (max && firstDay > max) return false;
  if (min && lastDay < min) return false;
  return true;
}

/**
 * Вычисляет новый {year, month} после навигации.
 *
 * @param {'prev'|'next'} direction — направление
 * @param {number} currentYear
 * @param {number} currentMonth — 1-based
 * @returns {{ year: number, month: number }}
 */
function navigateMonth(direction, currentYear, currentMonth) {
  let year = currentYear;
  let month = currentMonth;

  if (direction === 'prev') {
    if (month === 1) {
      month = 12;
      year--;
    } else {
      month--;
    }
  } else {
    if (month === 12) {
      month = 1;
      year++;
    } else {
      month++;
    }
  }

  return { year, month };
}

/**
 * Добавляет указанное количество дней к дате в формате ISO.
 *
 * @param {string} iso — 'YYYY-MM-DD'
 * @param {number} days — количество дней (может быть отрицательным)
 * @returns {string} новая дата в формате 'YYYY-MM-DD'
 */
function addDaysToISO(iso, days) {
  const parts = iso.split('-');
  const y = parseInt(parts[0], 10);
  const m = parseInt(parts[1], 10);
  const d = parseInt(parts[2], 10);
  const date = new Date(y, m - 1, d);
  date.setDate(date.getDate() + days);
  const ny = date.getFullYear();
  const nm = String(date.getMonth() + 1).padStart(2, '0');
  const nd = String(date.getDate()).padStart(2, '0');
  return `${ny}-${nm}-${nd}`;
}

// ============================================================
// Хелперы для createDateInput
// ============================================================

/**
 * Применяет маску ДД.ММ.ГГГГ к строке (чистая функция, без DOM).
 *
 * @param {string} value — исходное значение (может содержать нецифровые символы)
 * @returns {string} значение с маской
 */
function applyDateMask(value) {
  let cleaned = value.replace(/[^\d]/g, '');
  if (cleaned.length > 8) {
    cleaned = cleaned.substring(0, 8);
  }

  let result = '';
  if (cleaned.length > 0) {
    result += cleaned.substring(0, 2);
  }
  if (cleaned.length >= 2) {
    result += '.';
  }
  if (cleaned.length > 2) {
    result += cleaned.substring(2, 4);
  }
  if (cleaned.length >= 5) {
    result += '.';
  }
  if (cleaned.length > 4) {
    result += cleaned.substring(4, 8);
  }

  return result;
}

/**
 * Вычисляет позицию курсора после применения маски.
 *
 * @param {string} maskedValue — значение после applyDateMask()
 * @param {number} digitsBeforeCursor — количество цифр до курсора в исходном значении
 * @returns {number} новая позиция курсора
 */
function computeCursorPosition(maskedValue, digitsBeforeCursor) {
  let newCursorPos = 0;
  let digitCount = 0;
  for (let i = 0; i < maskedValue.length; i++) {
    if (/\d/.test(maskedValue[i])) {
      if (digitCount >= digitsBeforeCursor) break;
      digitCount++;
    }
    newCursorPos = i + 1;
  }

  // Если сразу за позицией курсора — точка, перепрыгиваем её
  if (newCursorPos < maskedValue.length && maskedValue[newCursorPos] === '.') {
    newCursorPos++;
  }

  return newCursorPos;
}

/**
 * Валидирует строку даты 'ДД.ММ.ГГГГ'.
 *
 * @param {string} dateString
 * @returns {{ valid: boolean, message: string }}
 */
function validateDateString(dateString) {
  if (!dateString || dateString.length < 10) {
    return { valid: false, message: '' };
  }

  const parsed = parseDate(dateString);
  if (!parsed) {
    return { valid: false, message: 'Некорректный формат даты' };
  }

  const { day, month, year } = parsed;

  if (month < 1 || month > 12) {
    return { valid: false, message: 'Месяц должен быть от 01 до 12' };
  }

  if (year < 1900 || year > 2099) {
    return { valid: false, message: 'Год должен быть от 1900 до 2099' };
  }

  const date = new Date(year, month - 1, day);
  if (
    date.getFullYear() !== year ||
    date.getMonth() !== month - 1 ||
    date.getDate() !== day
  ) {
    return { valid: false, message: 'Такой даты не существует' };
  }

  return { valid: true, message: '' };
}

// ============================================================
// createCalendar()
// ============================================================

/**
 * Создаёт экземпляр календаря и рендерит его в указанный контейнер.
 *
 * @param {object} options
 * @param {HTMLElement} options.container — DOM-элемент для рендеринга
 * @param {string} [options.value] — начальная дата в формате 'ДД.ММ.ГГГГ'
 * @param {Function} [options.onChange] — колбэк при выборе даты: onChange(dateString)
 * @param {string} [options.min] — минимальная дата в формате 'YYYY-MM-DD' (включительно)
 * @param {string} [options.max] — максимальная дата в формате 'YYYY-MM-DD' (включительно)
 * @returns {object} управляющий объект
 */
export function createCalendar({ container, value, onChange, min, max }) {
  // Внутреннее состояние
  let selectedISO = value ? displayToISO(value) : null;
  const todayISO = getTodayISO();

  // Начальный месяц/год: из value или сегодня
  let viewYear, viewMonth;
  if (selectedISO) {
    const parts = selectedISO.split('-');
    viewYear = parseInt(parts[0], 10);
    viewMonth = parseInt(parts[1], 10);
  } else {
    const now = new Date();
    viewYear = now.getFullYear();
    viewMonth = now.getMonth() + 1;
  }

  // Строим DOM
  container.innerHTML = `
    <div class="calendar">
      <div class="calendar__header">
        <button class="calendar__nav calendar__nav--prev" type="button" aria-label="Предыдущий месяц"><</button>
        <button type="button" class="calendar__month-label"></button>
        <button class="calendar__nav calendar__nav--next" type="button" aria-label="Следующий месяц">></button>
      </div>
      <div class="calendar__month-picker" hidden></div>
      <div class="calendar__weekdays">
        ${getWeekdayNames()
          .map((n) => `<span>${n}</span>`)
          .join('')}
      </div>
      <div class="calendar__grid"></div>
    </div>
  `;

  const monthLabel = container.querySelector('.calendar__month-label');
  const gridEl = container.querySelector('.calendar__grid');
  const prevBtn = container.querySelector('.calendar__nav--prev');
  const nextBtn = container.querySelector('.calendar__nav--next');

  /**
   * Отрисовывает сетку дней для текущих viewYear/viewMonth.
   */
  function renderGrid() {
    const days = getCalendarDays(viewYear, viewMonth);
    monthLabel.textContent = `${getMonthName(viewMonth)} ${viewYear}`;
    gridEl.innerHTML = buildCalendarGridHTML(
      days,
      todayISO,
      selectedISO,
      min,
      max
    );
    updateNavButtons();
  }

  /**
   * Обновляет состояние (disabled) кнопок навигации.
   */
  function updateNavButtons() {
    if (prevBtn) {
      const prev = navigateMonth('prev', viewYear, viewMonth);
      prevBtn.disabled = !canNavigateToMonth(prev.year, prev.month, min, max);
    }
    if (nextBtn) {
      const next = navigateMonth('next', viewYear, viewMonth);
      nextBtn.disabled = !canNavigateToMonth(next.year, next.month, min, max);
    }
  }

  /**
   * Выбирает день и уведомляет через onChange.
   *
   * @param {string} iso
   */
  function selectDay(iso) {
    if (!isDateInRange(iso, min, max)) return;

    selectedISO = iso;

    // Обновляем визуальное выделение
    gridEl.querySelectorAll('.calendar__day').forEach((btn) => {
      btn.classList.toggle(
        'calendar__day--selected',
        btn.getAttribute('data-iso') === iso
      );
    });

    if (onChange) {
      onChange(isoToDisplay(iso));
    }
  }

  // Обработчик кликов по дням
  gridEl.addEventListener('click', (e) => {
    const btn = e.target.closest('.calendar__day');
    if (!btn || btn.disabled) return;
    const iso = btn.getAttribute('data-iso');
    if (iso) selectDay(iso);
  });

  // Клавиатурная навигация: стрелки внутри календаря
  container.addEventListener('keydown', (e) => {
    const active = document.activeElement;
    if (!active || !active.classList.contains('calendar__day')) return;

    const currentISO = active.getAttribute('data-iso');
    if (!currentISO) return;

    let newISO = null;

    switch (e.key) {
      case 'ArrowLeft':
        newISO = addDaysToISO(currentISO, -1);
        break;
      case 'ArrowRight':
        newISO = addDaysToISO(currentISO, 1);
        break;
      case 'ArrowUp':
        newISO = addDaysToISO(currentISO, -7);
        break;
      case 'ArrowDown':
        newISO = addDaysToISO(currentISO, 7);
        break;
      case 'Enter':
      case ' ': {
        e.preventDefault();
        if (!active.disabled) selectDay(currentISO);
        return;
      }
    }

    if (newISO) {
      e.preventDefault();
      // Переключить месяц если нужно
      const nParts = newISO.split('-');
      const ny = parseInt(nParts[0], 10);
      const nm = parseInt(nParts[1], 10);
      if (ny !== viewYear || nm !== viewMonth) {
        viewYear = ny;
        viewMonth = nm;
        renderGrid();
      }
      // Сфокусировать новую кнопку
      const targetBtn = gridEl.querySelector(`[data-iso="${newISO}"]`);
      if (targetBtn && !targetBtn.disabled) {
        targetBtn.focus();
      }
    }
  });

  // Навигация по месяцам
  prevBtn.addEventListener('click', () => {
    const next = navigateMonth('prev', viewYear, viewMonth);
    viewYear = next.year;
    viewMonth = next.month;
    renderGrid();
  });

  nextBtn.addEventListener('click', () => {
    const next = navigateMonth('next', viewYear, viewMonth);
    viewYear = next.year;
    viewMonth = next.month;
    renderGrid();
  });

  // Клик по метке месяца — открыть попап выбора месяца/года
  monthLabel.addEventListener('click', () => {
    const pickerEl = container.querySelector('.calendar__month-picker');
    if (!pickerEl) return;

    if (!pickerEl.hidden) {
      pickerEl.hidden = true;
      return;
    }

    renderMonthPicker(pickerEl, viewYear, viewMonth, (year, month) => {
      viewYear = year;
      viewMonth = month;
      renderGrid();
      pickerEl.hidden = true;
    });
  });

  // Закрытие попапа при клике вне
  document.addEventListener('click', (e) => {
    const pickerEl = container.querySelector('.calendar__month-picker');
    if (!pickerEl || pickerEl.hidden) return;
    if (!container.contains(e.target)) {
      pickerEl.hidden = true;
    }
  });

  // Первичный рендеринг
  renderGrid();

  // ── Управляющий объект ──
  return {
    /**
     * Установить выбранную дату (строка 'ДД.ММ.ГГГГ').
     *
     * @param {string} dateString
     */
    setValue(dateString) {
      const iso = displayToISO(dateString);
      if (iso) {
        selectedISO = iso;
        const parts = iso.split('-');
        viewYear = parseInt(parts[0], 10);
        viewMonth = parseInt(parts[1], 10);
        renderGrid();
      }
    },

    /**
     * Получить текущую выбранную дату.
     *
     * @returns {string | null} дата в формате 'ДД.ММ.ГГГГ' или null
     */
    getValue() {
      return selectedISO ? isoToDisplay(selectedISO) : null;
    },

    /**
     * Переключить на указанный месяц (1-12) и год.
     *
     * @param {number} year
     * @param {number} month — 1-based
     */
    goToMonth(year, month) {
      viewYear = year;
      viewMonth = month;
      renderGrid();
    },

    /**
     * Уничтожить экземпляр (очистить контейнер).
     */
    destroy() {
      container.innerHTML = '';
    }
  };
}

// ============================================================
// createDateInput()
// ============================================================

/**
 * Создаёт поле ввода с маской ДД.ММ.ГГГГ и валидацией.
 *
 * @param {object} options
 * @param {HTMLElement} options.container — DOM-элемент для рендеринга
 * @param {string} [options.value] — начальное значение в формате 'ДД.ММ.ГГГГ'
 * @param {Function} [options.onChange] — колбэк при изменении валидной даты: onChange(dateString)
 * @param {string} [options.placeholder] — плейсхолдер (по умолчанию 'ДД.ММ.ГГГГ')
 * @returns {object} управляющий объект
 */
export function createDateInput({ container, value, onChange, placeholder }) {
  const placeholderText = placeholder || 'ДД.ММ.ГГГГ';

  container.innerHTML = `
    <div class="date-input">
      <input
        type="text"
        class="date-input__field"
        inputmode="numeric"
        placeholder="${placeholderText}"
        maxlength="10"
        autocomplete="off"
      />
      <p class="date-input__error" hidden>Некорректная дата</p>
    </div>
  `;

  const inputEl = container.querySelector('.date-input__field');
  const errorEl = container.querySelector('.date-input__error');

  // Установка начального значения
  if (value) {
    inputEl.value = value;
  }

  /**
   * Обработчик события input.
   */
  function handleInput() {
    if (inputEl._masking) return;
    inputEl._masking = true;

    const cursorPos = inputEl.selectionStart;
    const oldValue = inputEl.value;

    // Считаем, сколько цифр было до курсора в старом значении
    const digitsBeforeCursor = oldValue
      .substring(0, cursorPos)
      .replace(/[^\d]/g, '').length;

    const masked = applyDateMask(oldValue);
    inputEl.value = masked;

    // Вычисляем новую позицию курсора
    const newCursorPos = computeCursorPosition(masked, digitsBeforeCursor);
    inputEl.setSelectionRange(newCursorPos, newCursorPos);
    inputEl._masking = false;

    // Валидация при полном вводе
    clearError();

    if (masked.length === 10) {
      const validation = validateDateString(masked);
      if (!validation.valid) {
        setError(validation.message);
      } else if (onChange) {
        onChange(masked);
      }
    }
  }

  /**
   * Обработчик keydown для Backspace/Delete.
   *
   * @param {KeyboardEvent} e
   */
  function handleKeyDown(e) {
    if (e.key === 'Backspace' || e.key === 'Delete') {
      const pos = inputEl.selectionStart;
      if (
        e.key === 'Backspace' &&
        pos > 0 &&
        inputEl.value.charAt(pos - 1) === '.'
      ) {
        e.preventDefault();
        const val = inputEl.value;
        inputEl.value = val.substring(0, pos - 2) + val.substring(pos);
        inputEl.setSelectionRange(pos - 2, pos - 2);
        handleInput();
      } else if (
        e.key === 'Delete' &&
        pos < inputEl.value.length &&
        inputEl.value.charAt(pos) === '.'
      ) {
        e.preventDefault();
        const val = inputEl.value;
        inputEl.value = val.substring(0, pos) + val.substring(pos + 1);
        inputEl.setSelectionRange(pos, pos);
        handleInput();
      }
    }
  }

  /**
   * Показать ошибку валидации.
   *
   * @param {string} message
   */
  function setError(message) {
    inputEl.classList.add('date-input__field--error');
    errorEl.textContent = message;
    errorEl.hidden = false;
  }

  /**
   * Снять ошибку.
   */
  function clearError() {
    inputEl.classList.remove('date-input__field--error');
    errorEl.hidden = true;
  }

  // Навешиваем обработчики
  inputEl.addEventListener('input', handleInput);
  inputEl.addEventListener('keydown', handleKeyDown);

  // ── Управляющий объект ──
  return {
    /**
     * Установить значение.
     *
     * @param {string} dateString — 'ДД.ММ.ГГГГ'
     */
    setValue(dateString) {
      inputEl.value = dateString || '';
      clearError();
    },

    /**
     * Получить текущее значение.
     *
     * @returns {string} дата в формате 'ДД.ММ.ГГГГ' или ''
     */
    getValue() {
      return inputEl.value;
    },

    /**
     * Сфокусировать поле ввода.
     */
    focus() {
      inputEl.focus();
    },

    /**
     * Показать ошибку валидации.
     *
     * @param {string} message
     */
    setError,

    /**
     * Снять ошибку.
     */
    clearError,

    /**
     * Уничтожить экземпляр.
     */
    destroy() {
      inputEl.removeEventListener('input', handleInput);
      inputEl.removeEventListener('keydown', handleKeyDown);
      container.innerHTML = '';
    }
  };
}

// ============================================================
// createDatePicker()
// ============================================================

/**
 * Создаёт композитный виджет: календарь + поле ввода с двунаправленной связью.
 *
 * @param {object} options
 * @param {HTMLElement} options.container — DOM-элемент для рендеринга
 * @param {string} [options.value] — начальная дата в формате 'ДД.ММ.ГГГГ'
 * @param {Function} [options.onChange] — колбэк при изменении даты: onChange(dateString)
 * @param {string} [options.min] — минимальная дата 'YYYY-MM-DD'
 * @param {string} [options.max] — максимальная дата 'YYYY-MM-DD'
 * @returns {object} управляющий объект
 */
export function createDatePicker({ container, value, onChange, min, max }) {
  // Рендерим контейнеры
  container.innerHTML = `
    <div class="date-picker">
      <div class="date-picker__input" id="dp-input-container"></div>
      <div class="date-picker__calendar" id="dp-calendar-container"></div>
    </div>
  `;

  const inputContainer = container.querySelector('#dp-input-container');
  const calendarContainer = container.querySelector('#dp-calendar-container');

  if (!inputContainer || !calendarContainer) {
    return {
      getValue: () => null,
      setValue: () => {},
      focus: () => {},
      destroy: () => {
        container.innerHTML = '';
      }
    };
  }

  // Флаг для предотвращения циклических вызовов
  let updating = false;

  const calendar = createCalendar({
    container: calendarContainer,
    value,
    onChange: (dateStr) => {
      if (updating) return;
      updating = true;
      input.setValue(dateStr);
      updating = false;
      if (onChange) onChange(dateStr);
    },
    min,
    max
  });

  const input = createDateInput({
    container: inputContainer,
    value,
    placeholder: 'ДД.ММ.ГГГГ',
    onChange: (dateStr) => {
      if (updating) return;
      updating = true;
      calendar.setValue(dateStr);
      // Переключить календарь на месяц выбранной даты
      const parsed = parseDate(dateStr);
      if (parsed) {
        calendar.goToMonth(parsed.year, parsed.month);
      }
      updating = false;
      if (onChange) onChange(dateStr);
    }
  });

  return {
    /**
     * Получить текущую дату.
     *
     * @returns {string | null} дата в формате 'ДД.ММ.ГГГГ' или null
     */
    getValue() {
      return input.getValue() || null;
    },

    /**
     * Установить дату.
     *
     * @param {string} dateString — 'ДД.ММ.ГГГГ'
     */
    setValue(dateString) {
      input.setValue(dateString);
      calendar.setValue(dateString);
    },

    /**
     * Сфокусировать поле ввода.
     */
    focus() {
      input.focus();
    },

    /**
     * Уничтожить виджет.
     */
    destroy() {
      calendar.destroy();
      input.destroy();
    }
  };
}
