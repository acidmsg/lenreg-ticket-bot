/**
 * Утилита экранирования HTML.
 * Экспортируется как ES6-модуль. Для обратной совместимости
 * также доступна через window.AppUtils.escapeHtml.
 */

/**
 * Экранирует HTML-сущности в строке.
 * @param {*} text - Исходный текст (приводится к строке).
 * @returns {string} Экранированная строка.
 */
export function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = String(text);
  return div.innerHTML;
}

// Обратная совместимость: глобальный доступ для кода, не использующего ES6-модули
if (typeof window !== 'undefined') {
  window.AppUtils = window.AppUtils || {};
  window.AppUtils.escapeHtml = escapeHtml;
}
