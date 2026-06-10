/**
 * Утилиты приложения.
 * Используется через window.AppUtils.*
 */
(function () {
  'use strict';

  window.AppUtils = window.AppUtils || {};

  /**
   * Экранирует HTML-сущности в строке.
   * @param {*} text - Исходный текст (приводится к строке).
   * @returns {string} Экранированная строка.
   */
  window.AppUtils.escapeHtml = function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
  };
})();
