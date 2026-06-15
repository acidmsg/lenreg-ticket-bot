/**
 * Общие утилиты для рендеринга ошибок.
 * Устраняет дублирование renderError/bindErrorEvents в doctors.js, patients.js, slots.js.
 *
 * @module utils/error
 */

import { escapeHtml } from './escape.js';
import { lucideIcon } from '../components/icon.js';

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
  retryBtnId = 'error-retry-btn'
) {
  container.innerHTML = `
    <div class="error-state">
      <div class="empty-state__icon">${lucideIcon('triangle-alert', 48)}</div>
      <p class="error-state__text">${escapeHtml(message)}</p>
      <button class="btn btn--primary" id="${escapeHtml(retryBtnId)}"><span class="lucide-icon">${lucideIcon('refresh-cw', 16)}</span> ${escapeHtml(retryLabel)}</button>
    </div>
  `;
  const retryBtn = container.querySelector(`#${CSS.escape(retryBtnId)}`);
  if (retryBtn && onRetry) {
    retryBtn.addEventListener('click', onRetry);
  }
}
