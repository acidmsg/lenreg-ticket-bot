/**
 * Экран просмотра свободных слотов для отслеживаемого врача.
 * Слоты группируются по датам.
 *
 * @module views/slots
 */

import { navigate } from "../app.js";
import { apiDelete } from "../api.js";
import { isInTelegram } from "../auth.js";
import {
  bindSlotsPickerChips,
  initSlotsPicker,
  renderSlotList,
  renderSlotsPickerLayout,
} from "../components/slots-picker.js";
import { escapeHtml } from "../utils/escape.js";
import {
  isServiceUnavailableError,
  renderError,
  SERVICE_UNAVAILABLE_MESSAGE,
} from "../utils/error.js";
import { refreshDoctorSlots } from "../utils/monitoring.js";
import { fetchSlots } from "../utils/slots-api.js";
import { bookSlot } from "../utils/booking.js";

// Реэкспорт для существующих потребителей (тесты и внешние импорты).
export {
  buildBookingConfirmMessage,
  showBookingConfirm,
} from "../utils/booking.js";
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

  const monitoringId = params?.monitoringId || "";
  const direct = params?.direct || null;
  if (!monitoringId && !direct) {
    renderError(container, "Не указан ID отслеживания.", "Повторить", null);
    return;
  }

  // Показываем спиннер загрузки
  container.innerHTML = renderLoading();

  try {
    // Режим мониторинга — по monitoringId; прямой режим — по тройке
    // clinic_id + doctor_id + patient_id (openapi 1.5.0, без мониторинга).
    const data = await fetchSlots(
      monitoringId ? { monitoringId } : { ...direct },
    );

    // §11.5: источник истины для карточки подтверждения — ответ
    // GET /api/user/slots, привязанный к monitoringId. Поля сохраняются
    // в params, который живёт в замыкании обработчиков чипов.
    saveBookingData(params, data);

    // Собираем итоговый HTML: информация о враче + пациенты + слоты
    let html = renderSlotInfo(data, monitoringId);

    // Блок пациентов (пришёл через params из doctors.js)
    const patients = params?.patients;
    if (patients && patients.length > 0) {
      html += renderPatientsBlock(patients, monitoringId);
    }

    const slots = data.slots || [];
    if (slots.length === 0) {
      html += renderNoSlots();
    } else {
      html += renderSlotsPickerLayout();
    }

    container.innerHTML = html;

    // Привязываем обработчики (удаление пациентов + кнопка обновления)
    bindSlotEvents(container, patients || [], params);

    // Гибридный режим: календарь слотов + панель выбранной даты.
    // При недоступности VanillaCalendar — откат к плоскому списку.
    if (slots.length > 0) {
      const onSelect = (slot) => handleSlotBooking(slot, params);
      const calendarReady = initSlotsPicker(container, {
        slots,
        onSelect,
        fallbackClinicId: data.clinic_id || "",
      });
      if (!calendarReady) {
        const layout = container.querySelector(".slots-layout");
        if (layout) {
          layout.outerHTML = renderSlotList(slots, data.clinic_id || "");
        }
        bindSlotsPickerChips(container, onSelect);
      }
    }
  } catch (error) {
    // 502/504 — внешний сервис клиники недоступен: показываем единое понятное
    // сообщение вместо «нет номерков» и вместо технических деталей ответа.
    const message = isServiceUnavailableError(error)
      ? SERVICE_UNAVAILABLE_MESSAGE
      : error.message;
    renderError(container, message, "Повторить", () =>
      renderSlots(container, params),
    );
  }
}

/**
 * Сохраняет в params данные врача и клиники из ответа слотов (§11.5).
 *
 * Дублирование этих полей в `navigate("slots", …)` не требуется: ответ
 * `GET /api/user/slots` уже содержит `doctor_name`, `specialty`, `clinic_name`.
 *
 * @param {object} params — параметры маршрута (мутируются)
 * @param {object} data — ответ `GET /api/user/slots`
 */
