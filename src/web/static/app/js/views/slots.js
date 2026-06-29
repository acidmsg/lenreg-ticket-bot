/**
 * Экран просмотра свободных слотов для отслеживаемого врача.
 * Слоты группируются по датам.
 *
 * @module views/slots
 */

import { navigate } from "../app.js";
import { apiGet, apiPost, apiDelete } from "../api.js";
import { isInTelegram } from "../auth.js";
import { createSlotCard } from "../components/card.js";
import { escapeHtml } from "../utils/escape.js";
import { renderError } from "../utils/error.js";
import { refreshDoctorSlots } from "../utils/monitoring.js";
import { showConfirm } from "../utils/ui.js";
import { lucideIcon } from "../components/icon.js";

/**
 * Рендерит экран слотов в указанный контейнер.
 *
 * @param {HTMLElement} container — DOM-элемент для рендеринга
 * @param {object|null} params — параметры маршрута ({ monitoringId })
 */
export async function renderSlots(container, params) {
  if (!container) return;

  const monitoringId = params?.monitoringId;
  if (!monitoringId) {
    renderError(container, "Не указан ID отслеживания.", "Повторить", null);
    return;
  }

  // Показываем спиннер загрузки
  container.innerHTML = renderLoading();

  try {
    const data = await apiGet(
      `/slots?monitoring_id=${encodeURIComponent(monitoringId)}`,
    );

    // Собираем итоговый HTML: информация о враче + пациенты + слоты
    let html = renderSlotInfo(data, monitoringId);

    // Блок пациентов (пришёл через params из doctors.js)
    const patients = params?.patients;
    if (patients && patients.length > 0) {
      html += renderPatientsBlock(patients);
    }

    const slots = data.slots || [];
    if (slots.length === 0) {
      html += renderNoSlots();
    } else {
      html += renderSlotList(slots);
    }

    container.innerHTML = html;

    // Привязываем обработчики (удаление пациентов + кнопка обновления)
    bindSlotEvents(container, patients || [], params);
  } catch (error) {
    renderError(container, error.message, "Повторить", () =>
      renderSlots(container, params),
    );
  }
}

/**
 * Рендерит спиннер загрузки.
 *
 * @returns {string} HTML спиннера
 */
function renderLoading() {
  return `
    <div class="spinner">
      <div class="spinner__icon"></div>
    </div>
  `;
}

/**
 * Рендерит информационный блок о враче (заголовок экрана слотов).
 *
 * @param {object} data — данные ответа API
 * @returns {string} HTML информации
 */
function renderSlotInfo(data, monitoringId) {
  const doctorName = extractDoctorName(data) || "Врач";
  const specialty = data.specialty || "";
  const clinicName = data.clinic_name || "";
  const total = data.total || 0;

  return `
    <div class="mb-md">
      <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
        <span style="font-size: var(--font-lg); font-weight: 600;">
          ${escapeHtml(doctorName)}
        </span>
        <button
          class="btn--refresh"
          id="slots-refresh-btn"
          data-monitoring-id="${escapeHtml(monitoringId || "")}"
          title="Проверить номерки"
          aria-label="Принудительная проверка номерков"
        >${lucideIcon("refresh-cw", 20)}</button>
      </div>
      ${specialty ? `<div class="card__subtitle">${escapeHtml(specialty)}</div>` : ""}
      ${clinicName ? `<div class="card__meta"><span class="lucide-icon">${lucideIcon("hospital", 14)}</span> ${escapeHtml(clinicName)}</div>` : ""}
      ${total > 0 ? `<div class="status status--available mt-md"><span class="lucide-icon">${lucideIcon("circle-check", 14)}</span> Найдено номерков: ${total}</div>` : ""}
    </div>
  `;
}

/**
 * Рендерит сообщение об отсутствии слотов.
 *
 * @returns {string} HTML
 */
function renderNoSlots() {
  return `
    <div class="empty-state" style="padding-top: 20px;">
      <div class="empty-state__icon">${lucideIcon("calendar", 48)}</div>
      <p class="empty-state__text">
        На данный момент свободных номерков нет.
        Мы уведомим вас, когда они появятся.
      </p>
    </div>
  `;
}

/**
 * Рендерит список слотов, сгруппированных по датам.
 * Каждый слот — кликабельная кнопка с data-атрибутами для бронирования.
 *
 * @param {Array} slots — массив слотов [{ date, time, appointment_id, clinic_id }]
 * @returns {string} HTML списка слотов
 */
function renderSlotList(slots) {
  // Группируем слоты по дате (сохраняем полные данные слота)
  const grouped = {};
  slots.forEach((slot) => {
    const date = slot.date || "—";
    if (!grouped[date]) {
      grouped[date] = [];
    }
    grouped[date].push({
      time: slot.time || "—",
      appointmentId: slot.appointment_id || slot.slot_id || "",
    });
  });

  // Сортируем даты
  const sortedDates = Object.keys(grouped).sort();

  const groupsHtml = sortedDates
    .map((date) => createSlotCard({ date, slots: grouped[date] }))
    .join("");

  return `
    ${groupsHtml}
    <p class="text-center mt-md" style="color: var(--color-text-secondary); font-size: var(--font-sm);">
      Выберите удобное время для записи
    </p>
  `;
}

