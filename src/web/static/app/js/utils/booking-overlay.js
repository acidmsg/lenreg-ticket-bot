/**
 * Полноэкранный overlay хода записи к врачу.
 *
 * Блокирует интерфейс на время POST /book и во время сверки статуса после
 * возврата (вариант V4). В index.html контейнера нет — создаётся динамически.
 *
 * @module utils/booking-overlay
 */

const OVERLAY_ID = "booking-overlay";

/**
 * Показывает overlay с указанным текстом (создаёт при первом вызове).
 * @param {string} message - «Оформляем запись…», «Проверяем статус…»
 */
export function showBookingOverlay(message) {
  let el = document.getElementById(OVERLAY_ID);
  if (!el) {
    el = document.createElement("div");
    el.id = OVERLAY_ID;
    el.className = "booking-overlay";
    el.setAttribute("role", "status");
    el.setAttribute("aria-live", "polite");
    el.innerHTML =
      '<div class="booking-overlay__box">' +
      '<div class="booking-overlay__spinner" aria-hidden="true"></div>' +
      '<div class="booking-overlay__text"></div>' +
      "</div>";
    document.body.appendChild(el);
  }
  const text = el.querySelector(".booking-overlay__text");
  if (text) text.textContent = message;
  requestAnimationFrame(() => el.classList.add("booking-overlay--visible"));
}

/** Скрывает и удаляет overlay. */
export function hideBookingOverlay() {
  const el = document.getElementById(OVERLAY_ID);
  if (!el) return;
  el.classList.remove("booking-overlay--visible");
  setTimeout(() => el.remove(), 200);
}
