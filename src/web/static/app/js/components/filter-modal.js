/**
 * Модальная форма настройки фильтра отслеживания врача (§9.5).
 *
 * Точка входа — иконка 🔎 в строке каждого пациента карточки врача.
 * Модалка предзаполняется текущим фильтром (обязательно: `PUT /filter`
 * перезаписывает все пять полей) и всегда отправляет полный набор значений.
 *
 * Строки интерфейса заданы по-русски прямо в модуле — сложившаяся практика
 * Mini App (прецедент `slots-booking-hint`); каталоги `.po` содержат ссылку
 * на этот файл для контроля паритета ключей (§9.7).
 *
 * @module components/filter-modal
 */

import { apiPut } from "../api.js";
import { escapeHtml } from "../utils/escape.js";
import { lucideIcon } from "./icon.js";

/** Максимальное число конкретных дат (§9.5.4). */
const MAX_SPECIFIC_DATES = 10;

/** Формат даты ГГГГ-ММ-ДД (§9.5.4). */
const ISO_DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

/** Разделитель токенов конкретных дат: запятая или пробел (§9.5.4). */
const SPECIFIC_DATES_DIVIDER = /[\s,]+/;

/** Префикс пути эндпоинта сохранения фильтра (§9.5.5). */
const FILTER_PATH_PREFIX = "/monitoring/";

/** Идентификатор оверлея модалки в DOM. */
const OVERLAY_ID = "filter-modal-overlay";

/** Имена полей формы — совпадают с ключами `MonitoringFilterRequest`. */
const FIELD_NAMES = [
  "date_from",
  "date_to",
  "time_from",
  "time_to",
  "specific_dates",
];

/**
 * Тексты интерфейса — зеркало ключей `filter-*` каталогов локализации (§9.7).
 */
const TEXT = {
  title: "Фильтр отслеживания",
  dateFrom: "Дата с",
  dateTo: "Дата по",
  timeFrom: "Время с",
  timeTo: "Время по",
  specificDates: "Конкретные даты",
  specificDatesHint: "Через запятую, формат ГГГГ-ММ-ДД, не более 10",
  emptyHint:
    "Оставьте поля пустыми, чтобы получать уведомления обо всех талонах.",
  close: "Отмена",
  save: "Сохранить",
  reset: "Сбросить фильтр",
  saved: "✅ Фильтр обновлён",
  saveError: "❌ Не удалось сохранить фильтр: {reason}",
  errorDateRange: "❌ Дата окончания раньше даты начала.",
  errorTimeRange: "❌ Конец интервала времени раньше начала.",
  errorSpecificDates:
    "❌ Не удалось разобрать даты. Перечислите их через запятую в формате " +
    "ГГГГ-ММ-ДД (не более 10).",
};

/** Обработчик Esc активной модалки (снимается при закрытии). */
let escapeHandler = null;

/**
 * Проверяет, задан ли хотя бы один параметр фильтра (§9.5.1).
 *
 * @param {object|null} filter — фильтр из ответа `GET /doctors`
 * @returns {boolean} `true`, если хотя бы одно ограничение задано
 */
export function hasActiveFilter(filter) {
  if (!filter) return false;
  return Boolean(
    filter.date_from ||
    filter.date_to ||
    filter.time_from ||
    filter.time_to ||
    (Array.isArray(filter.specific_dates) && filter.specific_dates.length > 0),
  );
}

/**
 * Форматирует дату `ГГГГ-ММ-ДД` в `ДД.ММ.ГГГГ` для краткого бейджа.
 *
 * @param {string} value — дата в формате ГГГГ-ММ-ДД
 * @returns {string} дата в формате ДД.ММ.ГГГГ
 */
export function formatIsoDate(value) {
  const parts = String(value).split("-");
  if (parts.length !== 3) return String(value);
  const [year, month, day] = parts;
  return `${day}.${month}.${year}`;
}

/**
 * Возвращает форму множественного числа для слова «дата».
 *
 * @param {number} count — количество дат
 * @returns {string} «дата» | «даты» | «дат»
 */
