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
  const div = document.createElement("div");
  div.textContent = String(text);
  return div.innerHTML;
}

/**
 * Экранирует значение для вставки в HTML-атрибут.
 *
 * ``escapeHtml()`` не трогает кавычки, поэтому название клиники вида
 * ``ГБУЗ ЛО "СЕРТОЛОВСКАЯ ГБ"`` обрывало атрибут ``data-clinic`` на первой
 * кавычке — в календарь уезжало одно «ГБУЗ ЛО».
 *
 * @param {*} text - Исходное значение (приводится к строке).
 * @returns {string} Экранированное значение без кавычек и угловых скобок.
 */
export function escapeAttr(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

// Обратная совместимость: глобальный доступ для кода, не использующего ES6-модули
if (typeof window !== "undefined") {
  window.AppUtils = window.AppUtils || {};
  window.AppUtils.escapeHtml = escapeHtml;
  window.AppUtils.escapeAttr = escapeAttr;
}
