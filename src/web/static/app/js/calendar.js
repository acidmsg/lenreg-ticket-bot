/**
 * Ссылка на добавление записи в календарь.
 *
 * Кнопка «В календарь» открывает готовую форму события во внешнем календаре
 * (Google Calendar): название, время начала и конца, описание и место. Даты
 * передаются в формате Google (`YYYYMMDDTHHMMSS`) вместе с часовым поясом
 * `Europe/Moscow`, поэтому событие встаёт на то же местное время.
 *
 * @module calendar
 */

/** Длительность приёма по умолчанию (минуты): в данных расписания её нет. */
export const EVENT_DURATION_MINUTES = 60;

/** Часовой пояс, в котором приходит расписание из внешнего API. */
export const CALENDAR_TIMEZONE = "Europe/Moscow";

/**
 * Разбирает дату и время записи в объект `Date`.
 *
 * @param {string} date — дата в формате `ДД.ММ.ГГГГ`
 * @param {string} time — время в формате `ЧЧ:ММ`
 * @returns {Date|null} начало приёма или `null`, если формат не подходит
 */
export function parseBookingStart(date, time) {
  const dateMatch = /^(\d{2})\.(\d{2})\.(\d{4})$/.exec(
    String(date || "").trim(),
  );
  const timeMatch = /^(\d{1,2}):(\d{2})$/.exec(String(time || "").trim());
  if (!dateMatch || !timeMatch) return null;

  const day = Number(dateMatch[1]);
  const month = Number(dateMatch[2]);
  const year = Number(dateMatch[3]);
  const hours = Number(timeMatch[1]);
  const minutes = Number(timeMatch[2]);

  if (month < 1 || month > 12 || hours > 23 || minutes > 59) return null;

  const start = new Date(year, month - 1, day, hours, minutes, 0, 0);
  if (Number.isNaN(start.getTime())) return null;
  // Отсекаем «переехавшие» даты вроде 31.02.2027.
  if (start.getDate() !== day || start.getMonth() !== month - 1) return null;
  return start;
}

/**
 * Форматирует момент времени для Google Calendar.
 *
 * @param {Date} value — момент времени
 * @returns {string} строка вида `20261001T103000`
 */
function formatGoogleDate(value) {
  const pad = (num) => String(num).padStart(2, "0");
  return (
    String(value.getFullYear()) +
    pad(value.getMonth() + 1) +
    pad(value.getDate()) +
    "T" +
    pad(value.getHours()) +
    pad(value.getMinutes()) +
    "00"
  );
}

/**
 * Собирает ссылку на создание события в Google Calendar.
 *
 * @param {object} booking — данные записи
 * @param {string} booking.date — дата приёма `ДД.ММ.ГГГГ`
 * @param {string} booking.time — время приёма `ЧЧ:ММ`
 * @param {string} [booking.doctor_name] — ФИО врача
 * @param {string} [booking.clinic_name] — клиника
 * @param {string} [booking.patient_name] — пациент
 * @param {string} [booking.specialty] — специальность
 * @param {string} [booking.booking_id] — идентификатор записи
 * @returns {string|null} ссылка или `null`, если расписание не сохранено
 */
export function buildGoogleCalendarUrl(booking = {}) {
  const start = parseBookingStart(booking.date, booking.time);
  if (!start) return null;

  const end = new Date(start.getTime() + EVENT_DURATION_MINUTES * 60 * 1000);
  const doctor = booking.doctor_name || "";
  const title = doctor ? `Приём: ${doctor}` : "Приём у врача";
  const details = [
    booking.patient_name ? `Пациент: ${booking.patient_name}` : "",
    booking.clinic_name ? `Клиника: ${booking.clinic_name}` : "",
    booking.specialty ? `Специальность: ${booking.specialty}` : "",
    booking.booking_id ? `Номерок: ${booking.booking_id}` : "",
  ]
    .filter(Boolean)
    .join("\n");

  const params = new URLSearchParams({
    action: "TEMPLATE",
    text: title,
    dates: `${formatGoogleDate(start)}/${formatGoogleDate(end)}`,
    details,
    location: booking.clinic_name || "",
    ctz: CALENDAR_TIMEZONE,
  });
  return `https://calendar.google.com/calendar/render?${params.toString()}`;
}