function pluralizeDates(count) {
  const mod100 = count % 100;
  const mod10 = count % 10;
  if (mod10 === 1 && mod100 !== 11) return "дата";
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return "даты";
  return "дат";
}

/**
 * Собирает части бейджа текущего фильтра (§9.5.1).
 *
 * @param {object|null} filter — фильтр из ответа `GET /doctors`
 * @returns {Array<string>} части бейджа (пустой массив — фильтр не задан)
 */
function formatFilterSummary(filter) {
  if (!hasActiveFilter(filter) || !filter) return [];

  const parts = [];

  const dateFrom = filter.date_from || "";
  const dateTo = filter.date_to || "";
  if (dateFrom && dateTo) {
    parts.push(`📅 ${formatIsoDate(dateFrom)}–${formatIsoDate(dateTo)}`);
  } else if (dateFrom) {
    parts.push(`📅 с ${formatIsoDate(dateFrom)}`);
  } else if (dateTo) {
    parts.push(`📅 по ${formatIsoDate(dateTo)}`);
  }

  const timeFrom = filter.time_from || "";
  const timeTo = filter.time_to || "";
  if (timeFrom && timeTo) {
    parts.push(`🕒 ${timeFrom}–${timeTo}`);
  } else if (timeFrom) {
    parts.push(`🕒 с ${timeFrom}`);
  } else if (timeTo) {
    parts.push(`🕒 по ${timeTo}`);
  }

  const specificDates = Array.isArray(filter.specific_dates)
    ? filter.specific_dates
    : [];
  if (specificDates.length > 0) {
    parts.push(
      `📌 ${specificDates.length} ${pluralizeDates(specificDates.length)}`,
    );
  }

  return parts;
}

/**
 * Рендерит бейдж текущего фильтра для строки пациента.
 *
 * При пустом фильтре возвращает пустую строку (§9.5.1).
 *
 * @param {object|null} filter — фильтр из ответа `GET /doctors`
 * @returns {string} HTML-строка бейджа или `""`
 */
export function renderFilterBadge(filter) {
  const parts = formatFilterSummary(filter);
  if (parts.length === 0) return "";

  const items = parts
    .map(
      (part) => `<span class="filter-summary__item">${escapeHtml(part)}</span>`,
    )
    .join("");

  return `<span class="filter-summary">${items}</span>`;
}

/**
 * Рендерит подзаголовок модалки: врач и пациент (§9.5.2).
 *
 * @param {string} doctorName — ФИО врача
 * @param {string} patientName — имя пациента
 * @returns {string} HTML-строка подзаголовка или `""`
 */
function renderSubtitle(doctorName, patientName) {
  const parts = [];
  if (doctorName) parts.push(`👨‍⚕️ ${escapeHtml(doctorName)}`);
  if (patientName) parts.push(`👤 ${escapeHtml(patientName)}`);
  if (parts.length === 0) return "";
  return `<div class="app-modal__subtitle">${parts.join(" · ")}</div>`;
}

/**
 * Рендерит строку формы: подпись слева, поле справа, ошибка снизу.
 *
 * @param {object} options — параметры поля
 * @param {string} options.name — имя поля (ключ `MonitoringFilterRequest`)
 * @param {string} options.label — подпись поля
 * @param {string} options.type — тип `<input>`
 * @param {string} options.value — предзаполненное значение
 * @returns {string} HTML-строка поля
 */
function renderInlineField({ name, label, type, value }) {
  return `
    <div class="form-field">
      <div class="form-field__row">
        <label class="form-field__label" for="filter-${name}">${escapeHtml(label)}</label>
        <input
          class="form-field__input"
          type="${type}"
          id="filter-${name}"
          name="${name}"
          value="${escapeHtml(value)}"
        />
      </div>
      <div class="form-field__error hidden" data-error-for="${name}"></div>
    </div>
  `;
}

/**
 * Рендерит поле «Конкретные даты» с подсказкой и областью ошибки.
 *
 * @param {Array<string>} specificDates — текущий список дат
 * @returns {string} HTML-строка поля
 */
