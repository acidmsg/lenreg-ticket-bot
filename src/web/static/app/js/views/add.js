/**
 * Экран добавления врача (пошаговый stepper).
 * Шаг 1 → Выбор пациента
 * Шаг 2 → Выбор поликлиники
 * Шаг 3 → Выбор специальности
 * Шаг 4 → Выбор врача
 * Шаг 5 → Подтверждение → POST /api/user/doctors/add
 *
 * @module views/add
 */

import { apiGet, apiPost } from '../api.js';
import { isInTelegram } from '../auth.js';
import { createStepper } from '../components/stepper.js';
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

  /** ID выбранной специальности */
  let selectedSpecialty = null;

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
      title: 'Выберите поликлинику',
      description: 'В какой поликлинике искать врача?',
      searchPlaceholder: 'Поиск по названию...',
      loadData: loadClinics,
      renderItem: renderClinicItem
    },
    {
      title: 'Выберите специальность',
      description: 'Какой врач вам нужен?',
      searchPlaceholder: 'Поиск по названию...',
      loadData: loadSpecialties,
      renderItem: renderSpecialtyItem
    },
    {
      title: 'Выберите врача',
      description: 'Какого конкретно врача отслеживать?',
      loadData: loadDoctors,
      renderItem: renderDoctorItem
    },
    {
      title: 'Подтверждение',
      description: 'Проверьте данные перед добавлением',
      loadData: async () => {
        // На этом шаге данные уже выбраны, показываем подтверждение
        return [{ _confirm: true }];
      },
      renderItem: () => renderConfirmation()
    }
  ];

  createStepper({
    container,
    steps,
    onComplete: async (selections) => {
      // selections: [patient, clinic, specialty, doctor, confirm]
      // Данные из всех шагов
      const patient = selections[0]?.value;
      const clinic = selections[1]?.value;
      const specialty = selections[2]?.value;
      const doctor = selections[3]?.value;

      const clinicName = selections[1]?.label || '';
      const doctorName = selections[3]?.label || '';
      const specialtyName = selections[2]?.label || '';

      try {
        await apiPost('/doctors/add', {
          clinic_id: clinic.clinic_id || clinic.id || String(clinic),
          specialty_id:
            specialty.specialty_id || specialty.id || String(specialty),
          doctor_id: doctor.doctor_id || doctor.id || String(doctor),
          patient_id: patient.patient_id || patient.id || String(patient)
        });

        // Тактильный отклик
        if (isInTelegram()) {
          window.Telegram.WebApp.HapticFeedback.notificationOccurred('success');
          window.Telegram.WebApp.sendData(
            JSON.stringify({
              action: 'doctor_added',
              doctor_name: doctorName,
              specialty: specialtyName,
              clinic_name: clinicName
            })
          );
        }

        // Возвращаемся на главный экран
        navigate('doctors');
      } catch (error) {
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
      'У вас нет добавленных пациентов. Добавьте пациента через бота командой /start.'
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
    label: c.short_name || c.name || `Поликлиника №${c.clinic_id}`,
    subtitle: `${c.name || ''}${c.city ? `, ${c.city}` : ''}`
  }));

  // Кэшируем на 1 час
  saveToCache('clinics_cache', items);

  return items;
}

/**
 * Загружает список специальностей для выбранной поликлиники.
 *
 * @returns {Promise<Array<{value: object, label: string}>>}
 */
async function loadSpecialties() {
  const data = await apiGet('/specialties');
  const specialties = data.specialties || [];

  return specialties
    .filter((s) => !s.is_tech && s.is_doc) // Только врачебные специальности
    .map((s) => ({
      value: s,
      label: s.name || `Специальность #${s.specialty_id}`
    }));
}

/**
 * Загружает список доступных врачей по выбранной специальности.
 *
 * @returns {Promise<Array<{value: object, label: string, subtitle: string}>>}
 */
async function loadDoctors() {
  const data = await apiGet('/doctors/available');
  const doctors = data.doctors || [];

  return doctors.map((d) => ({
    value: d,
    label: d.name || `Врач #${d.doctor_id}`,
    subtitle:
      d.free_tickets !== undefined ? `Свободных слотов: ${d.free_tickets}` : ''
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
    <span class="list__item-arrow">→</span>
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
    <span class="list__item-arrow">→</span>
  `;
}

/**
 * Рендерит элемент списка специальностей.
 *
 * @param {object} item — элемент списка
 * @returns {string} HTML элемента
 */
function renderSpecialtyItem(item) {
  return `
    <div class="list__item-content">
      <div class="list__item-title">${escapeHtml(item.label)}</div>
    </div>
    <span class="list__item-arrow">→</span>
  `;
}

/**
 * Рендерит элемент списка врачей.
 *
 * @param {object} item — элемент списка
 * @returns {string} HTML элемента
 */
function renderDoctorItem(item) {
  return `
    <div class="list__item-content">
      <div class="list__item-title">${escapeHtml(item.label)}</div>
      ${item.subtitle ? `<div class="list__item-subtitle">${escapeHtml(item.subtitle)}</div>` : ''}
    </div>
    <span class="list__item-arrow">→</span>
  `;
}

/**
 * Рендерит экран подтверждения (шаг 5).
 *
 * @returns {string} HTML подтверждения
 */
function renderConfirmation() {
  // Данные берутся из selection предыдущих шагов через глобальный стейт stepper
  return `
    <div class="confirm-card">
      <div class="confirm-card__icon">✅</div>
      <p class="text-center mb-md" style="color: var(--tg-hint-color);">
        Проверьте выбранные данные и нажмите «Готово» для добавления врача в мониторинг.
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
