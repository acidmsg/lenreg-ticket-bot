(function () {
  'use strict';

  window.AppUtils = window.AppUtils || {};

  /**
   * Вызывает callback после готовности DOM.
   * @param {Function} callback - Функция для вызова.
   */
  window.AppUtils.onDOMReady = function onDOMReady(callback) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', callback);
    } else {
      callback();
    }
  };
})();
