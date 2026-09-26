/**
 * Общее оформление записи к врачу для Mini App.
 *
 * Один путь для всех экранов, откуда можно записаться: экран номерков
 * (`views/slots.js`) и шаг подтверждения мастера (`views/add.js`). Модуль
 * показывает карточку подтверждения, выполняет `POST /api/user/book`,
 * одинаково обрабатывает ошибки и инвалидирует кэш мониторинга.
 *
 * Модуль не знает про маршрутизацию: куда идти после успеха, решает вызывающий.
 *
 * @module utils/booking
 */

import { apiPost } from "../api.js";
import { refreshDoctorSlots } from "./monitoring.js";
import { escapeHtml } from "./escape.js";

/** Формат времени слота, ожидаемый контрактом `POST /book` (ЧЧ:ММ). */
export const SLOT_TIME_PATTERN = /^\d{2}:\d{2}$/;

/**
 * Преобразует дату слота из формата `ДД.ММ.ГГГГ` в ISO `ГГГГ-ММ-ДД`.
 *
 * Значение, которое не удалось разобрать, возвращается как есть (пустая
 * строка), чтобы вызывающий код отклонил запись до обращения к API.
 *
 * @param {string} value — дата в формате `ДД.ММ.ГГГГ`
 * @returns {string} дата в формате `ГГГГ-ММ-ДД` либо исходное/пустое значение
 */
export function toIsoSlotDate(value) {
  const parts = String(value || "").split(".");
  if (parts.length !== 3) return value || "";
  if (!parts.every((part) => /^\d+$/.test(part))) return "";
  const [day, month, year] = parts;
  return `${year.padStart(4, "0")}-${month.padStart(2, "0")}-${day.padStart(2, "0")}`;
}

/**
 * Собирает текст карточки подтверждения записи (§11.5).
 *
 * Порядок строк совпадает с ботом (§11.2). Строки с пустым значением
 * отбрасываются вместе с эмодзи. Значения экранируются: popup Mini App
 * рендерит HTML.
 *
 * Ключи-паритеты локализации (каталоги `locales/ru` и `locales/en`):
 * `booking-confirm-popup-doctor`, `booking-confirm-popup-specialty`,
 * `booking-confirm-popup-clinic`, `booking-confirm-popup-datetime`,
 * `booking-confirm-popup-patient`, `booking-confirm-popup-question`.
 *
 * @param {object} booking — данные записи
 * @param {string} booking.doctor — врач
 * @param {string} booking.specialty — специальность (может быть пустой)
 * @param {string} booking.clinic — клиника (может быть пустой)
 * @param {string} booking.date — дата приёма (`ДД.ММ.ГГГГ`)
 * @param {string} booking.time — время приёма (`ЧЧ:ММ`)
 * @param {string} booking.patient — пациент (может быть пустой)
 * @returns {string} текст карточки с вопросом подтверждения
 */
export function buildBookingConfirmMessage(booking) {
  const rows = [
    booking.doctor ? `🧑‍⚕️ ${escapeHtml(booking.doctor)}` : "",
    booking.specialty ? `📋 ${escapeHtml(booking.specialty)}` : "",
    booking.clinic ? `🏥 ${escapeHtml(booking.clinic)}` : "",
    booking.date
      ? `📅 ${escapeHtml(booking.date)} в ${escapeHtml(booking.time)}`
      : "",
    booking.patient ? `👤 Пациент: ${escapeHtml(booking.patient)}` : "",
  ];

  const card = rows.filter((row) => row !== "").join("\n");

  // ❓ Записаться? — ключ-паритет booking-confirm-popup-question
  return `${card}\n\n❓ Записаться?`;
}

/**
 * Показывает модальное окно подтверждения записи.
 *
 * Текст собирается один раз (§Ⅰ модульность) и используется в обеих ветках:
 * `Telegram.WebApp.showPopup` и `window.confirm`.
 *
 * @param {object} booking — данные записи ({ doctor, specialty, clinic, date, time, patient })
 * @returns {Promise<boolean>} подтверждено или нет
 */
export async function showBookingConfirm(booking) {
  // Заголовок — ключ-паритет booking-confirm-popup-title,
  // кнопки — существующие btn-booking-confirm / btn-booking-back.
  const title = "Подтверждение записи";
  const message = buildBookingConfirmMessage(booking);

  if (window.Telegram?.WebApp?.showPopup) {
    return new Promise((resolve) => {
      window.Telegram.WebApp.showPopup(
        {
          title: title,
          message: message,
          buttons: [
            { id: "confirm", type: "default", text: "✅ Подтвердить" },
            { id: "back", type: "cancel", text: "↩ Назад" },
          ],
        },
        (buttonId) => {
          resolve(buttonId === "confirm");
        },
      );
    });
  }

  return window.confirm(`${title}\n\n${message}`);
}