function saveBookingData(params, data) {
  params.doctorName = extractDoctorName(data);
  params.specialty = data.specialty || "";
  params.clinicName = data.clinic_name || "";
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
 * Рендерит блок пациентов, отслеживающих врача.
 *
 * @param {Array<{name: string, patientId: string, entryId: string}>} patients — список пациентов
 * @returns {string} HTML блока пациентов
 */
function renderPatientsBlock(patients, monitoringId = "") {
  const patientsHtml = patients
    .map((p) => {
      const active = p.entryId && p.entryId === monitoringId;
      return `
      <li class="monitoring-patient${active ? " monitoring-patient--active" : ""}">
        <span class="monitoring-patient__icon">${lucideIcon("user", 16)}</span>
        <button
          class="monitoring-patient__switch"
          data-entry-id="${escapeHtml(p.entryId)}"
          data-patient-name="${escapeHtml(p.name)}"
          aria-pressed="${active ? "true" : "false"}"
          title="Записаться на этого пациента"
        >${escapeHtml(p.name)}</button>
        <button
          class="monitoring-patient__delete"
          data-entry-id="${escapeHtml(p.entryId)}"
          data-patient-name="${escapeHtml(p.name)}"
          title="Удалить мониторинг для этого пациента"
        >${lucideIcon("trash-2", 16)}</button>
      </li>`;
    })
    .join("");

  return `
    <div class="slots-patients">
      <div class="monitoring-patients__title"><span class="lucide-icon">${lucideIcon("users", 14)}</span> Пациенты — выберите, на кого записывать:</div>
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
        patientsBlock.outerHTML = renderPatientsBlock(
          updatedPatients,
          params?.monitoringId,
        );
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
 * Привязывает выбор пациента на экране номерков.
 *
 * Кнопка имени пациента переключает, на кого будет оформлена запись.
 *
 * @param {HTMLElement} container — контейнер
 * @param {Array} patients — список пациентов
 * @param {object} params — параметры маршрута
 */
function bindPatientSwitches(container, patients, params) {
  container.querySelectorAll(".monitoring-patient__switch").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      handlePatientSwitch(btn, container, params);
    });
  });
}

/**
 * Переключает пациента, на которого будет оформлена запись.
 *
 * Номерки пациент-зависимы (`monitoring_id` = `{patient_id}_{doctor_id}`), поэтому
 * смена пациента сразу перезапрашивает экран: список слотов и карточка
 * подтверждения соответствуют выбранному пациенту, а `patient_id` в
 * `POST /book` берётся из тех же параметров маршрута.
 *
 * @param {HTMLElement} btn — кнопка пациента
 * @param {HTMLElement} container — контейнер экрана
 * @param {object} params — параметры маршрута
 */
async function handlePatientSwitch(btn, container, params) {
  btn.blur(); // убираем :active/:focus после клика (мобильное залипание)
  const entryId = btn.getAttribute("data-entry-id");
  if (!entryId) return;

  const direct = params?.direct;
  if (entryId === params?.monitoringId) return; // уже выбран — ничего не делаем

  if (window.Telegram?.WebApp?.HapticFeedback) {
    window.Telegram.WebApp.HapticFeedback.selectionChanged?.();
  }

  const nextParams = direct
    ? { ...params, direct: { ...direct, patientId: entryId.split("_", 1)[0] } }
    : { ...params, monitoringId: entryId };

  await renderSlots(container, nextParams);
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
  bindPatientSwitches(container, patients, params);
  bindSlotsPickerChips(container, (slot) => handleSlotBooking(slot, params));
}

/**
 * Разбирает `monitoringId` вида `{p_id}_{d_id}` на компоненты.
 *
 * @param {string} monitoringId — ID мониторинга пары пациент + врач
 * @returns {{patientId: string, doctorId: string}} `p_id` и `d_id` (пустые строки, если не найдены)
 */
function parseMonitoringId(monitoringId) {
  const parts = String(monitoringId || "").split("_");
  return {
    patientId: parts[0] || "",
    doctorId: parts[1] || "",
  };
}

/**
 * Обрабатывает клик по слоту: показывает подтверждение и выполняет бронирование.
 *
 * Врач определяется по `params.monitoringId` (`{p_id}_{d_id}`): `GET /api/user/slots`
 * не возвращает `doctor_id`, поэтому слоты привязаны к паре пациент + врач.
 *
 * @param {HTMLElement} chip — кнопка слота
 * @param {object} params — параметры маршрута
 */
async function handleSlotBooking(slot, params) {
  // patient_id и doctor_id — компоненты monitoringId; врач обязателен
  // в контракте POST /book, иначе бэкенд подберёт «первого врача клиники».
  const monitoringId = params?.monitoringId || "";
  const { patientId, doctorId } = parseMonitoringId(monitoringId);

  // Карточка подтверждения (§11.5) и сама запись — в общем модуле
  // `utils/booking.js`: тот же путь, что и у шага подтверждения мастера.
  const result = await bookSlot({
    date: slot?.date || "",
    time: slot?.time || "",
    appointmentId: slot?.appointmentId || "",
    clinicId: slot?.clinicId || "",
    patientId,
    doctorId,
    patientName: findPatientName(params?.patients, monitoringId, patientId),
    doctorName: params?.doctorName || "",
    specialty: params?.specialty || "",
    clinicName: params?.clinicName || "",
    monitoringId,
  });

  if (result.success) {
    // Возвращаемся на главную
    navigate("doctors");
    return;
  }

  // Отмена и нехватка данных — сообщение уже показано, обновлять нечего.
  if (result.error === "cancelled" || result.error === "invalid_data") return;

  // Мёртвого экрана нет: остаёмся на слотах и обновляем список,
  // чтобы занятый талон не висел в UI.
  await refreshSlotsAfterBookingError(params);
}

/**
 * Обновляет список слотов после отказа бронирования.
 *
 * Пользователь остаётся на экране слотов (никакой навигации), но список
 * перезапрашивается: талон, который уже заняли, исчезает из UI, а не остаётся
 * мёртвой кнопкой. Ошибка обновления не пробрасывается — сообщение об отказе
 * уже показано.
 *
 * @param {object} params — параметры маршрута
 */
async function refreshSlotsAfterBookingError(params) {
  const container = document.getElementById("slots-content");
  if (!container) return;
  try {
    await renderSlots(container, params);
  } catch {
    // Список не обновился — сообщение об ошибке уже показано.
  }
}

/**
 * Находит имя пациента для карточки подтверждения.
 *
 * Основной ключ — `entryId === monitoringId` (§11.5): `monitoring_id` имеет
 * формат `{p_id}_{d_id}` и совпадает с `entryId` пациента. Фолбэк —
 * сравнение `patientId` с `p_id`, извлечённым из `monitoringId`. Если
 * пациент не найден, возвращается пустая строка: строка пациента в карточке
 * не выводится, данные не подменяются.
 *
 * @param {Array<{name: string, patientId: string, entryId: string}>} patients — пациенты
 * @param {string} monitoringId — ID мониторинга вида `{p_id}_{d_id}`
 * @param {string} patientId — `p_id`, извлечённый из `monitoringId`
 * @returns {string} имя пациента или пустая строка
 */
function findPatientName(patients, monitoringId, patientId) {
  const entries = patients || [];
  const patient =
    entries.find((entry) => entry.entryId === monitoringId) ||
    entries.find((entry) => entry.patientId === patientId);
  return patient?.name || "";
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
