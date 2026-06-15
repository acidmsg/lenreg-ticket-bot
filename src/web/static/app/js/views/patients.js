/**
 * Экран управления пациентами.
 * Просмотр списка пациентов, добавление (отдельный экран) и удаление.
 *
 * @module views/patients
 */

import { apiGet, apiPost, apiDelete } from '../api.js';
import { isInTelegram } from '../auth.js';
import { lucideIcon } from '../components/icon.js';
import { escapeHtml } from '../utils/escape.js';
import { renderError } from '../utils/error.js';
import { showConfirm } from '../utils/ui.js';
import { navigate } from '../app.js';

// ============================================================
// Валидация
// ============================================================

/**
 * Валидирует ФИО: три слова, только кириллица, дефисы и пробелы.
 *
 * @param {string} value — введённое значение
 * @returns {{ valid: boolean, error: string|null }}
 */
function validatePatientName(value) {
  const trimmed = (value || '').trim();
  if (!trimmed) {
    return { valid: false, error: 'Введите фамилию, имя и отчество' };
  }
  if (!/^[а-яёА-ЯЁ\s-]+$/.test(trimmed)) {
    return {
      valid: false,
      error: 'Допустима только кириллица, пробелы и дефис'
    };
  }
  const parts = trimmed.split(/\s+/).filter(Boolean);
  if (parts.length !== 3) {
    return {
      valid: false,
      error: 'ФИО должно состоять из трёх слов: Фамилия Имя Отчество'
    };
  }
  return { valid: true, error: null };
}

/**
 * Валидирует дату рождения: формат ДД.ММ.ГГГГ.
 *
 * @param {string} value — введённое значение
 * @returns {{ valid: boolean, error: string|null }}
 */
function validateBday(value) {
  const trimmed = (value || '').trim();
  if (!trimmed) {
    return { valid: false, error: 'Введите дату рождения' };
  }
  if (!/^\d{2}\.\d{2}\.\d{4}$/.test(trimmed)) {
    return {
      valid: false,
      error: 'Дата рождения должна быть в формате ДД.ММ.ГГГГ'
    };
  }

  const [d, m, y] = trimmed.split('.').map(Number);

  // Проверка месяца
  if (m < 1 || m > 12) {
    return { valid: false, error: 'Некорректный месяц (01–12)' };
  }

  // Проверка дня с учётом реального календаря (високосные годы, разная длина месяцев)
  const daysInMonth = new Date(y, m, 0).getDate();
  if (d < 1 || d > daysInMonth) {
    return {
      valid: false,
      error: `Некорректный день для выбранного месяца (1–${daysInMonth})`
    };
  }

  // Проверка, что дата не в будущем
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const inputDate = new Date(y, m - 1, d);
  if (inputDate > today) {
    return { valid: false, error: 'Дата рождения не может быть в будущем' };
  }

  return { valid: true, error: null };
}

/**
 * Отображает ошибку валидации у конкретного поля.
 *
 * @param {HTMLElement|null} inputEl — поле ввода
 * @param {HTMLElement|null} errorEl — элемент для текста ошибки
 * @param {string|null} message — сообщение (null = нет ошибки)
 */
function setFieldError(inputEl, errorEl, message) {
  if (!inputEl || !errorEl) return;
  if (message) {
    inputEl.classList.add('form__input--invalid');
    errorEl.textContent = message;
  } else {
    inputEl.classList.remove('form__input--invalid');
    errorEl.textContent = '';
  }
}

// ============================================================
// Сборка формы
// ============================================================

/**
 * Формирует HTML-разметку формы добавления пациента.
 *
 * @returns {string} HTML-разметка
 */
function buildPatientFormHTML() {
  return `
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
          <span class="form__error" id="patient-fio-error"></span>
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
          <span class="form__error" id="patient-bday-error"></span>
        </div>
        <div class="mb-md">
          <label class="form__label" for="patient-alias">Псевдоним (необязательно)</label>
          <input
            type="text"
            id="patient-alias"
            class="form__input"
            placeholder="Например: мама, ребёнок"
            autocomplete="off"
          >
        </div>
      </form>
      <div id="patient-form-error" class="hidden mt-md" style="color: var(--color-danger); font-size: var(--font-sm);"></div>
      <div class="fab-group">
        <button class="btn btn--secondary btn--sm" id="patient-add-back">← Назад</button>
        <button class="fab" id="patient-add-submit"><span class="lucide-icon">${lucideIcon('circle-plus', 16)}</span> Добавить</button>
      </div>
    </div>
  `;
}