/**
 * Обрабатывает ошибку бронирования: показывает toast с понятным сообщением.
 *
 * @param {string} errorCode — код ошибки (slot_taken, api_unavailable, ...)
 * @param {string} detail — детальное описание
 */
function handleBookingError(errorCode, detail) {
  if (window.Telegram?.WebApp?.HapticFeedback) {
    window.Telegram.WebApp.HapticFeedback.notificationOccurred("error");
  }

  let message;
  switch (errorCode) {
    case "slot_taken":
      message = "❌ Этот талон уже занят. Выберите другое время.";
      break;
    case "api_unavailable":
      message = "❌ Сервер записи временно недоступен. Попробуйте позже.";
      break;
    case "api_timeout":
      message = "❌ Сервер не отвечает. Попробуйте позже.";
      break;
    case "forbidden":
      message = "❌ Доступ запрещён. Попробуйте позже.";
      break;
    default:
      message = `❌ Ошибка записи: ${detail || "попробуйте позже"}`;
      break;
  }

  if (window.showToast) {
    window.showToast(message, "error");
  } else if (window.Telegram?.WebApp?.showAlert) {
    window.Telegram.WebApp.showAlert(message);
  } else {
    alert(message);
  }
}

/**
 * Показывает подтверждение и выполняет запись к врачу.
 *
 * Единая точка для экрана номерков и шага подтверждения мастера: валидация
 * данных, карточка подтверждения, `POST /book`, разбор ошибок и инвалидация
 * кэша мониторинга (best-effort — неудача инвалидации не отменяет запись).
 *
 * @param {object} params — данные записи
 * @param {string} params.date — дата слота (`ДД.ММ.ГГГГ`)
 * @param {string} params.time — время слота (`ЧЧ:ММ`)
 * @param {string} params.appointmentId — ID слота (`appointment_id`)
 * @param {string} params.clinicId — ID клиники
 * @param {string} params.patientId — ID пациента
 * @param {string} params.doctorId — ID врача
 * @param {string} [params.patientName=""] — имя пациента для карточки подтверждения
 * @param {string} [params.doctorName=""] — врач
 * @param {string} [params.specialty=""] — специальность
 * @param {string} [params.clinicName=""] — клиника
 * @param {string} [params.monitoringId=""] — ID мониторинга для инвалидации кэша
 * @returns {Promise<{success: boolean, error?: string, detail?: string}>}
 *   `success: true` — талон забронирован; `error: "cancelled"` — пользователь
 *   отказался на подтверждении; `error: "invalid_data"` — данных не хватило.
 */
export async function bookSlot({
  date = "",
  time = "",
  appointmentId = "",
  clinicId = "",
  patientId = "",
  doctorId = "",
  patientName = "",
  doctorName = "",
  specialty = "",
  clinicName = "",
  monitoringId = "",
} = {}) {
  const slotDate = toIsoSlotDate(date);

  if (
    !appointmentId ||
    !clinicId ||
    !patientId ||
    !doctorId ||
    !slotDate ||
    !SLOT_TIME_PATTERN.test(time)
  ) {
    if (window.showToast) {
      window.showToast("❌ Недостаточно данных для записи", "error");
    }
    return { success: false, error: "invalid_data" };
  }

  // Карточка подтверждения (§11.5): врач, специальность, клиника и пациент.
  const booking = {
    doctor: doctorName,
    specialty,
    clinic: clinicName,
    date,
    time,
    patient: patientName,
  };

  const confirmed = await showBookingConfirm(booking);
  if (!confirmed) return { success: false, error: "cancelled" };

  // Тактильный отклик
  if (window.Telegram?.WebApp?.HapticFeedback) {
    window.Telegram.WebApp.HapticFeedback.impactOccurred("medium");
  }

  try {
    const result = await apiPost("/book", {
      clinic_id: clinicId,
      patient_id: patientId,
      doctor_id: doctorId,
      appointment_id: appointmentId,
      slot_date: slotDate,
      slot_time: time,
      history_id: "",
      referral_id: "",
    });

    if (result.success) {
      if (window.Telegram?.WebApp?.HapticFeedback) {
        window.Telegram.WebApp.HapticFeedback.notificationOccurred("success");
      }
      if (window.showToast) {
        window.showToast("✅ Вы успешно записаны!", "success");
      }
      // Инвалидация кэша слотов: забронированный талон не должен висеть в UI.
      if (monitoringId) {
        try {
          await refreshDoctorSlots(monitoringId);
        } catch {
          // Неудача инвалидации не отменяет успешную запись.
        }
      }
      return { success: true };
    }

    const errorCode = result.error || "unknown";
    const detail = result.detail || "Неизвестная ошибка";
    handleBookingError(errorCode, detail);
    return { success: false, error: errorCode, detail };
  } catch (error) {
    handleBookingError("network", error.message);
    return { success: false, error: "network", detail: error.message };
  }
}
