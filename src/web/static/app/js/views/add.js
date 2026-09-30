/**
 * Экран добавления врача (пошаговый stepper).
 * Шаг 1 → Выбор пациента
 * Шаг 2 → Выбор поликлиники
 * Шаг 3 → Выбор врача (имя + специальность подзаголовком)
 * Шаг 4 → Подтверждение → POST /api/user/doctors/add
 *
 * @module views/add
 */

import { apiDelete, apiGet, apiPost } from "../api.js";
import { isInTelegram } from "../auth.js";
import { createStepper } from "../components/stepper.js";
import { escapeHtml } from "../utils/escape.js";
import { lucideIcon } from "../components/icon.js";
import { navigate } from "../app.js";
import { fetchSlots } from "../utils/slots-api.js";
import {
  bindSlotsPickerChips,
  initSlotsPicker,
  renderSlotList,
  renderSlotsPickerLayout,
} from "../components/slots-picker.js";
import { bookSlot } from "../utils/booking.js";

/** Управление мастером: нужно коллбэкам шагов для перехода на экран подтверждения. */
let wizard = null;

/** Режим экрана подтверждения: "booking" — записаться, "monitor" — следить. */
let step5Mode = "monitor";

/** Защита от двойной отправки с экрана подтверждения. */
let step5Submitting = false;

/**
 * Ставит врача под мониторинг (завершение мастера в режиме «Следить»).
 *
 * Вынесено из `onComplete` мастера: тот же поток, что и раньше, — POST
 * `/doctors/add` с возвратом на главный экран и мягкой обработкой дубликата.
 *
 * @param {Array} selections — выбранные значения шагов мастера
 */
async function completeMonitoringStep(selections) {
  // selections содержит 2 или 3 элемента:
  // - Нормальный поток (3): [patient, clinic, doctor]
  // - Глобальный поиск (2): [patient, doctor(with clinic info)]
  const patient = selections[0]?.value;
  let clinic, doctor;

  if (selections[1]?._skipNext) {
    // Глобальный поиск: doctor уже содержит clinic_id
    doctor = selections[1]?.value;
    clinic = {
      clinic_id: doctor?.clinic_id || "",
      short_name: doctor?.clinic_name || "",
      name: doctor?.clinic_name || "",
    };
  } else {
    // Нормальный поток
    clinic = selections[1]?.value;
    doctor = selections[2]?.value;
  }

  const doctorName = extractDoctorName(doctor) || "";
  const specialtyName = doctor?.specialty_name || "";

  try {
    await apiPost("/doctors/add", {
      clinic_id: clinic?.clinic_id || clinic?.id || String(clinic || ""),
      specialty_id: doctor?.specialty_id || "",
      doctor_id: doctor?.doctor_id || doctor?.id || String(doctor || ""),
      patient_id: patient?.patient_id || patient?.id || String(patient || ""),
      doctor_name: doctorName,
      specialty_name: specialtyName,
    });

    // Тактильный отклик
    if (isInTelegram()) {
      window.Telegram.WebApp.HapticFeedback.notificationOccurred("success");
    }

    // Возвращаемся на главный экран
    navigate("doctors");
  } catch (error) {
    // Дубликат (врач уже отслеживается) — возвращаемся на главную без ошибки
    const msg = (error.message || "").toLowerCase();
    if (
      msg.includes("уже отслеживается") ||
      msg.includes("already") ||
      msg.includes("duplicate") ||
      msg.includes("exists")
    ) {
      navigate("doctors");
      return;
    }

    if (isInTelegram()) {
      window.Telegram.WebApp.showAlert(
        `Ошибка при добавлении: ${error.message}`,
      );
    } else {
      alert(`Ошибка при добавлении: ${error.message}`);
    }
  }
}

/**
 * Рендерит экран добавления врача в указанный контейнер.
 *
 * @param {HTMLElement} container — DOM-элемент для рендеринга
 */