function renderSpecificDatesField(specificDates) {
  return `
    <div class="form-field">
      <label class="form-field__label" for="filter-specific_dates">${escapeHtml(TEXT.specificDates)}</label>
      <input
        class="form-field__input"
        type="text"
        id="filter-specific_dates"
        name="specific_dates"
        value="${escapeHtml(specificDates.join(", "))}"
        placeholder="2026-07-01, 2026-07-15"
        autocomplete="off"
      />
      <div class="form-field__hint">${escapeHtml(TEXT.specificDatesHint)}</div>
      <div class="form-field__error hidden" data-error-for="specific_dates"></div>
    </div>
  `;
}

/**
 * Рендерит разметку модальной формы целиком (§9.5.2).
 *
 * @param {object} options — параметры разметки
 * @param {string} options.doctorName — ФИО врача
 * @param {string} options.patientName — имя пациента
 * @param {object|null} options.filter — текущий фильтр (предзаполнение)
 * @returns {string} HTML-строка модалки
 */
function renderModalMarkup({ doctorName, patientName, filter }) {
  const current = filter || {};
  const specificDates = Array.isArray(current.specific_dates)
    ? current.specific_dates
    : [];

  return `
    <div class="app-modal" role="dialog" aria-modal="true" aria-labelledby="filter-modal-title">
      <div class="app-modal__header">
        <h2 class="app-modal__title" id="filter-modal-title">${escapeHtml(TEXT.title)}</h2>
        <button
          type="button"
          class="app-modal__close"
          data-filter-close
          title="${escapeHtml(TEXT.close)}"
          aria-label="${escapeHtml(TEXT.close)}"
        >${lucideIcon("x", 18)}</button>
      </div>
      <div class="app-modal__body">
        ${renderSubtitle(doctorName, patientName)}
        ${renderInlineField({ name: "date_from", label: TEXT.dateFrom, type: "date", value: current.date_from || "" })}
        ${renderInlineField({ name: "date_to", label: TEXT.dateTo, type: "date", value: current.date_to || "" })}
        ${renderInlineField({ name: "time_from", label: TEXT.timeFrom, type: "time", value: current.time_from || "" })}
        ${renderInlineField({ name: "time_to", label: TEXT.timeTo, type: "time", value: current.time_to || "" })}
        ${renderSpecificDatesField(specificDates)}
        <p class="app-modal__hint">${escapeHtml(TEXT.emptyHint)}</p>
        <div class="app-modal__form-error hidden" data-form-error role="alert"></div>
      </div>
      <div class="app-modal__footer">
        <button type="button" class="btn btn--secondary" data-filter-reset>${escapeHtml(TEXT.reset)}</button>
        <button type="button" class="btn btn--primary" data-filter-save>${escapeHtml(TEXT.save)}</button>
      </div>
    </div>
  `;
}

/**
 * Собирает ссылки на поля формы и служебные элементы модалки.
 *
 * @param {HTMLElement} modal — корневой элемент `.app-modal`
 * @returns {object} элементы формы
 */
function collectFormElements(modal) {
  const inputs = {};
  const errors = {};
  for (const name of FIELD_NAMES) {
    inputs[name] = modal.querySelector(`[name="${name}"]`);
    errors[name] = modal.querySelector(`[data-error-for="${name}"]`);
  }

  return {
    inputs,
    errors,
    saveButton: modal.querySelector("[data-filter-save]"),
    resetButton: modal.querySelector("[data-filter-reset]"),
    formError: modal.querySelector("[data-form-error]"),
  };
}

/**
 * Читает текущие значения всех пяти полей формы.
 *
 * @param {object} elements — элементы формы
 * @returns {object} значения полей
 */
function readFields(elements) {
  const fields = {};
  for (const name of FIELD_NAMES) {
    fields[name] = elements.inputs[name].value;
  }
  return fields;
}

/**
 * Проверяет дату на существование в календаре (зеркало `date.fromisoformat`).
 *
 * @param {string} value — дата в формате ГГГГ-ММ-ДД
 * @returns {boolean} `true`, если дата корректна
 */
