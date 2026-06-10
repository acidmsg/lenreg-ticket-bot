(function () {
  'use strict';

  window.AppUtils = window.AppUtils || {};

  /**
   * Извлекает полное имя врача из поля name (строка или объект).
   * @param {string|Object} name - Имя врача.
   * @param {string} [fallback=''] - Значение по умолчанию, если имя не удалось извлечь.
   * @returns {string} Полное имя врача (Фамилия Имя Отчество) или fallback.
   */
  window.AppUtils.extractDoctorName = function extractDoctorName(
    name,
    fallback
  ) {
    fallback = fallback || '';
    if (typeof name === 'string') {
      return name.trim() || fallback;
    }
    if (typeof name === 'object' && name !== null) {
      const parts = [];
      if (name.last_name) parts.push(name.last_name);
      if (name.first_name) parts.push(name.first_name);
      if (name.middle_name) parts.push(name.middle_name);
      return parts.length > 0 ? parts.join(' ') : fallback;
    }
    return fallback;
  };
})();
