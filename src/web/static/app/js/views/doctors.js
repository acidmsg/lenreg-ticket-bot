/**
 * Экран списка отслеживаемых врачей (главный экран).
 * Отображает список врачей со статусом слотов.
 *
 * @module views/doctors
 */

import { apiGet, apiDelete } from "../api.js";
import { isInTelegram } from "../auth.js";
import { createDoctorCard } from "../components/card.js";
import { openFilterModal } from "../components/filter-modal.js";
import { renderError } from "../utils/error.js";
import { refreshDoctorSlots } from "../utils/monitoring.js";
import { startPolling } from "../utils/polling.js";
import { showMainButton } from "../utils/telegram-buttons.js";
import { showConfirm } from "../utils/ui.js";
import { lucideIcon } from "../components/icon.js";
import { navigate } from "../app.js";

/** Базовый интервал автообновления главного экрана, мс. */
const AUTO_REFRESH_INTERVAL_MS = 45000;

/**
 * Рендерит главный экран в указанный контейнер.
 *
 * @param {HTMLElement} container — DOM-элемент для рендеринга
 */
/**
 * Загружает врачей и количество активных записей для сводки.
 *
 * @returns {Promise<{doctors: Array, bookingsCount: number}>}
 */
async function loadHomeData() {
  const [doctorsData, bookingsData] = await Promise.all([
    apiGet("/doctors"),
    apiGet("/bookings").catch(() => ({ bookings: [] })),
  ]);
  const doctors = doctorsData.doctors || [];

  const clinicIds = [
    ...new Set(doctors.map((d) => d.clinic_id).filter(Boolean)),
  ];
  const availableData = await Promise.all(
    clinicIds.map((clinicId) =>
      apiGet(
        `/doctors/available?clinic_id=${encodeURIComponent(clinicId)}`,
      ).catch(() => ({ doctors: [] })),
    ),
  );
  const nearestByDoctor = {};
  for (const response of availableData) {
    for (const doctor of response.doctors || []) {
      if (doctor.doctor_id && doctor.nearest_date) {
        nearestByDoctor[doctor.doctor_id] = {
          date: doctor.nearest_date || "",
          time: doctor.nearest_time || "",
        };
      }
    }
  }

  return {
    doctors,
    bookingsCount: (bookingsData?.bookings || []).length,
    nearestByDoctor,
  };
}

export async function renderDoctors(container) {
  if (!container) return;

  // Системная кнопка добавления врача на главном экране.
  showMainButton({
    text: "Отслеживать врача",
    onClick: () => navigate("add"),
  });

  // Показываем скелетон загрузки
  container.innerHTML = renderSkeletons();

  try {
    const { doctors, bookingsCount, nearestByDoctor } = await loadHomeData();

    if (doctors.length === 0) {
      container.innerHTML = renderEmpty();
      bindEmptyEvents(container);
      return;
    }

    container.innerHTML = renderDoctorList(
      doctors,
      bookingsCount,
      nearestByDoctor,
    );
    container.dataset.signature = listSignature(
      doctors,
      bookingsCount,
      nearestByDoctor,
    );
    updateCheckedLabels(container, new Date());
    bindDoctorEvents(container, doctors);

    // Автообновление из состояния БД: сеть дёргается по расписанию,
    // очистка поллера — на роутере при смене экрана (stopAllPollers).
    startPolling(() => refreshDoctorList(container), {
      intervalMs: AUTO_REFRESH_INTERVAL_MS,
    });
  } catch (error) {
    renderError(container, error.message, "Повторить", () =>
      renderDoctors(container),
    );
  }
}

/**
 * Перезапрашивает состояние мониторинга и обновляет список без перезахода.
 *
 * Данные берутся из БД/Redis через сервер (`GET /doctors`) — внешние вызовы
 * zdrav в поллинге не выполняются. DOM перерисовывается только при изменении
 * состояния; метки времени обновляются всегда.
 *
 * @param {HTMLElement} container — контейнер списка
 */
