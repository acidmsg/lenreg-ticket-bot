/**
 * Экран добавления врача (пошаговый stepper).
 * Шаг 1 → Выбор пациента
 * Шаг 2 → Выбор поликлиники
 * Шаг 3 → Выбор врача (имя + специальность подзаголовком)
 * Шаг 4 → Подтверждение → POST /api/user/doctors/add
 *
 * @module views/add
 */

import { apiGet, apiPost } from '../api.js';
import { isInTelegram } from '../auth.js';
import { createStepper } from '../components/stepper.js';
import { lucideIcon } from '../components/icon.js';
import { navigate } from '../app.js';

/**
 * Рендерит экран добавления врача в указанный контейнер.
 *
 * @param {HTMLElement} container — DOM-элемент для рендеринга
 */
export function renderAddDoctor(container) {
  if (!container) return;

  /** Выбранный пациент (если один — выбирается автоматически) */
  let selectedPatient = null;

  /** ID выбранной поликлиники */
  let selectedClinic = null;

  /** ID выбранного врача */
  let selectedDoctor = null;

  const steps = [
    {
      title: 'Выберите пациента',
      description: 'Для кого отслеживать врача?',
      loadData: loadPatients,
      renderItem: renderPatientItem
    },
    {
      title: 'Поиск врача',
      description: `${lucideIcon('search', 14)} Начните вводить фамилию, имя или отчество врача`,
      searchPlaceholder: 'Фамилия, имя или отчество...',
      searchMode: 'doctors',
      onSearchModeChange: (mode) => {
        const step = steps[1];
        if (mode === 'doctors') {
          step.title = 'Поиск врача';
          step.description = `${lucideIcon('search', 14)} Начните вводить фамилию, имя или отчество врача`;
          step.searchPlaceholder = 'Фамилия, имя или отчество...';
        } else {
          step.title = 'Выбор поликлиники';
          step.description = 'Выберите поликлинику из списка';
          step.searchPlaceholder = 'Поиск клиники...';
        }
      },
      loadData: async (selections) => {
        if (steps[1].searchMode === 'doctors') {
          return await searchDoctorsGlobally(selections);
        }
        return await loadClinics(selections);
      },
      renderItem: (item) => {
        if (steps[1].searchMode === 'doctors') {
          return renderDoctorSearchItem(item);
        }
        return renderClinicItem(item);
      }
    },
    {
      title: 'Выберите врача',
      description: 'Какого конкретно врача отслеживать?',
      searchPlaceholder: 'Поиск по имени или специальности...',
      loadData: loadDoctors,
      renderItem: renderDoctorItem
    },
    {
      title: 'Подтверждение',
      description: 'Проверьте данные перед добавлением',
      loadData: async (selections) => {
        // На этом шаге данные уже выбраны, показываем подтверждение
        const patient = selections[0]?.value || {};
        let clinic, doctor;

        if (selections[1]?._skipNext) {
          // Глобальный поиск: selections[1] — врач с clinic_id/clinic_name внутри
          doctor = selections[1]?.value || {};
          clinic = {
            name: doctor?.clinic_name || '',
            short_name: doctor?.clinic_name || ''
          };
        } else {
          // Нормальный поток: selections[1] — поликлиника, selections[2] — врач
          clinic = selections[1]?.value || {};
          doctor = selections[2]?.value || {};
        }

        return [
          {
            _confirm: true,
            patient,
            clinic,
            doctor,
            _skipNext: selections[1]?._skipNext
          }
        ];
      },
      renderItem: (item) => renderConfirmation(item)
    }
  ];

  createStepper({
    container,
    steps,
    onComplete: async (selections) => {
      // selections содержит 2 или 3 элемента:
      // - Нормальный поток (3): [patient, clinic, doctor]
      // - Глобальный поиск (2): [patient, doctor(with clinic info)]
      const patient = selections[0]?.value;
      let clinic, doctor;

      if (selections[1]?._skipNext) {
        // Глобальный поиск: doctor уже содержит clinic_id
        doctor = selections[1]?.value;
        clinic = {
          clinic_id: doctor?.clinic_id || '',
          short_name: doctor?.clinic_name || '',
          name: doctor?.clinic_name || ''
        };
      } else {
        // Нормальный поток
        clinic = selections[1]?.value;
        doctor = selections[2]?.value;
      }

      const clinicName = clinic?.short_name || clinic?.name || '';
      const doctorName = extractDoctorName(doctor) || '';
      const specialtyName = doctor?.specialty_name || '';

      try {
        await apiPost('/doctors/add', {
          clinic_id: clinic?.clinic_id || clinic?.id || String(clinic || ''),
          specialty_id: doctor?.specialty_id || '',
          doctor_id: doctor?.doctor_id || doctor?.id || String(doctor || ''),
          patient_id:
            patient?.patient_id || patient?.id || String(patient || ''),
          doctor_name: doctorName,
          specialty_name: specialtyName
        });

        // Тактильный отклик
        if (isInTelegram()) {
          window.Telegram.WebApp.HapticFeedback.notificationOccurred('success');
        }

        // Возвращаемся на главный экран
        navigate('doctors');
      } catch (error) {
        // Дубликат (врач уже отслеживается) — просто возвращаемся на главную без ошибки
        const msg = (error.message || '').toLowerCase();
        if (
          msg.includes('уже отслеживается') ||
          msg.includes('already') ||
          msg.includes('duplicate') ||
          msg.includes('exists')
        ) {
          navigate('doctors');
          return;
        }

        if (isInTelegram()) {
          window.Telegram.WebApp.showAlert(
            `Ошибка при добавлении: ${error.message}`
          );
        } else {
          alert(`Ошибка при добавлении: ${error.message}`);
        }
      }
    },
    onCancel: () => {
      navigate('doctors');
    }
  });

  // Перехватываем клики по уже отслеживаемым врачам
  container.addEventListener(
    'click',
    (e) => {
      const stepperItem = e.target.closest('.stepper-item');
      if (!stepperItem) return;

      const monitoredEl = stepperItem.querySelector('.doctor-card--monitored');
      if (!monitoredEl) return;

      // Останавливаем всплытие, чтобы stepper не засчитал выбор
      e.stopPropagation();
      e.stopImmediatePropagation();

      if (isInTelegram()) {
        window.Telegram.WebApp.HapticFeedback.notificationOccurred('warning');
      }
      if (window.showToast) {
        window.showToast('Этот врач уже отслеживается');
      }
    },
    true
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
  const data = await apiGet('/patients');
  const patients = data.patients || [];

  if (patients.length === 0) {
    throw new Error(
      'У вас нет добавленных пациентов. Вернитесь назад и нажмите «Пациенты», чтобы добавить пациента.'
    );
  }

  return patients.map((p) => ({
    value: p,
    label: `${p.fio || 'Пациент'}${p.alias ? ` (${p.alias})` : ''}`,
    subtitle: p.bday ? `Дата рождения: ${p.bday}` : ''
  }));
}

/**
 * Загружает список поликлиник (из кэша БД с localStorage-кэшированием).
 *
 * @returns {Promise<Array<{value: object, label: string, subtitle: string}>>}
 */
async function loadClinics() {
  // Пытаемся загрузить из localStorage (TTL 1 час)
  const cached = getFromCache('clinics_cache');
  if (cached) {
    return cached;
  }

  const data = await apiGet('/clinics');
  const clinics = data.clinics || [];

  const items = clinics.map((c) => ({
    value: c,
    label: c.short_name || c.name || 'Поликлиника',
    subtitle: `${c.name || ''}${c.city ? `, ${c.city}` : ''}`
  }));

  // Кэшируем на 1 час
  saveToCache('clinics_cache', items);

  return items;
}

/**
 * Загружает список специальностей для выбранной поликлиники.
 *
 * @param {Array<{value: object, label: string}>} [selections=[]] — выбранные значения предыдущих шагов
 * @returns {Promise<Array<{value: object, label: string}>>}
 */
async function loadSpecialties(selections = []) {
  const params = {};
  if (selections.length > 1 && selections[1]?.value) {
    const clinic = selections[1].value;
    params.clinic_id = clinic.clinic_id || clinic.id;
  }
  const data = await apiGet('/specialties', params);
  const specialties = data.specialties || [];

  return specialties
    .filter((s) => !s.is_tech && s.is_doc) // Только врачебные специальности
    .map((s) => ({
      value: s,
      label: s.name || `Специальность #${s.specialty_id}`
    }));
}

/**
 * Загружает список доступных врачей для выбранной поликлиники
 * (по всем специальностям одновременно).
 *
 * @param {Array<{value: object, label: string}>} [selections=[]] — выбранные значения предыдущих шагов
 * @returns {Promise<Array<{value: object, label: string, subtitle: string}>>}
 */
async function loadDoctors(selections = []) {
  const params = {};
  // Шаг 0: пациент
  if (selections.length > 0 && selections[0]?.value) {
    const patient = selections[0].value;
    params.patient_id = patient.patient_id || patient.id;
  }
  // Шаг 1: поликлиника (после пациента [0])
  if (selections.length > 1 && selections[1]?.value) {
    const clinic = selections[1].value;
    params.clinic_id = clinic.clinic_id || clinic.id;
  }
  // Если нет clinic_id — не вызываем API (гонка при быстром переключении)
  if (!params.clinic_id) return [];
  const data = await apiGet('/doctors/available', params);
  const doctors = data.doctors || [];

  // Получаем текущие мониторинги пользователя, чтобы пометить уже отслеживаемых врачей
  let monitoredDoctorIds = new Set();
  try {
    const monitoringData = await apiGet('/doctors', {
      patient_id: params.patient_id || ''
    });
    const monitoredDoctors = monitoringData.doctors || [];
    monitoredDoctorIds = new Set(
      monitoredDoctors.map((d) => String(d.doctor_id))
    );
  } catch {
    // Если не удалось получить мониторинги — не блокируем загрузку списка
  }

  return doctors.map((d) => ({
    value: d,
    label: extractDoctorName(d) || 'Неизвестный врач',
    specialty: d.specialty_name || '',
    subtitle:
      d.free_tickets !== undefined
        ? `Свободных номерков: ${d.free_tickets}`
        : '',
    _monitored: monitoredDoctorIds.has(String(d.doctor_id))
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
  const searchInput = document.getElementById('stepper-search');
  const query = searchInput ? searchInput.value.trim() : '';

  if (query.length < 2) {
    return [];
  }

  const params = { q: query };

  const data = await apiGet('/doctors/search', params);
  const doctors = data.doctors || [];

  // Получаем текущие мониторинги, чтобы пометить уже отслеживаемых врачей
  let monitoredDoctorIds = new Set();
  try {
    const patient = selections[0]?.value;
    if (patient) {
      const monitoringData = await apiGet('/doctors', {
        patient_id: patient.patient_id || patient.id || ''
      });
      const monitoredDoctors = monitoringData.doctors || [];
      monitoredDoctorIds = new Set(
        monitoredDoctors.map((d) => String(d.doctor_id))
      );
    }
  } catch {
    // Если не удалось получить мониторинги — не блокируем поиск
  }

  return doctors.map((d) => ({
    value: d,
    label: d.name || 'Неизвестный врач',
    specialty: d.specialty_name || '',
    subtitle: d.clinic_name || '',
    // Флаг для stepper: пропустить шаг выбора врача внутри клиники
    _skipNext: true,
    _monitored: monitoredDoctorIds.has(String(d.doctor_id))
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
      ${item.subtitle ? `<div class="list__item-subtitle">${escapeHtml(item.subtitle)}</div>` : ''}
    </div>
    <span class="list__item-arrow">${lucideIcon('arrow-right', 16)}</span>
  `;
}

/**
 * Рендерит элемент списка поликлиник.
 *
 * @param {object} item — элемент списка
 * @returns {string} HTML элемента
 */
function renderClinicItem(item) {
  return `
    <div class="list__item-content">
      <div class="list__item-title">${escapeHtml(item.label)}</div>
      ${item.subtitle ? `<div class="list__item-subtitle">${escapeHtml(item.subtitle)}</div>` : ''}
    </div>
    <span class="list__item-arrow">${lucideIcon('arrow-right', 16)}</span>
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
          ${item.specialty ? `<div class="list__item-subtitle">${escapeHtml(item.specialty)}</div>` : ''}
          ${item.subtitle ? `<div class="list__item-subtitle" style="color: var(--tg-hint-color);">${escapeHtml(item.subtitle)}</div>` : ''}
          <div class="list__item-subtitle" style="color: var(--tg-destructive-color);">уже отслеживается</div>
        </div>
      </div>
    `;
  }

  return `
    <div class="list__item-content">
      <div class="list__item-title">${escapeHtml(item.label)}</div>
      ${item.specialty ? `<div class="list__item-subtitle">${escapeHtml(item.specialty)}</div>` : ''}
      ${item.subtitle ? `<div class="list__item-subtitle">${escapeHtml(item.subtitle)}</div>` : ''}
    </div>
    <span class="list__item-arrow">${lucideIcon('arrow-right', 16)}</span>
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
          ${item.specialty ? `<div class="list__item-subtitle">${escapeHtml(item.specialty)}</div>` : ''}
          ${item.subtitle ? `<div class="list__item-subtitle" style="color: var(--tg-hint-color);">${escapeHtml(item.subtitle)}</div>` : ''}
          <div class="list__item-subtitle" style="color: var(--tg-destructive-color);">уже отслеживается</div>
        </div>
      </div>
    `;
  }

  return `
    <div class="list__item-content">
      <div class="list__item-title">${escapeHtml(item.label)}</div>
      ${item.specialty ? `<div class="list__item-subtitle">${escapeHtml(item.specialty)}</div>` : ''}
      ${item.subtitle ? `<div class="list__item-subtitle">${escapeHtml(item.subtitle)}</div>` : ''}
    </div>
    <span class="list__item-arrow">${lucideIcon('arrow-right', 16)}</span>
  `;
}

/**
 * Рендерит экран подтверждения с выбранными данными.
 *
 * @param {object} item — элемент данных шага, содержащий patient, clinic, doctor
 * @returns {string} HTML подтверждения
 */
function renderConfirmation(item) {
  const patient = item.patient || {};
  const clinic = item.clinic || {};
  const doctor = item.doctor || {};

  const patientName = patient.fio || 'Неизвестно';
  const clinicName = clinic.short_name || clinic.name || 'Неизвестно';
  const doctorName = extractDoctorName(doctor) || 'Неизвестно';
  const specialtyName = doctor.specialty_name || '';

  return `
    <div class="confirm-card">
      <div class="confirm-card__icon">${lucideIcon('file-text', 48)}</div>
      <div class="confirm-card__details">
        <div class="confirm-label"><span class="lucide-icon">${lucideIcon('user', 14)}</span> Пациент</div>
        <div class="confirm-value">${escapeHtml(patientName)}</div>
        <div class="confirm-label"><span class="lucide-icon">${lucideIcon('hospital', 14)}</span> Клиника</div>
        <div class="confirm-value">${escapeHtml(clinicName)}</div>
        <div class="confirm-label"><span class="lucide-icon">${lucideIcon('stethoscope', 14)}</span> Врач</div>
        <div class="confirm-value">${escapeHtml(doctorName)}</div>
        ${
          specialtyName
            ? `
        <div class="confirm-label"><span class="lucide-icon">${lucideIcon('microscope', 14)}</span> Специальность</div>
        <div class="confirm-value">${escapeHtml(specialtyName)}</div>`
            : ''
        }
      </div>
      <p class="text-center mt-md" style="color: var(--tg-hint-color);">
        Проверьте выбранные данные и нажмите «Готово» для добавления в мониторинг.
      </p>
    </div>
  `;
}

// ============================================================
// Кэширование в localStorage
// ============================================================

const CACHE_PREFIX = 'mini_app_';
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
      data
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
 * @param {object} doctor — объект врача из API
 * @returns {string} строковое представление имени врача
 */
function extractDoctorName(doctor) {
  const name = doctor.name;
  if (!name) return '';

  // Если name — строка, возвращаем как есть
  if (typeof name === 'string') return name;

  // Если name — объект (например, {first_name: "...", last_name: "..."}),
  // пробуем собрать строку из известных полей
  if (typeof name === 'object' && name !== null) {
    const parts = [];
    if (name.last_name) parts.push(name.last_name);
    if (name.first_name) parts.push(name.first_name);
    if (name.middle_name) parts.push(name.middle_name);
    if (parts.length > 0) return parts.join(' ');
    // Если не удалось извлечь — возвращаем строковое представление объекта
    return String(name);
  }

  return String(name);
}

/**
 * Экранирует HTML-символы.
 *
 * @param {string} text — исходный текст
 * @returns {string} экранированный текст
 */
function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = String(text);
  return div.innerHTML;
}