export function renderAddDoctor(container) {
  if (!container) return;

  const steps = [
    {
      title: "Выберите пациента",
      description: "Для кого отслеживать врача?",
      loadData: loadPatients,
      renderItem: renderPatientItem,
    },
    {
      title: "Поиск врача",
      description: `${lucideIcon("search", 14)} Начните вводить фамилию, имя или отчество врача`,
      searchPlaceholder: "Фамилия, имя или отчество...",
      searchMode: "doctors",
      onSearchModeChange: (mode) => {
        const step = steps[1];
        if (mode === "doctors") {
          step.title = "Поиск врача";
          step.description = `${lucideIcon("search", 14)} Начните вводить фамилию, имя или отчество врача`;
          step.searchPlaceholder = "Фамилия, имя или отчество...";
        } else {
          step.title = "Выбор поликлиники";
          step.description = "Выберите поликлинику из списка";
          step.searchPlaceholder = "Поиск клиники...";
        }
      },
      // Предпрогрев при выборе: и клиника из списка, и врач глобального
      // поиска несут clinic_id в value. Сигнал «выстрелил-и-забыл» уходит
      // до перехода на шаг 3, чтобы цифры были тёплыми к отрисовке списка.
      onSelect: (item) => preheatClinicSlots(item?.value?.clinic_id),
      loadData: async (selections) => {
        if (steps[1].searchMode === "doctors") {
          return await searchDoctorsGlobally(selections);
        }
        return await loadClinics(selections);
      },
      renderItem: (item) => {
        if (steps[1].searchMode === "doctors") {
          return renderDoctorSearchItem(item);
        }
        return renderClinicItem(item);
      },
    },
    {
      title: "Выберите врача",
      description: "Какого конкретно врача отслеживать?",
      searchPlaceholder: "Поиск по имени или специальности...",
      loadData: loadDoctors,
      renderItem: renderDoctorItem,
      // Догрузка цифр без потери скорости: первый список мгновенный, после
      // отрисовки дорисовываем талоны видимых врачей без действий пользователя.
      onRender: (container, state) => {
        if (hasPendingSlots(state)) {
          startSlotsRefresh(container, state);
        }
      },
    },
    {
      title: "Выбор талона",
      description: "Отметьте время в календаре или перейдите к слежению",
      // Шаг интерактивный, а не список выбора: единственный элемент — панель
      // шага (календарь либо состояние «талонов нет»), поэтому type: "widget"
      // запрещает автопереход по единственному элементу. Решение — за
      // пользователем: «Запись» (после выбора слота) или «Следить».
      type: "widget",
      // Переход («Следить») и действие («Запись») ведут на экран подтверждения:
      // режим фиксируется до перехода, сам экран — следующий шаг мастера.
      nextLabel: "Следить",
      onNext: () => {
        step5Mode = "monitor";
      },
      actionLabel: "Запись",
      onAction: () => {
        step5Mode = "booking";
        if (wizard) wizard.goToStep(4);
      },
      onRender: (container, state) => initStep4Picker(container, state),
      loadData: async (selections) => {
        // На этом шаге данные уже выбраны, показываем подтверждение
        const patient = selections[0]?.value || {};
        let clinic, doctor;

        if (selections[1]?._skipNext) {
          // Глобальный поиск: selections[1] — врач с clinic_id/clinic_name внутри
          doctor = selections[1]?.value || {};
          clinic = {
            name: doctor?.clinic_name || "",
            short_name: doctor?.clinic_name || "",
          };
        } else {
          // Нормальный поток: selections[1] — поликлиника, selections[2] — врач
          clinic = selections[1]?.value || {};
          doctor = selections[2]?.value || {};
        }

        // Развилка «Записаться / Следить»: доступность врача проверяется сразу,
        // чтобы кнопка «Записаться» была активна только при наличии талонов.
        const availability = await loadDoctorAvailability({
          patient,
          clinic,
          doctor,
        });

        return [
          {
            _confirm: true,
            patient,
            clinic,
            doctor,
            availability,
          },
        ];
      },
      renderItem: (item) => renderConfirmation(item),
    },
    {
      title: "Подтверждение",
      description: "Проверьте данные и подтвердите действие",
      completeLabel: "Подтвердить",
      loadData: async () => [
        {
          _summary: true,
          mode: step5Mode,
          ctx: step4Context,
          slot: step4SelectedSlot,
        },
      ],
      renderItem: (item) => renderStep5Summary(item),
    },
  ];

  wizard = createStepper({
    container,
    steps,
    onComplete: async (selections) => {
      // Защита от двойной отправки: повторный клик по «Подтвердить» не должен
      // запускать вторую бронь или повторную постановку под мониторинг.
      if (step5Submitting) return;
      step5Submitting = true;

      try {
        // Экран подтверждения записи: бронируем выбранный талон.
        if (step5Mode === "booking") {
          await handleStep4Booking();
          return;
        }
        await completeMonitoringStep(selections);
      } finally {
        step5Submitting = false;
      }
    },
    onCancel: () => {
      navigate("doctors");
    },
  });

  // Развилка шага 4 живёт в футере stepper'а: «Запись» (кнопка действия,
  // привязывается самим stepper'ом через `onAction`) и «Следить».

  // Перехватываем клики по уже отслеживаемым врачам
  container.addEventListener(
    "click",
    (e) => {
      // Звёздочка избранного: клик по ней не должен выбирать клинику в мастере.
      const favoriteBtn = e.target.closest(".clinic-favorite");
      if (favoriteBtn) {
        e.stopPropagation();
        e.stopImmediatePropagation();
        void toggleClinicFavorite(favoriteBtn);
        return;
      }

      const stepperItem = e.target.closest(".stepper-item");
      if (!stepperItem) return;

      const monitoredEl = stepperItem.querySelector(".doctor-card--monitored");
      if (!monitoredEl) return;

      // Останавливаем всплытие, чтобы stepper не засчитал выбор
      e.stopPropagation();
      e.stopImmediatePropagation();

      if (isInTelegram()) {
        window.Telegram.WebApp.HapticFeedback.notificationOccurred("warning");
      }
      if (window.showToast) {
        window.showToast("Этот врач уже отслеживается");
      }
    },
    true,
  );
}

