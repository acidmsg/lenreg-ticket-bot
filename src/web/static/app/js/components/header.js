/**
 * Компонент шапки Mini App.
 * Отображает заголовок страницы, кнопку «Назад» (опционально), имя пользователя
 * и кнопку выбора темы.
 *
 * @module components/header
 */

import { lucideIcon } from "./icon.js";
import { escapeHtml } from "../utils/escape.js";
import { getThemeMode, THEME_DARK, THEME_LIGHT } from "../theme.js";

/** Иконка кнопки темы по текущему режиму. */
const MODE_ICONS = {
  [THEME_DARK]: "moon",
  [THEME_LIGHT]: "sun",
};

/** Подпись режима для `aria-label` кнопки темы. */
const MODE_LABELS = {
  system: "системная",
  [THEME_DARK]: "тёмная",
  [THEME_LIGHT]: "светлая",
};

/**
 * Возвращает HTML иконки кнопки темы для текущего режима.
 *
 * @returns {string} HTML иконки
 */
export function themeButtonIcon() {
  return lucideIcon(MODE_ICONS[getThemeMode()] || "monitor", 20);
}

/**
 * Возвращает `aria-label` кнопки темы для текущего режима.
 *
 * @returns {string} подпись кнопки
 */
export function themeButtonLabel() {
  const mode = getThemeMode();
  return `Тема оформления: ${MODE_LABELS[mode] || MODE_LABELS.system}`;
}

/**
 * Обновляет иконку и подпись кнопки темы после смены режима.
 */
export function refreshThemeButton() {
  const button = document.getElementById("header-theme");
  if (!button) return;
  button.innerHTML = themeButtonIcon();
  button.setAttribute("aria-label", themeButtonLabel());
}

/**
 * Рендерит HTML шапки.
 *
 * @param {string} title — заголовок страницы
 * @param {boolean} [showBack=false] — показывать ли кнопку «Назад»
 * @param {string} [userName=''] — имя пользователя
 * @returns {string} HTML-строка шапки
 */
export function renderHeader(title, showBack = false, userName = "") {
  const backButtonHtml = showBack
    ? `<button class="app-header__back" aria-label="Назад" id="header-back">${lucideIcon("chevron-left", 24)}</button>`
    : "";

  const userNameHtml = userName
    ? `<span class="app-header__user">${escapeHtml(userName)}</span>`
    : "";

  const themeButtonHtml = `
      <button
        type="button"
        class="app-header__theme"
        id="header-theme"
        aria-label="${escapeHtml(themeButtonLabel())}"
      >${themeButtonIcon()}</button>`;

  return `
    <header class="app-header">
      ${backButtonHtml}
      <h1 class="app-header__title">${escapeHtml(title)}</h1>
      ${userNameHtml}${themeButtonHtml}
    </header>
  `;
}