async function refreshDoctorList(container) {
  if (!container || !container.isConnected) return;

  const { doctors, bookingsCount, nearestByDoctor } = await loadHomeData();

  if (doctors.length === 0) {
    if (container.dataset.signature !== "") {
      container.innerHTML = renderEmpty();
      container.dataset.signature = "";
      bindEmptyEvents(container);
    }
    return;
  }

  const signature = listSignature(doctors, bookingsCount, nearestByDoctor);
  if (signature !== container.dataset.signature) {
    container.innerHTML = renderDoctorList(
      doctors,
      bookingsCount,
      nearestByDoctor,
    );
    container.dataset.signature = signature;
    bindDoctorEvents(container, doctors);
  }
  updateCheckedLabels(container, new Date());
}

/**
 * Строит подпись состояния списка — сравнение вместо лишней перерисовки.
 *
 * @param {Array} doctors — массив врачей из API
 * @returns {string} подпись состояния
 */
function listSignature(doctors, bookingsCount = 0, nearestByDoctor = {}) {
  return JSON.stringify({ doctors, bookingsCount, nearestByDoctor });
}

/**
 * Обновляет метки времени последней проверки в карточках врачей.
 *
 * @param {HTMLElement} container — контейнер списка
 * @param {Date} date — время успешного обновления
 */
function updateCheckedLabels(container, date) {
  const label = formatCheckedTime(date);
  container.querySelectorAll(".doctor-card__checked").forEach((el) => {
    el.textContent = label;
  });
}

/**
 * Форматирует время проверки компактно (ЧЧ:ММ).
 *
 * @param {Date} date — время проверки
 * @returns {string} время в формате ЧЧ:ММ
 */
export function formatCheckedTime(date) {
  const hh = String(date.getHours()).padStart(2, "0");
  const mm = String(date.getMinutes()).padStart(2, "0");
  return `${hh}:${mm}`;
}

/**
 * Рендерит скелетоны загрузки (3 карточки).
 *
 * @returns {string} HTML скелетонов
 */
function renderSkeletons() {
  let html = "";
  for (let i = 0; i < 3; i++) {
    html += `
      <div class="card skeleton--card">
        <div class="skeleton skeleton--title"></div>
        <div class="skeleton skeleton--text" style="width: 40%;"></div>
        <div class="skeleton skeleton--text" style="width: 70%;"></div>
        <div style="display: flex; gap: 8px; margin-top: 12px;">
          <div class="skeleton skeleton--chip"></div>
          <div class="skeleton skeleton--chip"></div>
        </div>
      </div>
    `;
  }
  return html;
}

/**
 * Рендерит пустое состояние.
 *
 * @returns {string} HTML пустого состояния
 */
function renderEmpty() {
  return `
    <div class="empty-state">
      <div class="empty-state__icon">${lucideIcon("stethoscope", 48)}</div>
      <p class="empty-state__text">
        Вы пока не отслеживаете ни одного врача.
        Добавьте первый мониторинг, чтобы получать уведомления о появлении свободных номерков.
      </p>
      <button class="btn btn--primary" id="empty-add-btn"><span class="lucide-icon">${lucideIcon("circle-plus", 16)}</span> Поиск врача</button>
    </div>
  `;
}

/**
 * Рендерит список карточек врачей, сгруппированных по doctor_id.
 *
 * @param {Array} doctors — массив врачей из API
 * @returns {string} HTML списка врачей
 */
