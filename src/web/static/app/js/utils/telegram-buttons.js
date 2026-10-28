/**
 * Управление системными кнопками Telegram: MainButton и SecondaryButton.
 *
 * @module utils/telegram-buttons
 */

/** @returns {object|null} объект Telegram.WebApp */
function getWebApp() {
  return window.Telegram?.WebApp || null;
}

let mainHandler = null;
let secondaryHandler = null;

/**
 * Скрывает системные кнопки и снимает обработчики.
 */
export function hideSystemButtons() {
  const tg = getWebApp();
  if (!tg) return;

  if (tg.MainButton) {
    if (mainHandler) tg.MainButton.offClick(mainHandler);
    mainHandler = null;
    tg.MainButton.hide();
  }

  if (tg.SecondaryButton) {
    if (secondaryHandler) tg.SecondaryButton.offClick(secondaryHandler);
    secondaryHandler = null;
    tg.SecondaryButton.hide();
  }
}

/**
 * Скрывает только SecondaryButton.
 */
export function hideSecondaryButton() {
  const tg = getWebApp();
  if (!tg?.SecondaryButton) return;
  if (secondaryHandler) tg.SecondaryButton.offClick(secondaryHandler);
  secondaryHandler = null;
  tg.SecondaryButton.hide();
}

/**
 * Показывает MainButton с заданным текстом и обработчиком.
 *
 * @param {object} options — параметры
 * @param {string} options.text — текст кнопки
 * @param {Function} options.onClick — обработчик нажатия
 * @param {boolean} [options.disabled=false] — неактивное состояние
 * @returns {boolean} true, если кнопка показана
 */
export function showMainButton({ text, onClick, disabled = false }) {
  const tg = getWebApp();
  if (!tg?.MainButton) return false;

  tg.MainButton.setText(String(text || ""));
  if (disabled) tg.MainButton.disable();
  else tg.MainButton.enable();
  tg.MainButton.show();

  if (mainHandler) tg.MainButton.offClick(mainHandler);
  mainHandler = () => {
    if (!disabled) onClick?.();
  };
  tg.MainButton.onClick(mainHandler);
  return true;
}

/**
 * Показывает SecondaryButton с заданным текстом и обработчиком.
 *
 * @param {object} options — параметры
 * @param {string} options.text — текст кнопки
 * @param {Function} options.onClick — обработчик нажатия
 * @param {boolean} [options.disabled=false] — неактивное состояние
 * @returns {boolean} true, если кнопка показана
 */
export function showSecondaryButton({ text, onClick, disabled = false }) {
  const tg = getWebApp();
  if (!tg?.SecondaryButton) return false;

  tg.SecondaryButton.setText(String(text || ""));
  if (disabled) tg.SecondaryButton.disable();
  else tg.SecondaryButton.enable();
  tg.SecondaryButton.show();

  if (secondaryHandler) tg.SecondaryButton.offClick(secondaryHandler);
  secondaryHandler = () => {
    if (!disabled) onClick?.();
  };
  tg.SecondaryButton.onClick(secondaryHandler);
  return true;
}
