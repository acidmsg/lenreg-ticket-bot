/**
 * Утилиты для работы с DOM.
 *
 * @module utils/dom
 */

/**
 * Вызывает callback после готовности DOM.
 *
 * @param {Function} callback - Функция для вызова.
 */
export function onDOMReady(callback) {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', callback);
  } else {
    callback();
  }
}

// Обратная совместимость
if (typeof window !== 'undefined') {
  window.AppUtils = window.AppUtils || {};
  window.AppUtils.onDOMReady = onDOMReady;
}