function renderDoctorList(doctors, bookingsCount = 0, nearestByDoctor = {}) {
  // Группировка по doctor_id
  const grouped = {};
  doctors.forEach((doctor) => {
    if (!grouped[doctor.doctor_id]) {
      grouped[doctor.doctor_id] = {
        doctorName: extractDoctorName(doctor) || "Неизвестный врач",
        specialty: doctor.specialty || "—",
        clinicName: doctor.clinic_name || "—",
        status: doctor.status || "checking",
        freeTickets: doctor.free_tickets || 0,
        // Карточка строится на первого пациента в группе (как monitoringId),
        // поэтому фильтр и счётчик «под фильтр» тоже берутся у первого (§7.3).
        matchingFreeTickets: doctor.matching_free_tickets || 0,
        filter: doctor.filter || null,
        nearestDate: nearestByDoctor[doctor.doctor_id]?.date || "",
        nearestTime: nearestByDoctor[doctor.doctor_id]?.time || "",
        patients: [],
      };
    }
    grouped[doctor.doctor_id].patients.push({
      name: doctor.patient_name || "",
      patientId: doctor.patient_id || "",
      entryId: doctor.monitoring_id || "",
      // Фильтр — свойство пары пациент + врач (§9.1), бейдж рендерится в строке
      filter: doctor.filter || null,
    });
  });

  const entries = Object.values(grouped).map((group) => {
    // monitoringId — от первого пациента в группе
    const monitoringId = group.patients.length > 0 ? group.patients[0].entryId : "";
    return {
      hasTickets: Number(group.freeTickets) > 0,
      html: createDoctorCard({
        doctorName: group.doctorName,
        specialty: group.specialty,
        clinicName: group.clinicName,
        status: group.status,
        freeTickets: group.freeTickets,
        matchingFreeTickets: group.matchingFreeTickets,
        filter: group.filter,
        nearestDate: group.nearestDate,
        nearestTime: group.nearestTime,
        patients: group.patients,
        monitoringId: monitoringId,
        isMonitored: true,
      }),
    };
  });

  const available = entries.filter((entry) => entry.hasTickets);
  const waiting = entries.filter((entry) => !entry.hasTickets);

  // Сводка сверху: сколько врачей с талонами, сколько ждём.
  const summary = `
    <div class="home-summary">
      <div class="summary-tile">
        <div class="summary-tile__value">${available.length}</div>
        <div class="summary-tile__label">есть талоны</div>
      </div>
      <div class="summary-tile">
        <div class="summary-tile__value">${entries.length}</div>
        <div class="summary-tile__label">на слежении</div>
      </div>
      <div class="summary-tile">
        <div class="summary-tile__value">${bookingsCount}</div>
        <div class="summary-tile__label">запись</div>
      </div>
    </div>`;

  const buildSection = (title, items, modifier = "") => {
    if (items.length === 0) return "";
    return `
      <section class="list-section ${modifier}">
        <h2 class="list-section__title">${title}</h2>
        ${items.map((entry) => entry.html).join("")}
      </section>`;
  };

  return `
    <div class="doctors-list">
      ${summary}
      ${buildSection("Есть талоны", available)}
      ${buildSection("Ждём талоны", waiting, "list-section--waiting")}
    </div>
  `;
}

/**
 * Асинхронный обработчик нажатия на кнопку принудительной проверки слотов.
 *
 * @param {HTMLElement} btn — кнопка refresh
 */
async function handleDoctorRefresh(btn, monitoringIdOverride = "") {
  const monitoringId =
    monitoringIdOverride || btn?.getAttribute("data-monitoring-id");
  if (!monitoringId) return;

  // Показываем анимацию загрузки
  if (btn) btn.classList.add("btn--refresh--loading");

  try {
    const result = await refreshDoctorSlots(monitoringId);

    // Только toast-уведомление, без изменения DOM
    const total = result.total || 0;
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
    // Показываем ошибку
    if (isInTelegram()) {
      window.Telegram.WebApp.showAlert(`Ошибка проверки: ${error.message}`);
    } else {
      alert(`Ошибка проверки: ${error.message}`);
    }
  } finally {
    if (btn) btn.classList.remove("btn--refresh--loading");
  }
}

/**
 * Асинхронный обработчик нажатия на кнопку удаления пациента из карточки врача.
 *
 * @param {HTMLElement} btn — кнопка удаления
 * @param {HTMLElement} container — контейнер для перерендера
 */
async function handleDoctorDelete(btn, container) {
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

    // Тактильный отклик
    if (isInTelegram()) {
      window.Telegram.WebApp.HapticFeedback.notificationOccurred("success");
    }

    // Перезагружаем список
    await renderDoctors(container);
  } catch (error) {
    if (isInTelegram()) {
      window.Telegram.WebApp.showAlert(`Ошибка при удалении: ${error.message}`);
    } else {
      alert(`Ошибка при удалении: ${error.message}`);
    }
  }
}

/**
 * Привязывает обработчик клика по карточке врача → открытие слотов.
 *
 * @param {HTMLElement} container — контейнер со списком
 * @param {Array} doctors — массив врачей
 */