/**
 * Рендерит блок пациентов, отслеживающих врача.
 *
 * @param {Array<{name: string, patientId: string, entryId: string}>} patients — список пациентов
 * @returns {string} HTML блока пациентов
 */
function renderPatientsBlock(patients) {
  const patientsHtml = patients
    .map(
      (p) => `
      <li class="monitoring-patient">
        <span class="monitoring-patient__icon">${lucideIcon("user", 16)}</span>
        <span class="monitoring-patient__name">${escapeHtml(p.name)}</span>
        <button
          class="monitoring-patient__delete"
          data-entry-id="${escapeHtml(p.entryId)}"
          data-patient-name="${escapeHtml(p.name)}"
          title="Удалить мониторинг для этого пациента"
        >${lucideIcon("trash-2", 16)}</button>
      </li>`,
    )
    .join("");

  return `
    <div class="slots-patients">
      <div class="monitoring-patients__title"><span class="lucide-icon">${lucideIcon("users", 14)}</span> Пациенты:</div>
      <ul class="monitoring-patients">
        ${patientsHtml}
      </ul>
    </div>
  `;
}

/**
 * Асинхронный обработчик нажатия на кнопку принудительной проверки слотов.
 *
 * @param {HTMLElement} btn — кнопка refresh
 */
async function handleSlotRefresh(btn) {
  const monitoringId = btn.getAttribute("data-monitoring-id");
  if (!monitoringId) return;

  // Показываем анимацию загрузки
  btn.classList.add("btn--refresh--loading");

  try {
    const result = await refreshDoctorSlots(monitoringId);

    const total = result.total || 0;

    // Только toast-уведомление, без перерисовки слотов
    if (window.showToast) {
      if (total > 0) {
        window.showToast("Талоны найдены: " + total);
      } else {
        window.showToast("Талоны не найдены");
      }
    } else if (isInTelegram()) {
      // Fallback: toast-модуль ещё не загружен — используем Telegram alert
      window.Telegram.WebApp.showPopup({
        title: "Проверка номерков",
        message: total > 0 ? "Талоны найдены: " + total : "Талоны не найдены",
        buttons: [{ type: "ok" }],
      });
    }

    // Тактильный отклик
    if (window.Telegram?.WebApp?.HapticFeedback) {
      window.Telegram.WebApp.HapticFeedback.notificationOccurred("success");
    }
  } catch (error) {
    if (isInTelegram()) {
      window.Telegram.WebApp.showAlert(`Ошибка проверки: ${error.message}`);
    } else {
      alert(`Ошибка проверки: ${error.message}`);
    }
  } finally {
    btn.classList.remove("btn--refresh--loading");
  }
}

/**
 * Асинхронный обработчик нажатия на кнопку удаления пациента на экране слотов.
 *
 * @param {HTMLElement} btn — кнопка удаления
 * @param {HTMLElement} container — контейнер
 * @param {Array} patients — список пациентов (мутабельный)
 * @param {object} params — параметры маршрута
 */
async function handleSlotDeletePatient(btn, container, patients, params) {
  btn.blur(); // убираем :active/:focus после клика (мобильное залипание)
  const entryId = btn.getAttribute("data-entry-id");
  const patientName = btn.getAttribute("data-patient-name") || "этого пациента";

  // Тактильный отклик перед показом диалога
  if (window.Telegram?.WebApp?.HapticFeedback) {
    window.Telegram.WebApp.HapticFeedback.impactOccurred("medium");
  }

  const confirmed = await showConfirm(
    `Удалить мониторинг для пациента «${patientName}»?`,
  );

  if (!confirmed) return;

  try {
    await apiDelete(`/doctors/${encodeURIComponent(entryId)}`);

    if (isInTelegram()) {
      window.Telegram.WebApp.HapticFeedback.notificationOccurred("success");
    }

    // Удаляем пациента из списка и перерендериваем секцию
    const updatedPatients = patients.filter((p) => p.entryId !== entryId);
    const patientsBlock = container.querySelector(".slots-patients");
    if (patientsBlock) {
      if (updatedPatients.length === 0) {
        patientsBlock.remove();
      } else {
        patientsBlock.outerHTML = renderPatientsBlock(updatedPatients);
        // Обновляем массив patients в замыкании через перепривязку
        patients.length = 0;
        updatedPatients.forEach((p) => patients.push(p));
        bindSlotEvents(container, patients, params);
      }
    }
  } catch (error) {
    if (isInTelegram()) {
      window.Telegram.WebApp.showAlert(`Ошибка при удалении: ${error.message}`);
    } else {
      alert(`Ошибка при удалении: ${error.message}`);
    }
  }
}

/**
 * Привязывает обработчик кнопки принудительной проверки слотов.
 *
 * @param {HTMLElement} container — контейнер
 */
function bindSlotRefreshButtons(container) {
  const refreshBtn = container.querySelector("#slots-refresh-btn");
  if (refreshBtn) {
    refreshBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      handleSlotRefresh(refreshBtn);
    });
  }
}