export function isRealIsoDate(value) {
  if (!ISO_DATE_PATTERN.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) return false;
  return parsed.toISOString().slice(0, 10) === value;
}

/**
 * Разбирает строку конкретных дат: разделитель «запятая или пробел» (§9.5.4).
 *
 * Дубликаты удаляются, порядок сохраняется, лимит — 10 дат.
 *
 * @param {string} raw — необработанное значение поля
 * @returns {{valid: boolean, dates: Array<string>}} результат разбора
 */
export function parseSpecificDates(raw) {
  const tokens = String(raw || "")
    .split(SPECIFIC_DATES_DIVIDER)
    .filter(Boolean);

  if (tokens.length === 0) return { valid: true, dates: [] };
  if (tokens.length > MAX_SPECIFIC_DATES) return { valid: false, dates: [] };

  const dates = [];
  for (const token of tokens) {
    if (!isRealIsoDate(token)) return { valid: false, dates: [] };
    if (!dates.includes(token)) dates.push(token);
  }
  return { valid: true, dates };
}

/**
 * Проверяет форму по матрице §9.5.4/§9.6.
 *
 * @param {object} fields — значения полей формы
 * @returns {{errors: object, specificDates: Array<string>}} ошибки и разобранные даты
 */
export function validateFilter(fields) {
  const errors = {};

  if (fields.date_from && fields.date_to && fields.date_to < fields.date_from) {
    errors.date_to = TEXT.errorDateRange;
  }
  if (fields.time_from && fields.time_to && fields.time_to < fields.time_from) {
    errors.time_to = TEXT.errorTimeRange;
  }

  const parsed = parseSpecificDates(fields.specific_dates);
  if (!parsed.valid) {
    errors.specific_dates = TEXT.errorSpecificDates;
  }

  return { errors, specificDates: parsed.dates };
}

/**
 * Собирает тело запроса `PUT /filter` — всегда ровно пять полей (§9.1, §9.11).
 *
 * PUT перезаписывает фильтр целиком, поэтому отправляется полный набор:
 * четыре строковых поля обрезаются от пробелов, `specific_dates` — массив дат.
 * Вынесено из [`submitFilter()`](filter-modal.js:577) — единый источник тела запроса.
 *
 * @param {object} fields — значения полей формы
 * @param {Array<string>} specificDates — разобранные конкретные даты
 * @returns {object} тело запроса из пяти полей
 */
export function buildFilterPayload(fields, specificDates) {
  return {
    date_from: fields.date_from.trim(),
    date_to: fields.date_to.trim(),
    time_from: fields.time_from.trim(),
    time_to: fields.time_to.trim(),
    specific_dates: specificDates,
  };
}

/**
 * Снимает подсветку и тексты всех ошибок формы.
 *
 * @param {object} elements — элементы формы
 */
function clearErrors(elements) {
  for (const name of FIELD_NAMES) {
    const errorBox = elements.errors[name];
    const input = elements.inputs[name];
    if (errorBox) {
      errorBox.textContent = "";
      errorBox.classList.add("hidden");
    }
    if (input) {
      input.classList.remove("form-field__input--invalid");
    }
  }
  if (elements.formError) {
    elements.formError.textContent = "";
    elements.formError.classList.add("hidden");
  }
}

/**
 * Показывает ошибку под конкретным полем.
 *
 * @param {object} elements — элементы формы
 * @param {string} name — имя поля
 * @param {string} message — текст ошибки
 */
function showFieldError(elements, name, message) {
  const errorBox = elements.errors[name];
  const input = elements.inputs[name];
  if (errorBox) {
    errorBox.textContent = message;
    errorBox.classList.remove("hidden");
  }
  if (input) {
    input.classList.add("form-field__input--invalid");
  }
}

/**
 * Показывает ошибку уровня формы (когда поле не определено).
 *
 * @param {object} elements — элементы формы
 * @param {string} message — текст ошибки
 */
function showFormError(elements, message) {
  if (!elements.formError) return;
  elements.formError.textContent = message;
  elements.formError.classList.remove("hidden");
}

