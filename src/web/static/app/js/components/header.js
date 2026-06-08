/**
 * Компонент шапки Mini App.
 * Отображает заголовок страницы, кнопку «Назад» (опционально) и имя пользователя.
 *
 * @module components/header
 */

import { lucideIcon } from './icon.js';

/**
 * Рендерит HTML шапки.
 *
 * @param {string} title — заголовок страницы
 * @param {boolean} [showBack=false] — показывать ли кнопку «Назад»
 * @param {string} [userName=''] — имя пользователя
 * @returns {string} HTML-строка шапки
 */
export function renderHeader(title, showBack = false, userName = '') {
  const backButtonHtml = showBack
    ? `<button class="app-header__back" aria-label="Назад" id="header-back">${lucideIcon('chevron-left', 24)}</button>`
    : '';

  const userNameHtml = userName
    ? `<span class="app-header__user">${escapeHtml(userName)}</span>`
    : '';

  return `
    <header class="app-header">
      ${backButtonHtml}
      <h1 class="app-header__title">${escapeHtml(title)}</h1>
      ${userNameHtml}
    </header>
  `;
}

/**
 * Экранирует HTML-символы для безопасного рендеринга.
 *
 * @param {string} text — исходный текст
 * @returns {string} экранированный текст
 */
function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}