// ============================================================
// Загрузчики данных для каждого шага
// ============================================================

/**
 * Загружает список пациентов пользователя.
 *
 * @returns {Promise<Array<{value: object, label: string}>>}
 */
async function loadPatients() {
  const data = await apiGet("/patients");
  const patients = data.patients || [];

  if (patients.length === 0) {
    throw new Error(
      "У вас нет добавленных пациентов. Вернитесь назад и нажмите «Пациенты», чтобы добавить пациента.",
    );
  }

  // Сортировка пациентов в алфавитном порядке по ФИО (кириллица).
  // localeCompare('ru') обеспечивает корректную сортировку букв «ё», «Ё» и т.д.
  patients.sort((a, b) => (a.fio || "").localeCompare(b.fio || "", "ru"));

  return patients.map((p) => ({
    value: p,
    label: `${p.fio || "Пациент"}${p.alias ? ` (${p.alias})` : ""}`,
    subtitle: p.bday ? `Дата рождения: ${p.bday}` : "",
  }));
}

/**
 * Загружает список поликлиник (из кэша БД с localStorage-кэшированием).
 *
 * @returns {Promise<Array<{value: object, label: string, subtitle: string}>>}
 */
async function loadClinics() {
  // Пытаемся загрузить из localStorage (TTL 1 час)
  const cached = getFromCache("clinics_cache");
  if (cached) {
    return await applyFavorites(cached);
  }

  const data = await apiGet("/clinics");
  const clinics = data.clinics || [];

  const items = clinics.map((c) => ({
    value: c,
    label: c.short_name || c.name || "Поликлиника",
    subtitle: `${c.name || ""}${c.city ? `, ${c.city}` : ""}`,
  }));

  // Кэшируем на 1 час без пометок избранного: они меняются чаще, чем кэш
  saveToCache("clinics_cache", items);

  return await applyFavorites(items);
}

/**
 * Поднимает избранные клиники наверх и помечает их.
 *
 * Избранное — надстройка: если API недоступен, список клиник всё равно
 * возвращается (без пометок), а не падает.
 *
 * @param {Array<object>} items — элементы списка клиник
 * @returns {Promise<Array<object>>} элементы с полем isFavorite
 */
async function applyFavorites(items) {
  let favoriteIds;
  try {
    const data = await apiGet("/favorites");
    favoriteIds = (data.favorites || []).map((favorite) =>
      String(favorite.clinic_id),
    );
  } catch {
    favoriteIds = [];
  }
  return sortClinicsFavoritesFirst(items, favoriteIds);
}

/**
 * Ставит избранные клиники первыми, сохраняя порядок внутри групп.
 *
 * Чистая функция — покрыта тестом `tests/js/views/add.test.js`.
 *
 * @param {Array<object>} items — элементы списка клиник
 * @param {Array<string>} favoriteIds — id избранных клиник
 * @returns {Array<object>} новые объекты с пометкой isFavorite
 */
export function sortClinicsFavoritesFirst(items, favoriteIds = []) {
  const favorites = new Set(favoriteIds.map((id) => String(id)));
  const marked = (items || []).map((item) => ({
    ...item,
    isFavorite: favorites.has(String(item?.value?.clinic_id ?? "")),
  }));
  return [
    ...marked.filter((item) => item.isFavorite),
    ...marked.filter((item) => !item.isFavorite),
  ];
}

/**
 * Переключает избранное для клиники и обновляет кнопку-звёздочку.
 *
 * @param {HTMLElement} button — кнопка избранного в элементе списка
 */
async function toggleClinicFavorite(button) {
  const clinicId = button?.dataset?.clinicId || "";
  if (!clinicId) return;

  const wasFavorite = button.classList.contains("clinic-favorite--on");
  try {
    if (wasFavorite) {
      await apiDelete(`/favorites/${encodeURIComponent(clinicId)}`);
    } else {
      await apiPost("/favorites", { clinic_id: clinicId });
    }
    button.classList.toggle("clinic-favorite--on", !wasFavorite);
    button.setAttribute("aria-pressed", String(!wasFavorite));
  } catch {
    if (window.showToast) {
      window.showToast("Не удалось изменить избранное", "error");
    }
  }
}

/**
 * Окно догрузки цифр талонов после отрисовки шага 3 (мс).
 *
 * Ограничивает короткий поллинг: не дождались свежего кэша — оставляем
 * то, что есть, без ошибок на экране (владелец карточки MA-STEP3-SLOTS).
 * Окно с запасом к фоновой очереди талонов: полный batch клиники — это
 * десяток вызовов портала, а очередь разбирается раз в 2 с.
 */
const SLOTS_REFRESH_WINDOW_MS = 25000;

/** Интервал повторных запросов догрузки талонов (мс). */
const SLOTS_REFRESH_INTERVAL_MS = 3000;

