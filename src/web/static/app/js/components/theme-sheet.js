/**
 * Шит выбора темы Mini App: системная, тёмная, светлая.
 *
 * Открывается кнопкой в шапке (`#header-theme`). Выбор применяется сразу и
 * сохраняется в localStorage модулем `theme.js`.
 *
 * @module components/theme-sheet
 */

import { lucideIcon } from "./icon.js";
import { escapeHtml } from "../utils/escape.js";
import {
  THEME_SYSTEM,
  THEME_DARK,
  THEME_LIGHT,
  getThemeMode,
  setThemeMode,
} from "../theme.js";
import { refreshThemeButton } from "./header.js";

/** Идентификатор оверлея шита в DOM. */
const OVERLAY_ID = "theme-sheet-overlay";

/** Варианты темы в порядке отображения. */
const OPTIONS = [
  {
    mode: THEME_SYSTEM,
    icon: "monitor",
    label: "Системная",
    hint: "Как в Telegram",
  },
  { mode: THEME_DARK, icon: "moon", label: "Тёмная", hint: "Неоновая плазма" },
  {
    mode: THEME_LIGHT,
    icon: "sun",
    label: "Светлая",
    hint: "Медицинская чистота",
  },
];

/**
 * Рендерит один вариант темы.
 *
 * @param {object} option — вариант темы
 * @param {string} activeMode — текущий режим темы
 * @returns {string} HTML варианта
 */
function renderOption(option, activeMode) {
  const isActive = option.mode === activeMode;
  const activeClass = isActive ? " theme-sheet__option--active" : "";

  return `
        <button
          type="button"
          class="theme-sheet__option${activeClass}"
          data-theme-mode="${option.mode}"
          aria-pressed="${isActive ? "true" : "false"}"
        >
          <span class="theme-sheet__option-icon">${lucideIcon(option.icon, 20)}</span>
          <span class="theme-sheet__option-text">
            <span class="theme-sheet__option-label">${escapeHtml(option.label)}</span>
            <span class="theme-sheet__option-hint">${escapeHtml(option.hint)}</span>
          </span>
          <span class="theme-sheet__option-check">${lucideIcon("check", 18)}</span>
        </button>`;
}

/**
 * Рендерит разметку шита выбора темы.
 *
 * @returns {string} HTML шита
 */
function renderSheetMarkup() {
  const activeMode = getThemeMode();
  const options = OPTIONS.map((option) =>
    renderOption(option, activeMode),
  ).join("");

  return `
    <div
      class="app-modal theme-sheet"
      role="dialog"
      aria-modal="true"
      aria-labelledby="theme-sheet-title"
    >
      <div class="app-modal__header">
        <h2 class="app-modal__title" id="theme-sheet-title">Тема оформления</h2>
        <button
          type="button"
          class="app-modal__close"
          id="theme-sheet-close"
          aria-label="Закрыть"
        >${lucideIcon("x", 18)}</button>
      </div>
      <div class="app-modal__body">
        <div class="theme-sheet__options">${options}
        </div>
      </div>
    </div>
  `;
}

/**
 * Обновляет отметку активного варианта без перерисовки шита.
 *
 * @param {HTMLElement} overlay — оверлей шита
 * @param {string} mode — выбранный режим темы
 */
function markActiveOption(overlay, mode) {
  overlay.querySelectorAll(".theme-sheet__option").forEach((option) => {
    const isActive = option.dataset.themeMode === mode;
    option.classList.toggle("theme-sheet__option--active", isActive);
    option.setAttribute("aria-pressed", isActive ? "true" : "false");
  });
}

/**
 * Закрывает шит выбора темы, если он открыт.
 */
export function closeThemeSheet() {
  const overlay = document.getElementById(OVERLAY_ID);
  if (overlay) overlay.remove();
  document.removeEventListener("keydown", handleKeydown);
}

/**
 * Закрывает шит по нажатию Escape.
 *
 * @param {KeyboardEvent} event — событие клавиатуры
 */
function handleKeydown(event) {
  if (event.key === "Escape") closeThemeSheet();
}

/**
 * Открывает шит выбора темы.
 */
export function openThemeSheet() {
  closeThemeSheet();

  const overlay = document.createElement("div");
  overlay.id = OVERLAY_ID;
  overlay.className = "app-modal-overlay";
  overlay.innerHTML = renderSheetMarkup();
  document.body.appendChild(overlay);

  overlay.addEventListener("click", (event) => {
    if (event.target === overlay) closeThemeSheet();
  });

  overlay
    .querySelector("#theme-sheet-close")
    .addEventListener("click", closeThemeSheet);

  overlay.querySelectorAll(".theme-sheet__option").forEach((option) => {
    option.addEventListener("click", () => {
      const mode = setThemeMode(option.dataset.themeMode);
      markActiveOption(overlay, mode);
      refreshThemeButton();
      closeThemeSheet();
    });
  });

  document.addEventListener("keydown", handleKeydown);
}
