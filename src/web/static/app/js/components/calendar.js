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
function parseDate(str) {
  if (!str || typeof str !== 'string') return null;
  const parts = str.split('.');
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
  // Первый день месяца (0 = воскресенье, 1 = понедельник, ..., 6 = суббота)
  const firstDay = new Date(year, month - 1, 1);
  // День недели первого дня (пн = 0, ..., вс = 6)
  let startDow = firstDay.getDay() - 1;
  if (startDow < 0) startDow = 6;

  // Начинаем с понедельника предыдущей недели
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

    // Обработчики навигации по годам
    container
      .querySelectorAll('.calendar__month-picker__year-nav')
      .forEach((btn) => {
        btn.addEventListener('click', () => {
          const action = btn.dataset.action;
          pickerYear += action === 'prev' ? -1 : 1;
          render();
        });
      });

    // Обработчики выбора месяца
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

    gridEl.innerHTML = days
      .map((d) => {
        let cls = 'calendar__day';
        if (!d.isCurrentMonth) cls += ' calendar__day--other-month';
        if (d.iso === todayISO) cls += ' calendar__day--today';
        if (d.iso === selectedISO) cls += ' calendar__day--selected';
        if (!isDateInRange(d.iso, min, max)) cls += ' calendar__day--disabled';

        const disabled = !isDateInRange(d.iso, min, max);
        return `<button class="${cls}" type="button" data-iso="${d.iso}"${disabled ? ' disabled' : ''} aria-label="${d.day} ${getMonthName(d.month)} ${d.year}">${d.day}</button>`;
      })
      .join('');

    // Обновляем состояние кнопок навигации
    updateNavButtons();
  }

  /**
   * Проверяет, можно ли перейти к указанному месяцу с учётом [min, max].
   */
  function canNavigateTo(year, month) {
    // Строим ISO первого дня месяца
    const firstDay = `${year}-${String(month).padStart(2, '0')}-01`;
    // Строим ISO последнего дня месяца
    const lastDayDate = new Date(year, month, 0);
    const lastDay = `${year}-${String(month).padStart(2, '0')}-${String(lastDayDate.getDate()).padStart(2, '0')}`;

    // Если есть max — первый день месяца не должен быть позже max
    if (max && firstDay > max) return false;
    // Если есть min — последний день месяца не должен быть раньше min
    if (min && lastDay < min) return false;
    return true;
  }

  /**
   * Обновляет состояние (disabled) кнопок навигации.
   */
  function updateNavButtons() {
    if (prevBtn) {
      prevBtn.disabled = !canNavigateTo(
        viewMonth === 1 ? viewYear - 1 : viewYear,
        viewMonth === 1 ? 12 : viewMonth - 1
      );
    }
    if (nextBtn) {
      nextBtn.disabled = !canNavigateTo(
        viewMonth === 12 ? viewYear + 1 : viewYear,
        viewMonth === 12 ? 1 : viewMonth + 1
      );
    }
  }

  /**
   * Выбирает день и уведомляет через onChange.
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
    const parts = currentISO.split('-');
    const cy = parseInt(parts[0], 10);
    const cm = parseInt(parts[1], 10);
    const cd = parseInt(parts[2], 10);
    const currentDate = new Date(cy, cm - 1, cd);

    switch (e.key) {
      case 'ArrowLeft': {
        const prev = new Date(currentDate);
        prev.setDate(prev.getDate() - 1);
        const py = prev.getFullYear();
        const pm = String(prev.getMonth() + 1).padStart(2, '0');
        const pd = String(prev.getDate()).padStart(2, '0');
        newISO = `${py}-${pm}-${pd}`;
        break;
      }
      case 'ArrowRight': {
        const next = new Date(currentDate);
        next.setDate(next.getDate() + 1);
        const ny = next.getFullYear();
        const nm = String(next.getMonth() + 1).padStart(2, '0');
        const nd = String(next.getDate()).padStart(2, '0');
        newISO = `${ny}-${nm}-${nd}`;
        break;
      }
      case 'ArrowUp': {
        const up = new Date(currentDate);
        up.setDate(up.getDate() - 7);
        const uy = up.getFullYear();
        const um = String(up.getMonth() + 1).padStart(2, '0');
        const ud = String(up.getDate()).padStart(2, '0');
        newISO = `${uy}-${um}-${ud}`;
        break;
      }
      case 'ArrowDown': {
        const down = new Date(currentDate);
        down.setDate(down.getDate() + 7);
        const dy = down.getFullYear();
        const dm = String(down.getMonth() + 1).padStart(2, '0');
        const dd = String(down.getDate()).padStart(2, '0');
        newISO = `${dy}-${dm}-${dd}`;
        break;
      }
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
    if (viewMonth === 1) {
      viewMonth = 12;
      viewYear--;
    } else {
      viewMonth--;
    }
    renderGrid();
  });

  nextBtn.addEventListener('click', () => {
    if (viewMonth === 12) {
      viewMonth = 1;
      viewYear++;
    } else {
      viewMonth++;
    }
    renderGrid();
  });

  // Клик по метке месяца — открыть попап выбора месяца/года
  monthLabel.addEventListener('click', () => {
    const pickerEl = container.querySelector('.calendar__month-picker');
    if (!pickerEl) return;

    // Если попап уже открыт — закрыть
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
   * Валидирует строку даты 'ДД.ММ.ГГГГ'.
   *
   * @param {string} str
   * @returns {{ valid: boolean, message: string }}
   */
  function validateDate(str) {
    if (!str || str.length < 10) {
      return { valid: false, message: '' };
    }

    const parsed = parseDate(str);
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

    // Проверка реальности даты
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

  /**
   * Применяет маску к значению поля.
   * Обеспечивает формат ДД.ММ.ГГГГ.
   */
  function applyMask() {
    let val = inputEl.value.replace(/[^\d]/g, ''); // Только цифры

    // Ограничиваем длину до построения результата (максимум 8 цифр)
    if (val.length > 8) {
      val = val.substring(0, 8);
    }

    let result = '';

    if (val.length > 0) {
      result += val.substring(0, 2);
    }
    if (val.length >= 2) {
      result += '.';
    }
    if (val.length > 2) {
      result += val.substring(2, 4);
    }
    if (val.length >= 5) {
      result += '.';
    }
    if (val.length > 4) {
      result += val.substring(4, 8);
    }

    return result;
  }

  /**
   * Обработчик события input.
   */
  function handleInput() {
    const cursorPos = inputEl.selectionStart;
    const oldLength = inputEl.value.length;

    const masked = applyMask();
    inputEl.value = masked;

    // Коррекция позиции курсора
    const newLength = masked.length;
    let newCursorPos = cursorPos;

    // Если добавилась точка — сдвигаем курсор
    if (newLength > oldLength && masked.charAt(cursorPos - 1) === '.') {
      newCursorPos += 1;
    }

    // Ограничиваем курсор
    newCursorPos = Math.min(newCursorPos, masked.length);
    inputEl.setSelectionRange(newCursorPos, newCursorPos);

    // Валидация при полном вводе
    clearError();

    if (masked.length === 10) {
      const validation = validateDate(masked);
      if (!validation.valid) {
        setError(validation.message);
      } else if (onChange) {
        onChange(masked);
      }
    }
  }

  /**
   * Обработчик keydown для Backspace/Delete.
   */
  function handleKeyDown(e) {
    if (e.key === 'Backspace' || e.key === 'Delete') {
      // При удалении точки — удаляем и предыдущую цифру
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
