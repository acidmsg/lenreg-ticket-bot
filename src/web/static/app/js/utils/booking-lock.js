/**
 * Мьютекс записи и «интент в полёте» для экрана бронирования.
 *
 * Интент в localStorage переживает перезагрузку и потерю связи: пока он есть,
 * интерфейс заблокирован, а после возврата приложение сверяет статус записи
 * (GET /api/user/bookings), а не повторяет запрос вслепую.
 *
 * @module utils/booking-lock
 */

import { safeGet, safeSet, safeRemove } from "./storage.js";

/** Ключ интента записи в localStorage. */
export const BOOKING_INTENT_KEY = "miniapp-booking-intent";

/** Время жизни интента: старше — считаем устаревшим и вычищаем. */
export const BOOKING_INTENT_TTL_MS = 15 * 60 * 1000;

/** Идёт ли запрос прямо сейчас (в памяти вкладки). */
let inFlight = false;

/**
 * Текущий интент записи или null.
 * @returns {object|null}
 */
export function readBookingIntent() {
  const raw = safeGet(BOOKING_INTENT_KEY, "");
  if (!raw) return null;
  let intent;
  try {
    intent = JSON.parse(raw);
  } catch {
    safeRemove(BOOKING_INTENT_KEY);
    return null;
  }
  const at = Number(intent && intent.at) || 0;
  if (!at || Date.now() - at > BOOKING_INTENT_TTL_MS) {
    // Устаревший интент не должен блокировать интерфейс навсегда.
    safeRemove(BOOKING_INTENT_KEY);
    return null;
  }
  return intent;
}

/**
 * Сохраняет интент записи.
 * @param {object} intent
 */
export function setBookingIntent(intent) {
  safeSet(BOOKING_INTENT_KEY, JSON.stringify(intent));
}

/** Очищает интент записи. */
export function clearBookingIntent() {
  safeRemove(BOOKING_INTENT_KEY);
}

/**
 * Заблокирован ли интерфейс: идёт запрос или остался незавершённый интент.
 * @returns {boolean}
 */
export function isBookingLocked() {
  return inFlight || readBookingIntent() !== null;
}

/**
 * Атомарно занимает мьютекс.
 * @returns {boolean} false, если уже занят
 */
export function acquireBookingLock() {
  if (inFlight) return false;
  inFlight = true;
  return true;
}

/** Освобождает мьютекс. */
export function releaseBookingLock() {
  inFlight = false;
}

/** Идёт ли POST прямо сейчас (в памяти вкладки). */
export function isBookingInFlight() {
  return inFlight;
}
