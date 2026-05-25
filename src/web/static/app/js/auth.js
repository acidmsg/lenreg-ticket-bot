/**
 * Модуль аутентификации Mini App.
 * Получает initData из Telegram.WebApp для передачи в API.
 *
 * @module auth
 */

/**
 * Проверяет, запущено ли приложение внутри Telegram.
 *
 * @returns {boolean} true, если доступен Telegram.WebApp
 */
export function isInTelegram() {
  return !!(window.Telegram && window.Telegram.WebApp);
}

/**
 * Возвращает initData — подписанную строку для аутентификации на сервере.
 * Используется в заголовке X-Telegram-InitData при каждом API-запросе.
 *
 * @returns {string} строка initData или пустая строка, если не в Telegram
 */
export function getInitData() {
  if (!isInTelegram()) {
    return '';
  }
  return window.Telegram.WebApp.initData || '';
}

/**
 * Возвращает распарсенные данные пользователя из initDataUnsafe.
 * Используется ТОЛЬКО для отображения (имя, фото), НЕ для auth.
 *
 * @returns {object|null} объект user или null, если недоступен
 */
export function getUserInfo() {
  if (!isInTelegram()) {
    return null;
  }
  const unsafe = window.Telegram.WebApp.initDataUnsafe;
  return unsafe && unsafe.user ? unsafe.user : null;
}