function bindDoctorCardClick(container, doctors) {
  container.querySelectorAll(".doctor-card").forEach((card) => {
    card.addEventListener("click", async (e) => {
      if (card._swiped) return;
      if (e.target.closest(".doctor-row__more")) return;

      // Не реагируем на клики по кнопкам удаления пациентов, настройки
      // фильтра и кнопке обновления
      if (e.target.closest(".monitoring-patient__delete")) return;
      if (e.target.closest(".monitoring-patient__filter")) return;
      if (e.target.closest(".btn--refresh")) return;

      // Находим пациентов для этой карточки
      const patients = findPatientsForCard(card, doctors);

      // Пациент выбирается селектом в карточке (P2-BOOKFLOW): всплывающий
      // выбор убран — сначала пациент, затем время на экране слотов.
      const select = card.querySelector(".doctor-card__patient-select");
      const entryId = select?.value || card.getAttribute("data-entry-id");
      if (!entryId) return;

      navigate("slots", { monitoringId: entryId, patients });
    });
  });
}

/**
 * Привязывает обработчики кнопок принудительной проверки слотов.
 *
 * @param {HTMLElement} container — контейнер со списком
 */
function bindDoctorRefreshButtons(container) {
  container.querySelectorAll(".btn--refresh").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      handleDoctorRefresh(btn);
    });
  });
}

/**
 * Привязывает обработчики кнопок удаления пациентов из карточек врачей.
 *
 * @param {HTMLElement} container — контейнер со списком
 */
function bindDoctorDeleteButtons(container) {
  container.querySelectorAll(".monitoring-patient__delete").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      handleDoctorDelete(btn, container);
    });
  });
}

/**
 * Привязывает обработчики кнопок настройки фильтра в строках пациентов.
 *
 * Кнопка живёт в строке пациента, поэтому фильтр открывается для пары
 * пациент + врач (§9.5.1). `stopPropagation` обязателен: иначе сработает
 * навигация в слоты по клику на карточку.
 *
 * @param {HTMLElement} container — контейнер со списком
 * @param {Array} doctors — массив врачей из API
 */
function bindFilterButtons(container, doctors) {
  container.querySelectorAll(".monitoring-patient__filter").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      btn.blur();

      const monitoringId = btn.getAttribute("data-entry-id");
      if (!monitoringId) return;

      const doctor = doctors.find(
        (item) => item.monitoring_id === monitoringId,
      );

      openFilterModal({
        monitoringId,
        doctorName: doctor ? extractDoctorName(doctor) : "",
        patientName: doctor ? doctor.patient_name || "" : "",
        filter: doctor ? doctor.filter || null : null,
        onChanged: () => renderDoctors(container),
      });
    });
  });
}

/**
 * Открывает нативное меню действий для карточки врача.
 *
 * @param {HTMLElement} card — карточка врача
 * @param {Array} doctors — массив врачей
 * @param {HTMLElement} container — контейнер списка
 */
function openDoctorActions(card, doctors, container) {
  const patients = findPatientsForCard(card, doctors);
  if (!patients.length) return;

  const select = card.querySelector(".doctor-card__patient-select");
  const entryId =
    select?.value || card.getAttribute("data-entry-id") || patients[0].entryId;
  const patient = patients.find((p) => p.entryId === entryId) || patients[0];
  const doctor = doctors.find((item) => item.monitoring_id === entryId);
  const tg = window.Telegram?.WebApp;
  if (typeof tg?.showPopup !== "function") return;

  tg.HapticFeedback?.impactOccurred?.("light");
  tg.showPopup(
    {
      title: doctor ? extractDoctorName(doctor) : "Действия",
      message: patient.name ? `Пациент: ${patient.name}` : "",
      buttons: [
        { id: "filter", type: "default", text: "Фильтр" },
        { id: "delete", type: "destructive", text: "Удалить" },
        { id: "refresh", type: "default", text: "Проверить" },
      ],
    },
    (buttonId) => {
      if (buttonId === "filter") {
        openFilterModal({
          monitoringId: entryId,
          doctorName: doctor ? extractDoctorName(doctor) : "",
          patientName: patient.name || "",
          filter: doctor ? doctor.filter || null : null,
          onChanged: () => renderDoctors(container),
        });
      } else if (buttonId === "delete") {
        const temp = document.createElement("span");
        temp.setAttribute("data-entry-id", entryId);
        temp.setAttribute("data-patient-name", patient.name || "");
        handleDoctorDelete(temp, container);
      } else if (buttonId === "refresh") {
        handleDoctorRefresh(null, entryId);
      }
    },
  );
}

/**
 * Привязывает кнопки «⋯» к меню действий.
 *
 * @param {HTMLElement} container — контейнер списка
 * @param {Array} doctors — массив врачей
 */