/**
 * Показывает ошибки валидации формы.
 *
 * @param {object} elements — элементы формы
 * @param {object} errors — карта «имя поля → текст ошибки»
 */
function showErrors(elements, errors) {
  for (const [name, message] of Object.entries(errors)) {
    showFieldError(elements, name, message);
  }
}

/**
 * Переключает состояние кнопки сохранения на время запроса.
 *
 * @param {object} elements — элементы формы
 * @param {boolean} isSaving — идёт ли сохранение
 */
function setSaving(elements, isSaving) {
  if (elements.saveButton) {
    elements.saveButton.disabled = isSaving;
  }
}

/**
 * Очищает поля формы («Сбросить фильтр»).
 *
 * Сброс локальный: сохранение выполняется только после нажатия «Сохранить»,
 * поэтому фильтр в БД не меняется (§9.5.2).
 *
 * @param {object} elements — элементы формы
 */
function resetForm(elements) {
  clearErrors(elements);
  for (const name of FIELD_NAMES) {
    elements.inputs[name].value = "";
  }
}

/**
 * Показывает toast через существующий компонент [`toast.js`](toast.js:1).
 *
 * @param {string} message — текст уведомления
 */
function notify(message) {
  if (typeof window.showToast === "function") {
    window.showToast(message);
  }
}

/**
 * Определяет поле, к которому относится сообщение об ошибке `400`.
 *
 * Сначала сообщение сопоставляется по значению из кавычек (формат FastAPI:
 * «Неверный формат даты: 'XXXX'»), затем — по имени поля или ключевому слову.
 *
 * @param {string} detail — сообщение из поля `detail`
 * @param {object} elements — элементы формы
 * @returns {string|null} имя поля или `null` для ошибки уровня формы
 */
function resolveErrorField(detail, elements) {
  const quoted = detail.match(/'([^']*)'/);
  if (quoted) {
    const value = quoted[1];
    for (const name of FIELD_NAMES) {
      if (elements.inputs[name].value.trim() === value) return name;
    }
  }

  const lowered = detail.toLowerCase();
  if (lowered.includes("date_from")) return "date_from";
  if (lowered.includes("date_to")) return "date_to";
  if (lowered.includes("time_from")) return "time_from";
  if (lowered.includes("time_to")) return "time_to";
  if (lowered.includes("specific")) return "specific_dates";
  return null;
}

/**
 * Обрабатывает ошибку сохранения фильтра по матрице ответов §9.5.5.
 *
 * @param {Error} error — ошибка из [`apiPut()`](api.js:130) (поле `status` — код ответа)
 * @param {object} elements — элементы формы
 * @param {Function} [onChanged] — перерендер списка карточек
 */
function handleSaveError(error, elements, onChanged) {
  const reason = error.message || "неизвестная ошибка";
  const status = error.status;

  // 400 — невалидный фильтр: показываем detail под соответствующим полем,
  // модалку не закрываем.
  if (status === 400) {
    const fieldName = resolveErrorField(reason, elements);
    if (fieldName) showFieldError(elements, fieldName, reason);
    else showFormError(elements, reason);
    return;
  }

  const message = TEXT.saveError.replace("{reason}", reason);

  // 403 — сессия истекла: toast + закрыть модалку.
  if (status === 403) {
    closeFilterModal();
    notify(message);
    return;
  }

  // 404 — запись исчезла из мониторинга: toast, закрыть, перерендерить список.
  if (status === 404) {
    closeFilterModal();
    notify(message);
    if (typeof onChanged === "function") onChanged();
    return;
  }

  // 500 — ошибка сервера: toast, модалку не закрываем.
  if (status === 500) {
    notify(message);
    return;
  }

  // Сеть или таймаут 20 с: сообщение внутри модалки, модалку не закрываем.
  showFormError(elements, reason);
}

