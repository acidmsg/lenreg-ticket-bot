/**
 * Разбор deep-link параметра `startapp` Telegram Mini App.
 *
 * Telegram передаёт значение `?startapp=…` в
 * `Telegram.WebApp.initDataUnsafe.start_param` только при открытии по прямой
 * ссылке `https://t.me/<bot>?startapp=…`. Здесь параметр превращается в
 * целевой маршрут SPA — чистый разбор без побочных эффектов.
 *
 * @module utils/start-param
 */

/**
 * Формат deep-link на экран номерков: `slots_<p_id>_<d_id>`.
 *
 * Инвариант: ``p_id`` и ``d_id`` — числовые идентификаторы (без «_»), поэтому
 * разделитель однозначен. При нарушении инварианта (id с «_») regex не
 * совпадает — разбор возвращает ``null`` и приложение открывает обычный
 * главный экран. Это осознанное поведение, а не ошибка.
 */
const SLOTS_PATTERN = /^slots_([^_]+)_([^_]+)$/;

/** Значения `start_param`, которые открывают простой маршрут без параметров. */
const SIMPLE_ROUTES = new Set(["patients", "bookings", "add"]);

/**
 * Разбирает значение `start_param` в целевой маршрут Mini App.
 *
 * Поддерживаемые форматы:
 * - `slots_<p_id>_<d_id>` → маршрут `slots` с `{ monitoringId: "<p_id>_<d_id>" }`;
 * - `patients`, `bookings`, `add` → соответствующий маршрут без параметров.
 *
 * Пустое или неизвестное значение даёт `null`: вызывающий код остаётся на
 * поведении по умолчанию (главный экран). Инвариант id и поведение при его
 * нарушении описаны у `SLOTS_PATTERN`.
 *
 * @param {string} param — значение `start_param` (может быть пустым/не строкой)
 * @returns {{route: string, params: object|null}|null} маршрут и параметры либо `null`
 */
export function parseStartParam(param) {
  const value = typeof param === "string" ? param : "";
  if (!value) {
    return null;
  }

  const slotsMatch = SLOTS_PATTERN.exec(value);
  if (slotsMatch) {
    const [, patientId, doctorId] = slotsMatch;
    return {
      route: "slots",
      params: { monitoringId: `${patientId}_${doctorId}` },
    };
  }

  if (SIMPLE_ROUTES.has(value)) {
    return { route: value, params: null };
  }

  return null;
}