function bindDoctorMenu(container, doctors) {
  container.querySelectorAll(".doctor-row__more").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const card = btn.closest(".doctor-card");
      if (card) openDoctorActions(card, doctors, container);
    });
  });
}

/**
 * Свайп влево по строке врача открывает меню действий.
 *
 * @param {HTMLElement} container — контейнер списка
 * @param {Array} doctors — массив врачей
 */
function bindDoctorSwipe(container, doctors) {
  container.querySelectorAll(".doctor-row").forEach((row) => {
    let startX = 0;
    let startY = 0;

    row.addEventListener(
      "touchstart",
      (event) => {
        const touch = event.touches[0];
        if (!touch) return;
        startX = touch.clientX;
        startY = touch.clientY;
        row._swiped = false;
      },
      { passive: true },
    );

    row.addEventListener("touchend", (event) => {
      const touch = event.changedTouches[0];
      if (!touch) return;
      const dx = touch.clientX - startX;
      const dy = touch.clientY - startY;
      if (dx < -60 && Math.abs(dy) < 40) {
        row._swiped = true;
        openDoctorActions(row, doctors, container);
        setTimeout(() => {
          row._swiped = false;
        }, 400);
      }
    });
  });
}

/**
 * Привязывает обработчики событий для списка врачей.
 *
 * @param {HTMLElement} container — контейнер со списком
 * @param {Array} doctors — массив врачей
 */
function bindDoctorEvents(container, doctors) {
  bindDoctorCardClick(container, doctors);
  bindDoctorRefreshButtons(container);
  bindDoctorDeleteButtons(container);
  bindFilterButtons(container, doctors);
  bindDoctorMenu(container, doctors);
  bindDoctorSwipe(container, doctors);
  bindPatientSelects(container, doctors);
}

/**
 * Привязывает селекты пациента в карточках врачей (P2-BOOKFLOW).
 *
 * Смена пациента сразу перезапрашивает слоты: они пациент-зависимы
 * (`monitoring_id` считается на пару пациент + врач), поэтому переход на экран
 * слотов выполняется с новым `monitoring_id`.
 *
 * @param {HTMLElement} container — контейнер со списком
 * @param {Array} doctors — массив врачей
 */
function bindPatientSelects(container, doctors) {
  container
    .querySelectorAll(".doctor-card__patient-select")
    .forEach((select) => {
      select.addEventListener("click", (e) => e.stopPropagation());
      select.addEventListener("change", (e) => {
        e.stopPropagation();
        const card = select.closest(".doctor-card");
        if (!card || !select.value) return;
        const patients = findPatientsForCard(card, doctors);
        navigate("slots", { monitoringId: select.value, patients });
      });
    });
}

/**
 * Находит пациентов для карточки врача по номеру карточки в DOM.
 *
 * @param {HTMLElement} card — DOM-элемент карточки врача
 * @param {Array} doctors — массив врачей из API
 * @returns {Array<{name: string, patientId: string, entryId: string}>}
 */
function findPatientsForCard(card, doctors) {
  const raw = card.getAttribute("data-patients");
  if (raw) {
    try {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) return parsed;
    } catch {
      // Повреждённый атрибут — используем старый расчёт по индексу.
    }
  }

  const cardIndex = Array.from(card.parentElement.children).indexOf(card);

  // Группируем врачей так же, как в renderDoctorList
  const grouped = {};
  doctors.forEach((doctor) => {
    if (!grouped[doctor.doctor_id]) {
      grouped[doctor.doctor_id] = { patients: [] };
    }
    grouped[doctor.doctor_id].patients.push({
      name: doctor.patient_name || "",
      patientId: doctor.patient_id || "",
      entryId: doctor.monitoring_id || "",
    });
  });

  const groups = Object.values(grouped);
  if (cardIndex >= 0 && cardIndex < groups.length) {
    return groups[cardIndex].patients;
  }
  return [];
}

/**
 * Привязывает обработчики для пустого состояния.
 *
 * @param {HTMLElement} container — контейнер
 */
function bindEmptyEvents(container) {
  const addBtn = container.querySelector("#empty-add-btn");
  if (addBtn) {
    addBtn.addEventListener("click", () => {
      navigate("add");
    });
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