// ============================================================
// Календарь и маска даты
// ============================================================

/**
 * Инициализирует VanillaCalendar на поле ввода даты.
 *
 * @param {HTMLInputElement} dateInput — поле ввода даты
 * @returns {VanillaCalendar} экземпляр календаря
 */
function initPatientCalendar(dateInput) {
  // Сегодняшняя дата в YYYY-MM-DD — верхняя граница (нельзя родиться в будущем)
  const today = new Date();
  const todayStr = today.toISOString().split('T')[0];

  const calendar = new VanillaCalendar(dateInput, {
    input: true,
    settings: {
      lang: 'ru',
      selection: {
        day: 'single'
      },
      visibility: {
        theme: 'dark'
      },
      range: {
        min: '1900-01-01',
        max: todayStr,
        disablePast: false
      }
    },
    actions: {
      clickDay(event, self) {
        // Блокируем выбор дат, отключённых библиотекой (за пределами range).
        // Библиотека v2.9.10 не проверяет dayBtnDisabled в обработчике клика —
        // только добавляет CSS-класс. Сбрасываем selectedDates до changeToInput.
        const target = event.target;
        if (target.classList.contains(self.CSSClasses.dayBtnDisabled)) {
          self.selectedDates = [];
        }
      },
      changeToInput(event, self) {
        const date = self.selectedDates[0];
        if (!date) return;
        const [y, m, d] = date.split('-');
        self.HTMLInputElement.value = `${d}.${m}.${y}`;
        // Флаг предотвращает обратную синхронизацию (маска → календарь)
        // при программной установке значения из календаря
        self.HTMLInputElement._fromCalendar = true;
        self.hide();
      }
    }
  });
  calendar.init();
  return calendar;
}

/**
 * Навешивает умную маску ввода даты с посегментной валидацией цифр
 * и прогрессивной синхронизацией календаря.
 *
 * Блокирует недопустимые символы на уровне ввода:
 *   день: первая цифра 0-3, если 3 — вторая 0-1 (макс 31)
 *   месяц: первая цифра 0-1, если 1 — вторая 0-2 (макс 12)
 *   год: 1xxx или 20xx (год ≥ 1900, итоговая проверка ≤ текущий — в validateBday)
 *
 * @param {HTMLInputElement} inputEl — поле ввода даты
 * @param {VanillaCalendar} calendar — экземпляр календаря
 * @param {HTMLElement} bdayError — элемент для ошибки валидации даты
 */