/**
 * Предел запросов догрузки за одно открытие шага.
 *
 * У врача может честно не быть талонов: 0 — это данные, а не «ещё не знаем»,
 * и по одному этому признаку цикл не отличит «кэш не обновился» от «талонов
 * нет». Поэтому вместо полного окна — ограниченное число запросов: цифры
 * успевают прийти, а сервер не держит ожидание свежего кэша на каждом тике
 * до конца окна (каждый запрос `refresh=1` ждёт до 2.5 с).
 */
const SLOTS_REFRESH_MAX_ATTEMPTS = 5;

/** Поколение догрузки: новый рендер/шаг отменяет прежние циклы. */
let slotsRefreshGeneration = 0;

/**
 * Ставит предпрогрев талонов клиники «выстрелил-и-забыл» (шаг 3).
 *
 * Вызывается при выборе клиники (или врача из глобального поиска) до
 * перехода на шаг «Выберите врача»: сигнал сразу ставит обновление талонов
 * клиники в фоновую очередь, чтобы к отрисовке списка цифры были тёплыми.
 * Ошибки предпрогрева не влияют на экран и молча игнорируются.
 *
 * @param {string|number} clinicId — ID выбранной клиники
 */
export function preheatClinicSlots(clinicId) {
  const id = String(clinicId || "").trim();
  if (!id) return;
  // «Выстрелил-и-забыл»: ответ не нужен, ошибки не показываем.
  apiPost(`/clinics/${encodeURIComponent(id)}/slots/preheat`).catch(() => {});
}

/**
 * Собирает query-параметры списка врачей из выборов мастера.
 *
 * @param {Array<{value: object}>} [selections=[]] — выборы предыдущих шагов
 * @returns {{patient_id?: string, clinic_id?: string}}
 */
function buildAvailabilityParams(selections = []) {
  const params = {};
  // Шаг 0: пациент
  if (selections.length > 0 && selections[0]?.value) {
    const patient = selections[0].value;
    params.patient_id = patient.patient_id || patient.id;
  }
  // Шаг 1: поликлиника
  if (selections.length > 1 && selections[1]?.value) {
    const clinic = selections[1].value;
    params.clinic_id = clinic.clinic_id || clinic.id;
  }
  return params;
}

/**
 * Подзаголовок врача со числом свободных номерков.
 *
 * @param {object} doctor — объект врача из API
 * @returns {string} текст подзаголовка
 */
function doctorSubtitle(doctor) {
  return doctor?.free_tickets !== undefined
    ? `Свободных номерков: ${doctor.free_tickets}`
    : "";
}

/** Есть ли в списке врачи без цифр талонов (для запуска догрузки). */
function hasPendingSlots(state) {
  return (state?.stepData || []).some(
    (item) => !item?._monitored && Number(item?.value?.free_tickets) === 0,
  );
}

/**
 * Дорисовывает цифры талонов в уже отрисованном списке врачей (шаг 3).
 *
 * Обновляет только подзаголовок видимого элемента — без полного
 * перерисовывания списка: не сбрасываются скролл, поиск и выделение.
 * Отслеживаемые врачи не трогаются: у их карточек иной подзаголовок.
 *
 * @param {HTMLElement} container — контейнер stepper'а
 * @param {object} state — состояние stepper'а (stepData — элементы шага)
 * @param {object} data — ответ повторного запроса (поле doctors)
 * @returns {number} — сколько врачей обновилось
 */
export function applyRefreshedSlots(container, state, data) {
  const doctors = data?.doctors || [];
  const items = state?.stepData || [];
  if (!doctors.length || !items.length) return 0;

  const byId = new Map(doctors.map((d) => [String(d.doctor_id), d]));
  let updated = 0;

  items.forEach((item, index) => {
    if (item?._monitored) return;
    const fresh = byId.get(String(item?.value?.doctor_id));
    if (!fresh) return;
    const value = item.value;
    if (
      value.free_tickets === fresh.free_tickets &&
      value.nearest_date === fresh.nearest_date
    ) {
      return;
    }
    value.free_tickets = fresh.free_tickets;
    value.nearest_date = fresh.nearest_date;
    item.subtitle = doctorSubtitle(fresh);
    updated += 1;
    const node = container?.querySelector(
      `.stepper-item[data-index="${index}"] .list__item-subtitle`,
    );
    if (node) node.textContent = item.subtitle;
  });

  return updated;
}

/**
 * Инициирует догрузку цифр талонов видимых врачей без действий пользователя.
 *
 * Короткий поллинг в ограниченном окне: повторный запрос с `refresh=1` ждёт
 * свежий кэш талонов на сервере и возвращает обновлённые значения. Цикл
 * останавливается, когда все видимые врачи получили цифры, либо по концу окна.
 * Ошибки и пустые ответы молча пропускаются — экран остаётся как есть.
 *
 * @param {HTMLElement} container — контейнер stepper'а
 * @param {object} state — состояние stepper'а
 * @param {object} [options={}] — параметры (для тестов)
 * @param {Function} [options.get] — функция GET-запроса
 * @param {number} [options.windowMs] — окно догрузки, мс
 * @param {number} [options.intervalMs] — интервал запросов, мс
 */
