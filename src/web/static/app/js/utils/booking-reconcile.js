/**
 * Сверка «интента в полёте» с фактическими записями.
 * @module utils/booking-reconcile
 */

import { apiGet } from "../api.js";
import { clearBookingIntent, isBookingInFlight, readBookingIntent } from "./booking-lock.js";
import { hideBookingOverlay, showBookingOverlay } from "./booking-overlay.js";

/** Окно, в течение которого «не найдено» ещё не значит «не оформлено». */
export const RECONCILE_GRACE_MS = 25000;

let reconcilePromise = null;

/**
 * Ожидаемый booking_id из полей интента (точное равенство, не подстрока).
 * @param {object} intent
 * @returns {string}
 */
export function expectedBookingId(intent) {
  const p = intent.patientId || "";
  const d = intent.doctorId || "";
  const a = intent.appointmentId || "";
  return p + "_" + d + "_" + a;
}

async function runReconcile() {
  const intent = readBookingIntent();
  if (!intent) return { found: false };
  if (isBookingInFlight()) return { found: false, pending: true };

  showBookingOverlay("Проверяем статус…");
  try {
    const data = await apiGet("/bookings");
    const bookings = (data && data.bookings) || [];
    const expected = expectedBookingId(intent);
    const found = bookings.find((b) => String((b && b.booking_id) || "") === expected);

    if (found) {
      clearBookingIntent();
      if (window.showToast) window.showToast("✅ Запись подтверждена.", "success");
      return { found: true, booking: found };
    }

    const age = Date.now() - (Number(intent.at) || 0);
    if (age < RECONCILE_GRACE_MS) return { found: false, pending: true };

    clearBookingIntent();
    if (window.showToast) {
      window.showToast("Запись не подтверждена. Попробуйте ещё раз.", "error");
    }
    return { found: false };
  } catch (error) {
    if (window.showToast) {
      window.showToast("Не удалось проверить статус записи.", "info");
    }
    return { found: false, error: error && error.message };
  } finally {
    hideBookingOverlay();
  }
}

/**
 * Сверка с дедупликацией параллельных вызовов.
 * @returns {Promise<object>}
 */
export function reconcileBookingIntent() {
  if (reconcilePromise) return reconcilePromise;
  reconcilePromise = runReconcile().finally(() => {
    reconcilePromise = null;
  });
  return reconcilePromise;
}