function setupDateMask(inputEl, calendar, bdayError) {
  inputEl.addEventListener('input', () => {
    const raw = inputEl.value.replace(/\D/g, '');
    let digits = '';

    for (let i = 0; i < Math.min(raw.length, 8); i++) {
      const ch = raw[i];
      const d = parseInt(ch, 10);

      if (i === 0) {
        // Первая цифра дня: только 0-3
        if (d < 0 || d > 3) break;
      } else if (i === 1) {
        // Вторая цифра дня: если первая = 3 → только 0-1; иначе 0-9
        const d1 = parseInt(digits[0], 10);
        if (d1 === 3 && d > 1) break;
      } else if (i === 2) {
        // Первая цифра месяца: только 0-1
        if (d < 0 || d > 1) break;
      } else if (i === 3) {
        // Вторая цифра месяца: если первая = 1 → только 0-2; иначе 0-9
        const m1 = parseInt(digits[2], 10);
        if (m1 === 1 && d > 2) break;
      } else if (i === 4) {
        // Первая цифра года: только 1 или 2 (год ≥ 1900)
        if (d < 1 || d > 2) break;
      } else if (i === 5) {
        // Вторая цифра года: если первая=1 → только 9 (19xx); если первая=2 → только 0 (20xx)
        const y1 = parseInt(digits[4], 10);
        if (y1 === 1 && d !== 9) break;
        if (y1 === 2 && d !== 0) break;
      }
      // Для третьей и четвёртой цифры года — любые цифры, ограничение в validateBday

      digits += ch;
    }

    let formatted = '';
    if (digits.length > 0) formatted += digits.slice(0, 2);
    if (digits.length > 2) formatted += '.' + digits.slice(2, 4);
    if (digits.length > 4) formatted += '.' + digits.slice(4, 8);

    if (inputEl.value !== formatted) {
      inputEl.value = formatted;
    }

    // Прогрессивная синхронизация календаря при ручном вводе даты.
    // Программная установка inputEl.value не вызывает input-событие,
    // поэтому валидационный обработчик может не увидеть финальное значение.
    const inputLen = inputEl.value.trim().length;

    if (inputLen === 10) {
      // Полная дата (ДД.ММ.ГГГГ) — валидация + полная синхронизация календаря.
      const result = validateBday(inputEl.value);
      setFieldError(inputEl, bdayError, result.error);

      // Синхронизация календаря с ручным вводом:
      // если дата валидна и ввод не из календаря — переключаем календарь
      // на соответствующий месяц/год и подсвечиваем выбранную дату.
      if (result.valid && !inputEl._fromCalendar) {
        const [d, m, y] = inputEl.value.split('.').map(Number);
        // Параметры update() в VanillaCalendar Pro v2.9.10 — булевы флаги
        // (true = «использовать сохранённое значение из settings.selected»),
        // а не новые значения года/месяца. Передача числовых значений (year: 2025,
        // month: 6) интерпретируется как truthy → месяц/год не меняются.
        //
        // Для переключения месяца/года нужно установить selectedYear/selectedMonth
        // (0-based, как Date.getMonth()) до вызова update() без аргументов.
        // Тогда be() возьмёт значения из selectedYear/selectedMonth/selectedDates.
        const dateStr = `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
        calendar.selectedDates = [dateStr];
        calendar.selectedYear = y;
        calendar.selectedMonth = m - 1; // 0-based: январь=0, ..., декабрь=11
        calendar.update();
      }
      // Сбрасываем флаг после обработки
      if (inputEl._fromCalendar) {
        delete inputEl._fromCalendar;
      }
    } else if (digits.length === 4 && !inputEl._fromCalendar) {
      // Введён день и месяц (4 сырые цифры = ДД.ММ, 5 символов с точкой).
      // Год ещё не введён — авто-подставляем текущий или прошлый.
      // Если ДД.ММ.текущийГод > сегодня → используем прошлый год.
      // День подсвечиваем синтетической ISO-датой с вычисленным годом.
      const [dd, mm] = inputEl.value.split('.').map(Number);
      if (mm >= 1 && mm <= 12) {
        const today = new Date();
        let year = today.getFullYear();
        const candidate = new Date(year, mm - 1, dd);
        if (candidate > today) {
          year--; // дата в будущем относительно сегодня → прошлый год
        }
        // Подсвечиваем день в календаре при частичном вводе (ДД.ММ без года).
        // Синтетическая ISO-дата с вычисленным годом для визуальной подсветки.
        const partialISO = `${year}-${String(mm).padStart(2, '0')}-${String(dd).padStart(2, '0')}`;
        calendar.selectedDates = [partialISO];
        calendar.selectedYear = year;
        calendar.selectedMonth = mm - 1; // 0-based
        calendar.update();
      }
    } else if (digits.length === 2 && !inputEl._fromCalendar) {
      // Введён только день (2 сырые цифры = ДД).
      // Если день ДД текущего месяца ещё не наступил → переключаем на предыдущий месяц.
      // День подсвечиваем синтетической ISO-датой с вычисленным месяцем/годом.
      const dd = Number(digits);
      const today = new Date();
      let month = today.getMonth(); // 0-based
      let year = today.getFullYear();
      if (dd > today.getDate()) {
        month--;
        if (month < 0) {
          month = 11;
          year--;
        }
      }
      // Подсвечиваем день в календаре при частичном вводе (только ДД).
      // Синтетическая ISO-дата с вычисленным месяцем/годом для визуальной подсветки.
      const displayMonth = month + 1; // 1-based для ISO-строки
      const partialISO = `${year}-${String(displayMonth).padStart(2, '0')}-${String(dd).padStart(2, '0')}`;
      calendar.selectedDates = [partialISO];
      calendar.selectedYear = year;
      calendar.selectedMonth = month;
      calendar.update();
    } else if (
      inputLen < 10 &&
      inputEl.classList.contains('form__input--invalid')
    ) {
      // Сбрасываем ошибку при стирании символов
      setFieldError(inputEl, bdayError, null);
    }
  });
}

// ============================================================
// Отправка формы
// ============================================================

/**
 * Навешивает обработчик отправки формы добавления пациента.
 *
 * @param {HTMLFormElement} form — элемент формы
 * @param {Function} onSuccess — колбэк при успешном добавлении
 */
function setupPatientFormSubmit(form, onSuccess) {
  const container = form.closest('.patient-add-form');
  if (!container) return;

  const fioInput = container.querySelector('#patient-fio');
  const bdayInput = container.querySelector('#patient-bday');
  const aliasInput = container.querySelector('#patient-alias');
  const fioError = container.querySelector('#patient-fio-error');
  const bdayError = container.querySelector('#patient-bday-error');
  const errorEl = container.querySelector('#patient-form-error');
  const submitBtn = container.querySelector('#patient-add-submit');

  if (!submitBtn) return;

  submitBtn.addEventListener('click', async () => {
    const full_name = fioInput?.value?.trim() || '';
    const birth_date = bdayInput?.value?.trim() || '';
    const alias = aliasInput?.value?.trim() || '';

    // Валидация с подсветкой полей
    const fioResult = validatePatientName(full_name);
    setFieldError(fioInput, fioError, fioResult.error);

    const bdayResult = validateBday(birth_date);
    setFieldError(bdayInput, bdayError, bdayResult.error);

    if (!fioResult.valid || !bdayResult.valid) {
      return;
    }

    hideFormError(errorEl);

    try {
      const body = { full_name, birth_date };
      if (alias) body.alias = alias;
      await apiPost('/patients/add', body);

      // Тактильный отклик (если доступен)
      if (isInTelegram() && window.Telegram.WebApp?.HapticFeedback) {
        window.Telegram.WebApp.HapticFeedback.notificationOccurred('success');
      }

      onSuccess();
    } catch (error) {
      showFormError(errorEl, error.message);
    }
  });
}

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
    renderError(container, error.message, 'Повторить', () =>
      renderPatients(container)
    );
  }
}

/**
 * Рендерит форму добавления пациента на отдельном экране.
 *
 * @param {HTMLElement} container — DOM-элемент для рендеринга
 */
export async function renderPatientAddForm(container) {
  if (!container) return;

  container.innerHTML = buildPatientFormHTML();

  const dateInput = container.querySelector('#patient-bday');
  const fioInput = container.querySelector('#patient-fio');
  const fioError = container.querySelector('#patient-fio-error');
  const bdayError = container.querySelector('#patient-bday-error');

  // Инициализация календаря и маски даты
  if (dateInput) {
    const calendar = initPatientCalendar(dateInput);
    setupDateMask(dateInput, calendar, bdayError);
  }

  // Валидация ФИО в реальном времени
  if (fioInput) {
    fioInput.addEventListener('blur', () => {
      const result = validatePatientName(fioInput.value);
      setFieldError(fioInput, fioError, result.error);
    });
    fioInput.addEventListener('input', () => {
      if (fioInput.classList.contains('form__input--invalid')) {
        const result = validatePatientName(fioInput.value);
        if (result.valid) {
          setFieldError(fioInput, fioError, null);
        }
      }
    });
  }

  // Валидация даты рождения в реальном времени (blur + input)
  if (dateInput) {
    dateInput.addEventListener('blur', () => {
      const result = validateBday(dateInput.value);
      setFieldError(dateInput, bdayError, result.error);
    });
    dateInput.addEventListener('input', () => {
      const len = dateInput.value.trim().length;
      if (len === 10) {
        const result = validateBday(dateInput.value);
        setFieldError(dateInput, bdayError, result.error);
      } else if (
        len < 10 &&
        dateInput.classList.contains('form__input--invalid')
      ) {
        setFieldError(dateInput, bdayError, null);
      }
    });
  }

  // Кнопка «Назад»
  const backBtn = container.querySelector('#patient-add-back');
  if (backBtn) {
    backBtn.addEventListener('click', () => {
      navigate('patients');
    });
  }

  // Отправка формы
  const form = container.querySelector('#patient-form');
  if (form) {
    setupPatientFormSubmit(form, () => {
      navigate('patients');
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

  // Сортировка пациентов в алфавитном порядке по ФИО (кириллица).
  // localeCompare('ru') обеспечивает корректную сортировку букв «ё», «Ё» и т.д.
  patients.sort((a, b) => (a.fio || '').localeCompare(b.fio || '', 'ru'));

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
