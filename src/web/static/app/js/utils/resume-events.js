/**
 * События возврата приложения после фона/потери сети.
 *
 * Подписки собираются в один debounce-канал, чтобы каскад событий
 * (visibilitychange + activate + online) не запускал сверку несколько раз.
 *
 * @module utils/resume-events
 */

import { BOOKING_INTENT_KEY } from "./booking-lock.js";

/** Окно схлопывания каскада событий. */
const RESUME_DEBOUNCE_MS = 400;

/** Подписчики на возврат. */
const listeners = new Set();
let scheduled = false;

/**
 * Планирует уведомление подписчиков один раз за окно debounce.
 * @param {string} reason - источник события
 */
function schedule(reason) {
  if (scheduled) return;
  scheduled = true;
  setTimeout(() => {
    scheduled = false;
    listeners.forEach((cb) => {
      try {
        cb(reason);
      } catch (_) {
        // Сбой подписчика не должен ломать остальные и сам канал.
      }
    });
  }, RESUME_DEBOUNCE_MS);
}

/**
 * Подписывает на возврат приложения.
 * @param {(reason: string) => void} callback
 * @returns {() => void} отписка
 */
export function onResume(callback) {
  listeners.add(callback);
  return () => listeners.delete(callback);
}

/** Инициализирует источники событий возврата (идемпотентно по факту). */
export function initResumeEvents() {
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) schedule("visibilitychange");
  });
  window.addEventListener("online", () => schedule("online"));
  window.addEventListener("storage", (event) => {
    // Реагируем только на смену интента записи, а не на любой ключ.
    if (!event || !event.key || event.key === BOOKING_INTENT_KEY) {
      schedule("storage");
    }
  });

  const wa = window.Telegram?.WebApp;
  if (wa && typeof wa.onEvent === "function") {
    wa.onEvent("activate", () => schedule("activate"));
  }
}