export function startSlotsRefresh(container, state, options = {}) {
  const {
    get = apiGet,
    windowMs = SLOTS_REFRESH_WINDOW_MS,
    intervalMs = SLOTS_REFRESH_INTERVAL_MS,
    maxAttempts = SLOTS_REFRESH_MAX_ATTEMPTS,
  } = options;

  const params = buildAvailabilityParams(state?.selections || []);
  if (!params.clinic_id || !params.patient_id) return;

  const generation = ++slotsRefreshGeneration;
  const stepIndex = state.currentStep;
  const startedAt = Date.now();
  let attempts = 0;

  // Цикл жив, пока актуален: не перерисован шаг и не переключён экран.
  const isStale = () =>
    generation !== slotsRefreshGeneration ||
    state.currentStep !== stepIndex ||
    !container?.isConnected;

  const tick = async () => {
    if (isStale()) return;
    attempts += 1;
    let data = null;
    try {
      data = await get("/doctors/available", { ...params, refresh: 1 });
    } catch {
      // Данные не пришли — тихо пробуем ещё раз в пределах окна.
    }
    if (isStale()) return;
    if (data) applyRefreshedSlots(container, state, data);
    if (!hasPendingSlots(state)) return;
    if (attempts >= maxAttempts) return;
    if (Date.now() - startedAt >= windowMs) return;
    setTimeout(tick, intervalMs);
  };

  setTimeout(tick, intervalMs);
}

/**
 * Загружает список доступных врачей для выбранной поликлиники
 * (по всем специальностям одновременно).
 *
 * @param {Array<{value: object, label: string}>} [selections=[]] — выбранные значения предыдущих шагов
 * @returns {Promise<Array<{value: object, label: string, subtitle: string}>>}
 */
async function loadDoctors(selections = []) {
  const params = buildAvailabilityParams(selections);
  // Если нет clinic_id — не вызываем API (гонка при быстром переключении)
  if (!params.clinic_id) return [];
  const data = await apiGet("/doctors/available", params);
  const doctors = data.doctors || [];

  // Получаем текущие мониторинги пользователя, чтобы пометить уже отслеживаемых врачей
  let monitoredDoctorIds = new Set();
  try {
    const monitoringData = await apiGet("/doctors", {
      patient_id: params.patient_id || "",
    });
    const monitoredDoctors = monitoringData.doctors || [];
    monitoredDoctorIds = new Set(
      monitoredDoctors.map((d) => String(d.doctor_id)),
    );
  } catch {
    // Если не удалось получить мониторинги — не блокируем загрузку списка
  }

  return doctors.map((d) => ({
    value: d,
    label: extractDoctorName(d) || "Неизвестный врач",
    specialty: d.specialty_name || "",
    subtitle: doctorSubtitle(d),
    _monitored: monitoredDoctorIds.has(String(d.doctor_id)),
  }));
}

// ============================================================
// Глобальный поиск врачей (используется в режиме 'doctors')
// ============================================================

/**
 * Ищет врачей глобально по подстроке в имени через API /doctors/search.
 *
 * @param {Array<{value: object, label: string}>} [selections=[]] — выбранные значения предыдущих шагов
 * @returns {Promise<Array<{value: object, label: string, subtitle: string}>>}
 */
async function searchDoctorsGlobally(selections = []) {
  // Читаем поисковый запрос из поля ввода stepper
  const searchInput = document.getElementById("stepper-search");
  const query = searchInput ? searchInput.value.trim() : "";

  if (query.length < 2) {
    return [];
  }

  const params = { q: query };

  const data = await apiGet("/doctors/search", params);
  const doctors = data.doctors || [];

  // Получаем текущие мониторинги, чтобы пометить уже отслеживаемых врачей
  let monitoredDoctorIds = new Set();
  try {
    const patient = selections[0]?.value;
    if (patient) {
      const monitoringData = await apiGet("/doctors", {
        patient_id: patient.patient_id || patient.id || "",
      });
      const monitoredDoctors = monitoringData.doctors || [];
      monitoredDoctorIds = new Set(
        monitoredDoctors.map((d) => String(d.doctor_id)),
      );
    }
  } catch {
    // Если не удалось получить мониторинги — не блокируем поиск
  }

  return doctors.map((d) => ({
    value: d,
    label: d.name || "Неизвестный врач",
    specialty: d.specialty_name || "",
    subtitle: d.clinic_name || "",
    // Флаг для stepper: пропустить шаг выбора врача внутри клиники
    _skipNext: true,
    _monitored: monitoredDoctorIds.has(String(d.doctor_id)),
  }));
}

// ============================================================
// Рендереры элементов списка
// ============================================================

/**
 * Рендерит элемент списка пациентов.
 *
 * @param {object} item — элемент списка
 * @returns {string} HTML элемента
 */
