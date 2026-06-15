/**
 * Утилиты мониторинга — запросы проверки слотов и обновления.
 * Используется в doctors.js и slots.js для refresh-проверок.
 */

import { apiPost } from '../api.js';

/**
 * Проверить слоты врача — POST /doctors/check.
 * @param {string|number} monitoringId
 * @returns {Promise<object>} { found: number, total: number, last_checked: string }
 */
export async function checkDoctorSlots(monitoringId) {
  const data = await apiPost('/doctors/check', {
    monitoring_id: Number(monitoringId)
  });
  return data;
}

/**
 * Обработчик refresh-проверки слотов врача.
 * Используется в doctors.js и slots.js для унификации API-вызова.
 * DOM-обновление и toast остаются в views.
 *
 * @param {string|number} monitoringId
 * @returns {Promise<{found: number, total: number, last_checked: string}>}
 */
export async function refreshDoctorSlots(monitoringId) {
  return await checkDoctorSlots(monitoringId);
}
