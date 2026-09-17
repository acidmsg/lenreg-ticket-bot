/**
 * Общие утилиты для рендеринга ошибок.
 * Устраняет дублирование renderError/bindErrorEvents в doctors.js, patients.js, slots.js.
 *
 * @module utils/error
 */

import { escapeHtml } from "./escape.js";
import { lucideIcon } from "../components/icon.js";

/**
 * Маппинг кодов ошибок API → человекочитаемые сообщения (T-19).
 * Дублирует серверный ``format_error_message()`` из ``src/utils/helpers.py``.
 *
 * @type {Record<string, string>}
 */
/** Единый текст при недоступности внешнего сервиса записи (HTTP 502/504). */
export const SERVICE_UNAVAILABLE_MESSAGE =
  "Сервис клиники временно недоступен, попробуйте позже.";

/** HTTP-статусы недоступности внешнего сервиса записи: 502 и 504. */
export const SERVICE_UNAVAILABLE_STATUSES = [502, 504];

/**
 * Проверяет, что ошибка означает недоступность внешнего сервиса записи.
 *
 * @param {{status?: number}|null} error - ошибка запроса либо ответ fetch
 * @returns {boolean} true для HTTP 502/504
 */
export function isServiceUnavailableError(error) {
  return SERVICE_UNAVAILABLE_STATUSES.includes(error?.status);
}

export const ERROR_MESSAGES = {
  slot_taken: "Слот уже занят. Выберите другой.",
  api_unavailable: "Сервис записи временно недоступен. Попробуйте позже.",
  api_timeout: "Сервис записи не отвечает. Попробуйте позже.",
  forbidden: "Сессия истекла. Пожалуйста, начните заново.",
  unknown: "Произошла непредвиденная ошибка.",
  no_slots: "На данный момент талонов нет.",
  monitoring_already_exists: "Враг уже в отслеживании.",
};

/**
 * Возвращает человекочитаемое сообщение по коду ошибки.
 *
 * @param {string} errorCode - Код ошибки из ответа API (поле ``error``).
 * @param {string} [detail] - Дополнительная деталь.
 * @returns {string} Отформатированное сообщение.
 */
export function formatErrorCode(errorCode, detail) {
  const base = ERROR_MESSAGES[errorCode] || ERROR_MESSAGES["unknown"];
  return detail ? `${base}\n\nПричина: ${detail}` : base;
}

/**
 * Отрисовать состояние ошибки с кнопкой «Повторить».
 * Разметка унифицирована на основе реализаций в doctors.js, patients.js, slots.js.
 *
 * @param {HTMLElement} container - контейнер для вставки
 * @param {string} message - текст ошибки
 * @param {string} retryLabel - текст кнопки повтора (обычно «Повторить»)
 * @param {Function} onRetry - callback при клике на «Повторить»
 * @param {string} [retryBtnId='error-retry-btn'] - ID кнопки повтора (для обратной совместимости)
 */
export function renderError(
  container,
  message,
  retryLabel,
  onRetry,
  retryBtnId = "error-retry-btn",
) {
  container.innerHTML = `
    <div class="error-state">
      <div class="empty-state__icon">${lucideIcon("triangle-alert", 48)}</div>
      <p class="error-state__text">${escapeHtml(message)}</p>
      <button class="btn btn--primary" id="${escapeHtml(retryBtnId)}"><span class="lucide-icon">${lucideIcon("refresh-cw", 16)}</span> ${escapeHtml(retryLabel)}</button>
    </div>
  `;
  const retryBtn = container.querySelector(`#${CSS.escape(retryBtnId)}`);
  if (retryBtn && onRetry) {
    retryBtn.addEventListener("click", onRetry);
  }
}