/**
 * Отправляет фильтр на сервер: `PUT /monitoring/{monitoring_id}/filter` (§9.5.5).
 *
 * @param {object} options — параметры сохранения
 * @param {object} options.elements — элементы формы
 * @param {string} options.monitoringId — monitoring_id пары пациент + врач
 * @param {Function} [options.onChanged] — перерендер списка карточек
 */
async function submitFilter({ elements, monitoringId, onChanged }) {
  clearErrors(elements);

  const fields = readFields(elements);
  const { errors, specificDates } = validateFilter(fields);

  if (Object.keys(errors).length > 0) {
    showErrors(elements, errors);
    return;
  }

  // PUT перезаписывает все пять полей — отправляем полный набор (§9.1, §9.11).
  const body = buildFilterPayload(fields, specificDates);

  setSaving(elements, true);
  try {
    await apiPut(
      `${FILTER_PATH_PREFIX}${encodeURIComponent(monitoringId)}/filter`,
      body,
    );

    closeFilterModal();
    notify(TEXT.saved);

    if (window.Telegram?.WebApp?.HapticFeedback) {
      window.Telegram.WebApp.HapticFeedback.notificationOccurred("success");
    }
    if (typeof onChanged === "function") onChanged();
  } catch (error) {
    handleSaveError(error, elements, onChanged);
  } finally {
    setSaving(elements, false);
  }
}

/**
 * Вешает обработчики закрытия и кнопок модалки.
 *
 * @param {object} options — параметры привязки
 * @param {HTMLElement} options.overlay — оверлей модалки
 * @param {HTMLElement} options.modal — панель модалки
 * @param {object} options.elements — элементы формы
 * @param {string} options.monitoringId — monitoring_id пары пациент + врач
 * @param {Function} [options.onChanged] — перерендер списка карточек
 */
function bindModalEvents({
  overlay,
  modal,
  elements,
  monitoringId,
  onChanged,
}) {
  const closeBtn = modal.querySelector("[data-filter-close]");
  if (closeBtn) {
    closeBtn.addEventListener("click", closeFilterModal);
  }

  // Клик по оверлею (но не по панели) закрывает модалку.
  overlay.addEventListener("click", (event) => {
    if (event.target === overlay) closeFilterModal();
  });

  escapeHandler = (event) => {
    if (event.key === "Escape") closeFilterModal();
  };
  document.addEventListener("keydown", escapeHandler);

  if (elements.resetButton) {
    elements.resetButton.addEventListener("click", () => resetForm(elements));
  }
  if (elements.saveButton) {
    elements.saveButton.addEventListener("click", () =>
      submitFilter({ elements, monitoringId, onChanged }),
    );
  }
}

/**
 * Закрывает модалку фильтра, если она открыта.
 *
 * Закрытие без сохранения не меняет фильтр (§9.5.2).
 */
export function closeFilterModal() {
  if (escapeHandler) {
    document.removeEventListener("keydown", escapeHandler);
    escapeHandler = null;
  }
  const overlay = document.getElementById(OVERLAY_ID);
  if (overlay) overlay.remove();
}

/**
 * Открывает модальную форму настройки фильтра (§9.5.2).
 *
 * @param {object} options — параметры открытия
 * @param {string} options.monitoringId — monitoring_id пары пациент + врач
 * @param {string} [options.doctorName=""] — ФИО врача для подзаголовка
 * @param {string} [options.patientName=""] — имя пациента для подзаголовка
 * @param {object|null} [options.filter=null] — текущий фильтр (предзаполнение)
 * @param {Function} [options.onChanged] — вызывается после успешного сохранения
 */
export function openFilterModal({
  monitoringId,
  doctorName = "",
  patientName = "",
  filter = null,
  onChanged,
}) {
  if (!monitoringId) return;

  closeFilterModal();

  const overlay = document.createElement("div");
  overlay.id = OVERLAY_ID;
  overlay.className = "app-modal-overlay";
  overlay.innerHTML = renderModalMarkup({ doctorName, patientName, filter });
  document.body.appendChild(overlay);

  const modal = overlay.querySelector(".app-modal");
  const elements = collectFormElements(modal);
  bindModalEvents({ overlay, modal, elements, monitoringId, onChanged });
}
