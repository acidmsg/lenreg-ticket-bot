/**
 * Тема Mini App: системная, тёмная, светлая.
 *
 * Выбранный режим хранится в localStorage (`miniapp-theme`), по умолчанию —
 * системный. Системный режим следует теме Telegram (`Telegram.WebApp.colorScheme`),
 * а при его отсутствии — медиазапросу `prefers-color-scheme`.
 *
 * Разметку переключателя даёт `components/theme-sheet.js`; раннее применение
 * режима до первой отрисовки — inline-скрипт в `index.html` (без вспышки темы).
 *
 * @module theme
 */

import { safeGet, safeSet } from "./utils/storage.js";

/** Ключ localStorage с выбранным режимом темы. */
export const THEME_STORAGE_KEY = "miniapp-theme";

/** Системный режим: следовать теме Telegram или ОС. */
export const THEME_SYSTEM = "system";

/** Принудительно тёмная тема. */
export const THEME_DARK = "dark";

/** Принудительно светлая тема. */
export const THEME_LIGHT = "light";

/** Допустимые режимы темы. */
export const THEME_MODES = [THEME_SYSTEM, THEME_DARK, THEME_LIGHT];

/** Подписчики на изменение темы. */
const listeners = new Set();

/** Признак однократной подписки на события Telegram/медиазапроса. */
let subscribed = false;

/**
 * Приводит произвольное значение к допустимому режиму темы.
 *
 * @param {string|null} value — значение из хранилища или интерфейса
 * @returns {string} допустимый режим (`system` при неизвестном значении)
 */
export function normalizeMode(value) {
  return THEME_MODES.includes(value) ? value : THEME_SYSTEM;
}

/**
 * Читает сохранённый режим темы.
 *
 * @returns {string} режим темы (`system`, `dark` или `light`)
 */
export function getThemeMode() {
  return normalizeMode(safeGet(THEME_STORAGE_KEY, THEME_SYSTEM));
}

/**
 * Определяет текущую тему системы: сначала Telegram, затем медиазапрос.
 *
 * @returns {string} `light` или `dark`
 */
export function getSystemTheme() {
  const scheme = window.Telegram?.WebApp?.colorScheme;
  if (scheme === THEME_LIGHT || scheme === THEME_DARK) return scheme;

  if (
    window.matchMedia &&
    window.matchMedia("(prefers-color-scheme: light)").matches
  ) {
    return THEME_LIGHT;
  }
  return THEME_DARK;
}

/**
 * Превращает режим в конкретную тему для атрибута `data-theme`.
 *
 * @param {string} mode — режим темы
 * @returns {string} `light` или `dark`
 */
export function resolveTheme(mode) {
  const normalized = normalizeMode(mode);
  return normalized === THEME_SYSTEM ? getSystemTheme() : normalized;
}

/**
 * Применяет режим к документу и уведомляет подписчиков.
 *
 * @param {string} mode — режим темы
 * @returns {string} применённая тема (`light` или `dark`)
 */
export function applyThemeMode(mode) {
  const normalized = normalizeMode(mode);
  const resolved = resolveTheme(normalized);

  document.documentElement.dataset.theme = resolved;
  document.documentElement.dataset.themeMode = normalized;

  listeners.forEach((callback) => {
    try {
      callback(normalized, resolved);
    } catch (_error) {
      // Подписчик не должен ломать переключение темы
    }
  });

  return resolved;
}

/**
 * Сохраняет и применяет выбранный режим темы.
 *
 * @param {string} mode — режим темы (`system`, `dark` или `light`)
 * @returns {string} применённый режим
 */
export function setThemeMode(mode) {
  const normalized = normalizeMode(mode);
  safeSet(THEME_STORAGE_KEY, normalized);
  applyThemeMode(normalized);
  return normalized;
}

/**
 * Подписывает обработчик на изменение темы.
 *
 * @param {(mode: string, resolved: string) => void} callback — обработчик
 * @returns {() => void} функция отписки
 */
export function subscribeTheme(callback) {
  listeners.add(callback);
  return () => listeners.delete(callback);
}

/**
 * Применяет сохранённый режим и подписывается на смену темы Telegram и ОС.
 *
 * Подписка выполняется один раз: повторный вызов только переприменяет режим.
 */
export function initTheme() {
  applyThemeMode(getThemeMode());

  if (subscribed) return;
  subscribed = true;

  const onSystemChange = () => {
    if (getThemeMode() === THEME_SYSTEM) applyThemeMode(THEME_SYSTEM);
  };

  const tg = window.Telegram?.WebApp;
  if (tg && typeof tg.onEvent === "function") {
    tg.onEvent("themeChanged", onSystemChange);
  }

  if (window.matchMedia) {
    const query = window.matchMedia("(prefers-color-scheme: light)");
    if (typeof query.addEventListener === "function") {
      query.addEventListener("change", onSystemChange);
    } else if (typeof query.addListener === "function") {
      query.addListener(onSystemChange);
    }
  }
}
