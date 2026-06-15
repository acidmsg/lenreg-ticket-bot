/**
 * Общие UI-утилиты: рендеринг ошибок, уведомлений, диалоги подтверждения.
 */

import { escapeHtml } from './escape.js';

/**
 * Показать toast-уведомление.
 * @param {string} message
 * @param {'success'|'error'|'info'} type
 */
export function showToast(message, type = 'info') {
  const toast = document.createElement('div');
  toast.className = `toast toast--${type}`;
  toast.textContent = message;
  document.body.appendChild(toast);
  requestAnimationFrame(() => toast.classList.add('toast--visible'));
  setTimeout(() => {
    toast.classList.remove('toast--visible');
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

/**
 * Показать диалог подтверждения (Telegram ShowConfirm или браузерный confirm).
 * Унифицирует inline-логику из doctors.js, slots.js и patients.js.
 *
 * @param {string} message - текст подтверждения
 * @returns {Promise<boolean>}
 */
export async function showConfirm(message) {
  if (window.Telegram?.WebApp?.showConfirm) {
    return await new Promise((resolve) => {
      window.Telegram.WebApp.showConfirm(message, (result) => resolve(result));
    });
  }
  return window.confirm(message);
}