/**
 * Привязывает обработчики кнопок удаления пациентов на экране слотов.
 *
 * @param {HTMLElement} container — контейнер
 * @param {Array} patients — список пациентов
 * @param {object} params — параметры маршрута
 */
function bindSlotDeletePatientButtons(container, patients, params) {
  container.querySelectorAll(".monitoring-patient__delete").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      handleSlotDeletePatient(btn, container, patients, params);
    });
  });
}

/**
 * Привязывает обработчики событий на экране слотов.
 *
 * @param {HTMLElement} container — контейнер
 * @param {Array} patients — список пациентов
 * @param {object} params — параметры маршрута
 */
function bindSlotEvents(container, patients, params) {
  bindSlotRefreshButtons(container);
  bindSlotDeletePatientButtons(container, patients, params);
  bindSlotChipClicks(container, params);
}

/**
 * Привязывает обработчики кликов по кнопкам слотов (бронирование).
 *
 * @param {HTMLElement} container — контейнер
 * @param {object} params — параметры маршрута ({ monitoringId, patients })
 */
function bindSlotChipClicks(container, params) {
  container.querySelectorAll(".slot-chip--clickable").forEach((chip) => {
    chip.addEventListener("click", (e) => {
      e.stopPropagation();
      handleSlotBooking(chip, params);
    });
  });
}

/**
 * Обрабатывает клик по слоту: показывает подтверждение и выполняет бронирование.
 *
 * @param {HTMLElement} chip — кнопка слота
 * @param {object} params — параметры маршрута
 */
async function handleSlotBooking(chip, params) {
  const date = chip.getAttribute("data-slot-date") || "";
  const time = chip.getAttribute("data-slot-time") || "";
  const appointmentId = chip.getAttribute("data-appointment-id") || "";
  const clinicId = chip.getAttribute("data-clinic-id") || "";

  if (!appointmentId) {
    if (window.showToast) {
      window.showToast("❌ Невозможно определить слот для записи", "error");
    }
    return;
  }

  // Извлекаем patient_id из monitoringId
  const monitoringId = params?.monitoringId || "";
  const parts = monitoringId.split("_");
  const patientId = parts.length >= 1 ? parts[0] : "";

  if (!patientId || !clinicId) {
    if (window.showToast) {
      window.showToast("❌ Недостаточно данных для записи", "error");
    }
    return;
  }

  // Имя врача — из ответа API slots (сохраняется в params при навигации)
  const doctorName = params?.doctorName || "врачу";

  // Показываем подтверждение
  const confirmed = await showBookingConfirm(doctorName, date, time);

  if (!confirmed) return;

  // Тактильный отклик
  if (window.Telegram?.WebApp?.HapticFeedback) {
    window.Telegram.WebApp.HapticFeedback.impactOccurred("medium");
  }

  // Выполняем бронирование
  try {
    const result = await apiPost("/book", {
      clinic_id: clinicId,
      patient_id: patientId,
      appointment_id: appointmentId,
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
      // Возвращаемся на главную
      navigate("doctors");
    } else {
      const errorCode = result.error || "unknown";
      const detail = result.detail || "Неизвестная ошибка";
      handleBookingError(errorCode, detail);
    }
  } catch (error) {
    handleBookingError("network", error.message);
  }
}

/**
 * Показывает модальное окно подтверждения записи.
 *
 * @param {string} doctorName — имя врача
 * @param {string} date — дата приёма
 * @param {string} time — время приёма
 * @returns {Promise<boolean>} подтверждено или нет
 */
async function showBookingConfirm(doctorName, date, time) {
  const message = `Записаться к ${doctorName} на ${date} в ${time}?`;

  if (window.Telegram?.WebApp?.showPopup) {
    return new Promise((resolve) => {
      window.Telegram.WebApp.showPopup(
        {
          title: "Подтверждение записи",
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

  return window.confirm(message);
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
 * Извлекает строковое имя врача из поля name, которое может быть объектом.
 *
 * NOTE: Локальная версия отличается от utils/doctor.js (Фаза 2, Шаг 4).
 * utils/doctor.js принимает name напрямую + fallback-параметр.
 * Здесь принимается doctor-объект, извлекается doctor.name,
 * fallback — doctor.doctor_name. Унификация требует изменения сигнатур вызовов.
 *
 * @param {object} doctor — объект врача из API
 * @returns {string} строковое представление имени врача
 */
function extractDoctorName(doctor) {
  const name = doctor.name;
  if (!name) return String(doctor.doctor_name || "");

  // Если name — строка, возвращаем как есть
  if (typeof name === "string") return name;

  // Если name — объект (например, {first_name: "...", last_name: "..."}),
  // пробуем собрать строку из известных полей
  if (typeof name === "object" && name !== null) {
    const parts = [];
    if (name.last_name) parts.push(name.last_name);
    if (name.first_name) parts.push(name.first_name);
    if (name.middle_name) parts.push(name.middle_name);
    if (parts.length > 0) return parts.join(" ");
    // Если не удалось извлечь — используем doctor_name как fallback
    return String(doctor.doctor_name || name);
  }

  return String(name);
}
