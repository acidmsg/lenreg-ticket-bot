/**
 * Безопасные обёртки над localStorage.
 *
 * Все методы перехватывают ошибки (QuotaExceededError, недоступность в iframe,
 * заблокированные cookie и т.п.) и возвращают fallback-значения при ошибках чтения.
 *
 * @module utils/storage
 */

/**
 * Безопасное чтение из localStorage.
 *
 * @param {string} key - Ключ.
 * @param {*} [defaultValue=null] - Значение по умолчанию при ошибке или отсутствии ключа.
 * @returns {string|null|*} Строковое значение, либо defaultValue при ошибке/отсутствии.
 */
export function safeGet(key, defaultValue = null) {
  try {
    const value = localStorage.getItem(key);
    return value !== null ? value : defaultValue;
  } catch (_) {
    return defaultValue;
  }
}

/**
 * Безопасная запись в localStorage.
 *
 * @param {string} key - Ключ.
 * @param {string} value - Значение (строка).
 */
export function safeSet(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch (_) {
    // Игнорируем ошибки localStorage (QuotaExceededError, недоступность)
  }
}

/**
 * Безопасное удаление из localStorage.
 *
 * @param {string} key - Ключ.
 */
export function safeRemove(key) {
  try {
    localStorage.removeItem(key);
  } catch (_) {
    // Игнорируем ошибки localStorage
  }
}

// Обратная совместимость: глобальный доступ для IIFE-скриптов (_design_lab/ и др.)
if (typeof window !== 'undefined') {
  window.AppUtils = window.AppUtils || {};
  window.AppUtils.safeGet = safeGet;
  window.AppUtils.safeSet = safeSet;
  window.AppUtils.safeRemove = safeRemove;
}