function renderPatientItem(item) {
  return `
    <div class="list__item-content">
      <div class="list__item-title">${escapeHtml(item.label)}</div>
      ${item.subtitle ? `<div class="list__item-subtitle">${escapeHtml(item.subtitle)}</div>` : ""}
    </div>
    <span class="list__item-arrow">${lucideIcon("arrow-right", 16)}</span>
  `;
}

/**
 * Рендерит элемент списка поликлиник.
 *
 * @param {object} item — элемент списка
 * @returns {string} HTML элемента
 */
function renderClinicItem(item) {
  const clinicId = String(item?.value?.clinic_id ?? "");
  const favoriteLabel = item.isFavorite
    ? "Убрать из избранного"
    : "Добавить в избранное";
  return `
    <div class="list__item-content">
      <div class="list__item-title">${escapeHtml(item.label)}</div>
      ${item.subtitle ? `<div class="list__item-subtitle">${escapeHtml(item.subtitle)}</div>` : ""}
    </div>
    <button
      class="clinic-favorite${item.isFavorite ? " clinic-favorite--on" : ""}"
      type="button"
      data-clinic-id="${escapeHtml(clinicId)}"
      aria-pressed="${item.isFavorite ? "true" : "false"}"
      aria-label="${favoriteLabel}"
      title="${favoriteLabel}"
    >${lucideIcon("star", 16)}</button>
    <span class="list__item-arrow">${lucideIcon("arrow-right", 16)}</span>
  `;
}

/**
 * Рендерит элемент списка врачей.
 *
 * @param {object} item — элемент списка
 * @returns {string} HTML элемента
 */
/**
 * Рендерит элемент врача в режиме глобального поиска (на шаге clinic).
 * Отличается от renderDoctorItem наличием названия клиники в подзаголовке
 * и флагом _skipNext для пропуска шага выбора врача внутри клиники.
 *
 * @param {object} item — элемент списка врачей (из searchDoctorsGlobally)
 * @returns {string} HTML элемента
 */
function renderDoctorSearchItem(item) {
  // Врач уже отслеживается — показываем серым с пометкой
  if (item._monitored) {
    return `
      <div class="doctor-card--monitored">
        <div class="list__item-content">
          <div class="list__item-title">${escapeHtml(item.label)}</div>
          ${item.specialty ? `<div class="list__item-subtitle">${escapeHtml(item.specialty)}</div>` : ""}
          ${item.subtitle ? `<div class="list__item-subtitle" style="color: var(--color-text-secondary);">${escapeHtml(item.subtitle)}</div>` : ""}
          <div class="list__item-subtitle" style="color: var(--color-danger);">уже отслеживается</div>
        </div>
      </div>
    `;
  }

  return `
    <div class="list__item-content">
      <div class="list__item-title">${escapeHtml(item.label)}</div>
      ${item.specialty ? `<div class="list__item-subtitle">${escapeHtml(item.specialty)}</div>` : ""}
      ${item.subtitle ? `<div class="list__item-subtitle">${escapeHtml(item.subtitle)}</div>` : ""}
    </div>
    <span class="list__item-arrow">${lucideIcon("arrow-right", 16)}</span>
  `;
}

/**
 * Рендерит элемент списка врачей (на шаге выбора врача внутри клиники).
 *
 * @param {object} item — элемент списка
 * @returns {string} HTML элемента
 */
function renderDoctorItem(item) {
  // Врач уже отслеживается — показываем серым с пометкой
  if (item._monitored) {
    return `
      <div class="doctor-card--monitored">
        <div class="list__item-content">
          <div class="list__item-title">${escapeHtml(item.label)}</div>
          ${item.specialty ? `<div class="list__item-subtitle">${escapeHtml(item.specialty)}</div>` : ""}
          ${item.subtitle ? `<div class="list__item-subtitle" style="color: var(--color-text-secondary);">${escapeHtml(item.subtitle)}</div>` : ""}
          <div class="list__item-subtitle" style="color: var(--color-danger);">уже отслеживается</div>
        </div>
      </div>
    `;
  }

  return `
    <div class="list__item-content">
      <div class="list__item-title">${escapeHtml(item.label)}</div>
      ${item.specialty ? `<div class="list__item-subtitle">${escapeHtml(item.specialty)}</div>` : ""}
      ${item.subtitle ? `<div class="list__item-subtitle">${escapeHtml(item.subtitle)}</div>` : ""}
    </div>
    <span class="list__item-arrow">${lucideIcon("arrow-right", 16)}</span>
  `;
}

/**
 * Рендерит экран подтверждения с выбранными данными.
 *
 * @param {object} item — элемент данных шага, содержащий patient, clinic, doctor
 * @returns {string} HTML подтверждения
 */
function renderConfirmation(item) {
  const availability = item.availability || null;

  // Сводка о параметрах записи переехала на экран подтверждения (шаг 5):
  // здесь остаётся только выбор талона.
  return `
    <div class="confirm-card">
      ${renderStep4Block(availability)}
    </div>
  `;
}

