/**
 * Единая точка запроса свободных слотов Mini App.
 *
 * Два режима контракта `GET /api/user/slots` (openapi 1.5.0):
 * - `monitoringId` — врач из мониторинга пользователя;
 * - тройка `clinicId` + `doctorId` + `patientId` — прямая запись без мониторинга.
 *
 * Модуль не рендерит и не бронирует: только запрос данных, чтобы сценарии
 * (экран слотов, шаг мастера, карточка врача) не дублировали сборку URL.
 *
 * @module utils/slots-api
 */

import { apiGet } from "../api.js";

/**
 * Запрашивает свободные слоты врача.
 *
 * @param {object} options — параметры запроса
 * @param {string} [options.monitoringId=""] — ID мониторинга `{patient_id}_{doctor_id}`
 * @param {string} [options.clinicId=""] — ID клиники (режим прямой записи)
 * @param {string} [options.doctorId=""] — ID врача (режим прямой записи)
 * @param {string} [options.patientId=""] — ID пациента (режим прямой записи)
 * @returns {Promise<object>} ответ API: `{ monitoring_id, doctor_name, specialty, clinic_name, slots, total }`
 * @throws {Error} если не задан ни один из режимов либо API ответил ошибкой
 */
export async function fetchSlots({
  monitoringId = "",
  clinicId = "",
  doctorId = "",
  patientId = "",
} = {}) {
  if (monitoringId) {
    return await apiGet(
      `/slots?monitoring_id=${encodeURIComponent(monitoringId)}`,
    );
  }

  if (clinicId && doctorId && patientId) {
    const query = new URLSearchParams({
      clinic_id: clinicId,
      doctor_id: doctorId,
      patient_id: patientId,
    });
    return await apiGet(`/slots?${query.toString()}`);
  }

  throw new Error("Недостаточно данных для запроса номерков.");
}