/**
 * Рендерит экран подтверждения действия (шаг 5).
 *
 * Показывает итог выбранного действия: что именно произойдёт после нажатия
 * «Подтвердить». Режим выбирается кнопками шага талона: «Запись» — бронь
 * выбранного талона, «Следить» — постановка врача под мониторинг.
 *
 * @param {{mode?: string, ctx?: object, slot?: object}} item — данные шага
 * @returns {string} HTML подтверждения
 */
function renderStep5Summary(item) {
  const mode = item?.mode === "booking" ? "booking" : "monitor";
  const ctx = item?.ctx || {};
  const slot = item?.slot || null;
  const actionText =
    mode === "booking"
      ? "записаться на выбранное время"
      : "следить за появлением талонов";

  const slotRows =
    mode === "booking" && slot
      ? `
        <div class="confirm-label"><span class="lucide-icon">${lucideIcon("clock", 14)}</span> Дата и время</div>
        <div class="confirm-value">${escapeHtml(String(slot.date || ""))}${slot.time ? `, ${escapeHtml(String(slot.time))}` : ""}</div>`
      : "";

  return `
    <div class="confirm-card">
      <div class="confirm-card__details">
        <div class="confirm-label"><span class="lucide-icon">${lucideIcon("user", 14)}</span> Пациент</div>
        <div class="confirm-value">${escapeHtml(ctx.patientName || "Неизвестно")}</div>
        <div class="confirm-label"><span class="lucide-icon">${lucideIcon("hospital", 14)}</span> Клиника</div>
        <div class="confirm-value">${escapeHtml(ctx.clinicName || "Неизвестно")}</div>
        <div class="confirm-label"><span class="lucide-icon">${lucideIcon("stethoscope", 14)}</span> Врач</div>
        <div class="confirm-value">${escapeHtml(ctx.doctorName || "Неизвестно")}</div>
        ${
          ctx.specialty
            ? `
        <div class="confirm-label"><span class="lucide-icon">${lucideIcon("microscope", 14)}</span> Специальность</div>
        <div class="confirm-value">${escapeHtml(ctx.specialty)}</div>`
            : ""
        }
        ${slotRows}
      </div>
      <div class="confirm-note">Нажмите «Подтвердить», чтобы ${escapeHtml(actionText)}.</div>
    </div>
  `;
}

/**
 * Рендерит блок шага 4: доступность врача и календарь выбора слота.
 *
 * Календарь — тот же переиспользуемый компонент, что и на экране номерков
 * (`components/slots-picker.js`), поэтому разметка слотов не дублируется.
 *
 * @param {{slots?: Array, total?: number, error?: boolean}|null} availability — доступность
 * @returns {string} HTML блока либо пустая строка
 */
function renderStep4Block(availability) {
  if (!availability) return "";

  const total = availability.total || 0;

  if (availability.error) {
    return `
      <div class="confirm-availability">
        <div class="confirm-label"><span class="lucide-icon">${lucideIcon("calendar", 14)}</span> Доступность</div>
        <div class="confirm-value">Не удалось проверить номерки</div>
      </div>`;
  }

  if (total === 0) {
    // Номерков нет: календарь не нужен, слежение доступно кнопкой «Следить» в футере.
    return `<div class="confirm-note confirm-note--danger">Талонов сейчас нет — нажмите «Следить», чтобы отслеживать появление.</div>`;
  }

  return `
      <div class="confirm-availability">
        <div class="confirm-label"><span class="lucide-icon">${lucideIcon("calendar", 14)}</span> Доступность</div>
        <div class="confirm-value">Свободных номерков: ${total}. Выберите дату и время.</div>
      </div>
      ${renderSlotsPickerLayout("step4")}`;
}

/** Контекст шага 4 (реквизиты записи) и выбранный слот. */
let step4Context = null;
let step4SelectedSlot = null;

/**
 * Инициализирует календарь выбора слота на шаге подтверждения.
 *
 * Вызывается stepper'ом после рендера шага (`onRender`): DOM уже вставлен,
 * можно поднять VanillaCalendar и панель выбранной даты. Кнопка «Запись»
 * активна только после выбора слота.
 *
 * @param {HTMLElement} container — контейнер stepper'а
 * @param {object} state — состояние stepper'а
 */
function initStep4Picker(container, state) {
  const item = state?.stepData?.[0] || {};
  const availability = item.availability || {};
  const slots = availability.slots || [];
  const doctor = item.doctor || {};
  const clinic = item.clinic || {};

  step4Context = {
    clinicId: availability.clinicId || "",
    doctorId: availability.doctorId || "",
    patientId: availability.patientId || "",
    patientName: availability.patientName || "",
    doctorName: extractDoctorName(doctor) || "",
    specialty: doctor.specialty_name || "",
    clinicName: clinic.short_name || clinic.name || "",
  };
  step4SelectedSlot = null;

  const actionBtn = document.getElementById("stepper-action");
  if (slots.length === 0) {
    if (actionBtn) actionBtn.disabled = true;
    return;
  }

  const select = (slot) => {
    step4SelectedSlot = slot;
    if (actionBtn) actionBtn.disabled = false;
  };

  const calendarReady = initSlotsPicker(container, {
    slots,
    rootId: "step4",
    fallbackClinicId: step4Context.clinicId,
    onSelect: select,
  });

  if (!calendarReady) {
    // Календарь недоступен — плоский список (тот же компонент карточки слота).
    const layout = container.querySelector(".slots-layout");
    if (layout) {
      layout.outerHTML = renderSlotList(slots, step4Context.clinicId);
    }
    bindSlotsPickerChips(container, select);
  }

  // Слот не выбран — «Запись» неактивна.
  if (actionBtn) actionBtn.disabled = true;
}

/**
 * Оформляет запись на выбранный слот шага 4.
 *
 * Путь тот же, что и на экране номерков (`utils/booking.js`): подтверждение →
 * `POST /book` → обработка ошибок. Мониторинг при этом не создаётся.
 */
async function handleStep4Booking() {
  const ctx = step4Context;
  const slot = step4SelectedSlot;
  if (!ctx || !slot) {
    if (window.showToast) {
      window.showToast("❌ Выберите дату и время талона", "error");
    }
    return;
  }

  const result = await bookSlot({
    date: slot.date,
    time: slot.time,
    appointmentId: slot.appointmentId,
    clinicId: slot.clinicId || ctx.clinicId,
    patientId: ctx.patientId,
    doctorId: ctx.doctorId,
    patientName: ctx.patientName,
    doctorName: ctx.doctorName,
    specialty: ctx.specialty,
    clinicName: ctx.clinicName,
  });

  if (result.success) {
    // Запись видна сразу в «Моих записях».
    navigate("bookings");
  }
}

/**
 * Загружает доступность врача для шага подтверждения (best-effort).
 *
 * Использует прямой режим контракта слотов (clinic_id + doctor_id + patient_id),
 * поэтому запись мониторинга на этом шаге ещё не требуется.
 *
 * @param {object} data — выбранные на шаге данные
 * @param {object} data.patient — пациент
 * @param {object} data.clinic — клиника
 * @param {object} data.doctor — врач
 * @returns {Promise<{slots: Array, total: number, error: boolean, clinicId: string, doctorId: string, patientId: string}>}
 *   доступность и идентификаторы для дальнейшего перехода к записи
 */
async function loadDoctorAvailability({ patient, clinic, doctor }) {
  const clinicId = clinic?.clinic_id || clinic?.id || doctor?.clinic_id || "";
  const doctorId = doctor?.doctor_id || doctor?.id || "";
  const patientId = patient?.patient_id || patient?.id || "";
  const patientName = patient?.fio || "";

  try {
    const data = await fetchSlots({ clinicId, doctorId, patientId });
    return {
      slots: data.slots || [],
      total: data.total || 0,
      error: false,
      clinicId,
      doctorId,
      patientId,
      patientName,
    };
  } catch {
    return {
      slots: [],
      total: 0,
      error: true,
      clinicId,
      doctorId,
      patientId,
      patientName,
    };
  }
}

// ============================================================
// Кэширование в localStorage
// ============================================================

const CACHE_PREFIX = "mini_app_";
const CACHE_TTL_MS = 60 * 60 * 1000; // 1 час

/**
 * Сохраняет данные в localStorage-кэш.
 *
 * @param {string} key — ключ кэша
 * @param {any} data — данные для сохранения
 */
function saveToCache(key, data) {
  try {
    const entry = {
      timestamp: Date.now(),
      data,
    };
    localStorage.setItem(`${CACHE_PREFIX}${key}`, JSON.stringify(entry));
  } catch {
    // localStorage может быть недоступен (например, в iframe с ограничениями)
  }
}

/**
 * Загружает данные из localStorage-кэша, если TTL не истёк.
 *
 * @param {string} key — ключ кэша
 * @returns {any|null} данные или null, если просрочены / отсутствуют
 */
function getFromCache(key) {
  try {
    const raw = localStorage.getItem(`${CACHE_PREFIX}${key}`);
    if (!raw) return null;

    const entry = JSON.parse(raw);
    if (Date.now() - entry.timestamp > CACHE_TTL_MS) {
      localStorage.removeItem(`${CACHE_PREFIX}${key}`);
      return null;
    }

    return entry.data;
  } catch {
    return null;
  }
}

/**
 * Извлекает строковое имя врача из поля name, которое может быть объектом.
 *
 * NOTE: Локальная версия отличается от utils/doctor.js (Фаза 2, Шаг 4).
 * utils/doctor.js принимает name напрямую + fallback-параметр.
 * Здесь принимается doctor-объект, извлекается doctor.name,
 * fallback — '' (без doctor.doctor_name). Унификация требует изменения сигнатур.
 *
 * @param {object} doctor — объект врача из API
 * @returns {string} строковое представление имени врача
 */
function extractDoctorName(doctor) {
  const name = doctor.name;
  if (!name) return "";

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
    // Если не удалось извлечь — возвращаем строковое представление объекта
    return String(name);
  }

  return String(name);
}
