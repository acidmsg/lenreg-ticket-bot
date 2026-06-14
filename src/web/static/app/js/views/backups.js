/**
 * Представление страницы управления резервным копированием.
 *
 * Загружает данные через /api/backups и /api/backups/status,
 * рендерит таблицу бэкапов, панель статуса, обрабатывает создание
 * бэкапов и двухфакторное восстановление.
 *
 * @module views/backups
 */

// ── Конфигурация ─────────────────────────────────────────────

/** Базовый путь API бэкапов */
const API_BASE = '/api/backups';

/** @type {string|null} Токен подтверждения восстановления (шаг 1) */
let restoreToken = null;

/** @type {string|null} Имя файла для восстановления */
let restoreFilename = null;

// ── HTTP-клиент ──────────────────────────────────────────────

/**
 * Читает API-ключ из meta-тега, установленного сервером.
 *
 * @returns {string|null}
 */
function getApiKey() {
  const meta = document.querySelector('meta[name="x-api-key"]');
  return meta ? meta.getAttribute('content') : null;
}

/**
 * Выполняет fetch-запрос к API бэкапов.
 *
 * @param {string} path — путь относительно /api/backups (например, '', '/run')
 * @param {object} [options={}] — параметры fetch
 * @returns {Promise<Response>}
 */
async function apiFetch(path, options = {}) {
  const headers = {
    'Content-Type': 'application/json',
    'X-Requested-With': 'XMLHttpRequest',
    ...(options.headers || {})
  };

  const apiKey = getApiKey();
  if (apiKey) {
    headers['X-API-Key'] = apiKey;
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers
  });

  return response;
}

/**
 * GET-запрос к API бэкапов.
 *
 * @param {string} path — путь (например, '', '/status')
 * @returns {Promise<any>} распарсенный JSON
 */
async function apiGet(path) {
  const response = await apiFetch(path, { method: 'GET' });
  return handleResponse(response);
}

/**
 * POST-запрос к API бэкапов.
 *
 * @param {string} path — путь (например, '/run')
 * @param {object} [body=null] — тело запроса
 * @returns {Promise<any>} распарсенный JSON
 */
async function apiPost(path, body = null) {
  const response = await apiFetch(path, {
    method: 'POST',
    body: body ? JSON.stringify(body) : undefined
  });
  return handleResponse(response);
}

/**
 * DELETE-запрос к API бэкапов.
 *
 * @param {string} path — путь (например, '/filename.db')
 * @returns {Promise<any>} распарсенный JSON
 */
async function apiDelete(path) {
  const response = await apiFetch(path, { method: 'DELETE' });
  return handleResponse(response);
}

/**
 * Обрабатывает ответ сервера.
 *
 * @param {Response} response
 * @returns {Promise<any>}
 */
async function handleResponse(response) {
  let data;
  try {
    data = await response.json();
  } catch {
    if (!response.ok) {
      throw new Error(
        `Ошибка сервера: ${response.status} ${response.statusText}`
      );
    }
    return null;
  }

  if (!response.ok) {
    const message =
      (Array.isArray(data.detail)
        ? data.detail.map((e) => e.msg || JSON.stringify(e)).join('; ')
        : data.detail) ||
      data.message ||
      `Ошибка ${response.status}`;
    throw new Error(message);
  }

  return data;
}

// ── Рендеринг ────────────────────────────────────────────────

/**
 * Главная точка входа: инициализирует страницу.
 */
async function init() {
  await Promise.all([loadStatus(), loadBackups()]);
  bindEvents();
}

/**
 * Загружает и рендерит панель статуса.
 */
async function loadStatus() {
  const lastBackupEl = document.getElementById('status-last-backup');
  const lastSizeEl = document.getElementById('status-last-size');
  const integrityEl = document.getElementById('status-integrity');
  const freeSpaceEl = document.getElementById('status-free-space');

  try {
    const data = await apiGet('/status');

    if (data.last_backup && data.last_backup !== 'None') {
      lastBackupEl.textContent = formatDateTime(data.last_backup);
    } else {
      lastBackupEl.textContent = 'Никогда';
      lastBackupEl.classList.add('text-muted');
    }

    lastSizeEl.textContent = data.last_backup_size || '—';

    if (data.last_integrity) {
      integrityEl.innerHTML = renderIntegrityBadge(data.last_integrity);
    } else {
      integrityEl.textContent = '—';
    }

    freeSpaceEl.textContent = data.free_space || '—';
  } catch (error) {
    lastBackupEl.textContent = 'Ошибка';
    lastBackupEl.style.color = 'var(--color-danger)';
    console.error('Ошибка загрузки статуса бэкапов:', error);
  }
}

/**
 * Загружает и рендерит таблицу бэкапов.
 */
async function loadBackups() {
  const tbody = document.getElementById('backup-table-body');
  if (!tbody) return;

  tbody.innerHTML = `<tr><td colspan="5" class="text-muted">Загрузка...</td></tr>`;

  try {
    const data = await apiGet('');
    const backups = data.backups || [];

    if (backups.length === 0) {
      tbody.innerHTML =
        '<tr><td colspan="5" class="text-muted">Нет бэкапов</td></tr>';
      return;
    }

    tbody.innerHTML = backups.map(renderBackupRow).join('');
    bindRowEvents();
  } catch (error) {
    tbody.innerHTML = `<tr><td colspan="5" class="text-muted" style="color:var(--color-danger)">Ошибка загрузки: ${escapeHtml(error.message)}</td></tr>`;
    console.error('Ошибка загрузки списка бэкапов:', error);
  }
}

/**
 * Рендерит строку таблицы для одного бэкапа.
 *
 * @param {object} b — объект бэкапа
 * @param {string} b.filename
 * @param {string} b.category
 * @param {string} b.size
 * @param {string} b.mtime
 * @param {string} b.integrity
 * @returns {string} HTML строки
 */
function renderBackupRow(b) {
  return `
    <tr>
      <td class="cell-nowrap">${escapeHtml(b.filename)}<br><small class="text-muted">${formatDateTime(b.mtime)}</small></td>
      <td>${renderCategoryBadge(b.category)}</td>
      <td class="cell-nowrap">${escapeHtml(b.size)}</td>
      <td>${renderIntegrityBadge(b.integrity)}</td>
      <td>
        <button class="btn-link backup-restore-btn" data-filename="${escapeHtml(b.filename)}" data-category="${escapeHtml(b.category)}">
          Восстановить
        </button>
        <button class="btn-link backup-delete-btn" data-filename="${escapeHtml(b.filename)}" data-category="${escapeHtml(b.category)}" style="color:var(--color-danger);margin-left:8px;">
          Удалить
        </button>
      </td>
    </tr>
  `;
}

/**
 * Рендерит цветной бейдж категории.
 *
 * @param {string} category — daily | weekly | monthly
 * @returns {string} HTML
 */
function renderCategoryBadge(category) {
  const labels = {
    daily: 'Ежедневный',
    weekly: 'Еженедельный',
    monthly: 'Ежемесячный'
  };
  const label = labels[category] || category;
  return `<span class="backup-category-badge backup-category-badge--${category}">${escapeHtml(label)}</span>`;
}

/**
 * Рендерит индикатор целостности.
 *
 * @param {string} integrity — ok | fail | unchecked
 * @returns {string} HTML
 */
function renderIntegrityBadge(integrity) {
  const map = {
    ok: { icon: '🟢', text: 'Цел', cls: 'backup-integrity--ok' },
    fail: { icon: '🔴', text: 'Повреждён', cls: 'backup-integrity--fail' },
    unchecked: {
      icon: '🟡',
      text: 'Не проверен',
      cls: 'backup-integrity--unchecked'
    }
  };
  const info = map[integrity] || { icon: '⚪', text: integrity, cls: '' };
  return `<span class="backup-integrity ${info.cls}">${info.icon} ${escapeHtml(info.text)}</span>`;
}

// ── Форматирование ───────────────────────────────────────────

/**
 * Форматирует ISO-дату в человекочитаемый формат.
 *
 * @param {string} isoString — ISO 8601 строка
 * @returns {string} форматированная дата
 */
function formatDateTime(isoString) {
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return isoString;
    const day = String(d.getDate()).padStart(2, '0');
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const year = d.getFullYear();
    const hours = String(d.getHours()).padStart(2, '0');
    const minutes = String(d.getMinutes()).padStart(2, '0');
    return `${day}.${month}.${year} ${hours}:${minutes}`;
  } catch {
    return isoString;
  }
}

// ── События ──────────────────────────────────────────────────

/**
 * Привязывает глобальные обработчики событий.
 */
function bindEvents() {
  // Кнопка «Создать бэкап сейчас»
  const createBtn = document.getElementById('btn-create-backup');
  if (createBtn) {
    createBtn.addEventListener('click', onCreateBackup);
  }

  // Кнопка «Обновить»
  const refreshBtn = document.getElementById('btn-refresh-backups');
  if (refreshBtn) {
    refreshBtn.addEventListener('click', async () => {
      await Promise.all([loadStatus(), loadBackups()]);
    });
  }

  // Закрытие модального окна
  const modalClose = document.getElementById('restore-modal-close');
  if (modalClose) {
    modalClose.addEventListener('click', closeRestoreModal);
  }

  // Клик по оверлею — закрыть модальное окно
  const overlay = document.getElementById('restore-modal-overlay');
  if (overlay) {
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) {
        closeRestoreModal();
      }
    });
  }
}

/**
 * Привязывает обработчики к кнопкам «Восстановить» в строках таблицы.
 */
function bindRowEvents() {
  document.querySelectorAll('.backup-restore-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      const filename = btn.dataset.filename;
      const category = btn.dataset.category;
      if (filename) {
        openRestoreStep1(filename, category);
      }
    });
  });
}

// ── Создание бэкапа ──────────────────────────────────────────

/**
 * Обработчик кнопки «Создать бэкап сейчас».
 */
async function onCreateBackup() {
  const btn = document.getElementById('btn-create-backup');
  const spinner = document.getElementById('backup-spinner');

  if (!btn || !spinner) return;

  btn.disabled = true;
  btn.textContent = 'Выполняется...';
  spinner.classList.remove('hidden');

  try {
    const data = await apiPost('/run');

    if (data.status === 'ok') {
      showNotification('Бэкап успешно создан', 'success');
      await Promise.all([loadStatus(), loadBackups()]);
    } else {
      showNotification(data.message || 'Ошибка создания бэкапа', 'error');
    }
  } catch (error) {
    if (
      error.message.includes('409') ||
      error.message.includes('уже выполняется')
    ) {
      showNotification('Бэкап уже выполняется. Попробуйте позже.', 'warning');
    } else {
      showNotification(`Ошибка: ${error.message}`, 'error');
    }
  } finally {
    btn.disabled = false;
    btn.textContent = 'Создать бэкап сейчас';
    spinner.classList.add('hidden');
  }
}

// ── Удаление бэкапа ─────────────────────────────────────────

/**
 * Обработчик кнопки «Удалить» — запрашивает подтверждение и удаляет.
 *
 * @param {string} filename — имя файла бэкапа
 * @param {string} category — категория (daily/weekly/monthly/manual)
 */
async function onDeleteBackup(filename, category) {
  const categoryLabels = {
    daily: 'ежедневный',
    weekly: 'еженедельный',
    monthly: 'ежемесячный',
    manual: 'ручной'
  };
  const catLabel = categoryLabels[category] || category;

  if (
    !confirm(
      `Удалить бэкап?\n\nФайл: ${filename}\nКатегория: ${catLabel}\n\nЭто действие необратимо.`
    )
  ) {
    return;
  }

  try {
    const data = await apiDelete(`/${encodeURIComponent(filename)}`);

    if (data.status === 'ok') {
      showNotification(`Бэкап ${filename} удалён`, 'success');
      await Promise.all([loadStatus(), loadBackups()]);
    } else {
      showNotification(data.message || 'Ошибка удаления бэкапа', 'error');
    }
  } catch (error) {
    showNotification(`Ошибка: ${error.message}`, 'error');
  }
}

// ── Модальное окно восстановления ────────────────────────────

/**
 * Шаг 1: запрос подтверждения (без токена).
 *
 * @param {string} filename — имя файла бэкапа
 * @param {string} category — категория (daily/weekly/monthly)
 */
function openRestoreStep1(filename, category) {
  restoreFilename = filename;
  restoreToken = null;

  const body = document.getElementById('restore-modal-body');
  const footer = document.getElementById('restore-modal-footer');

  if (!body || !footer) return;

  const categoryLabels = {
    daily: 'ежедневный',
    weekly: 'еженедельный',
    monthly: 'ежемесячный',
    manual: 'ручной'
  };
  const catLabel = categoryLabels[category] || category;

  body.innerHTML = `
    <div class="backup-modal__warning">
      <p><strong>Внимание!</strong> Вы собираетесь восстановить базу данных из бэкапа.</p>
      <p>Файл: <code>${escapeHtml(filename)}</code> (${escapeHtml(catLabel)})</p>
      <p class="backup-modal__warning-text">
        Текущая база данных будет заменена. Все изменения, сделанные после этого бэкапа, будут потеряны.
      </p>
    </div>
  `;

  footer.innerHTML = `
    <button class="btn btn--secondary" id="restore-modal-cancel">Отмена</button>
    <button class="btn btn--danger" id="restore-modal-confirm">Подтвердить</button>
  `;

  document
    .getElementById('restore-modal-cancel')
    ?.addEventListener('click', closeRestoreModal);
  document
    .getElementById('restore-modal-confirm')
    ?.addEventListener('click', onRestoreStep1Confirm);

  showRestoreModal();
}

/**
 * Подтверждение шага 1 — запрос токена.
 */
async function onRestoreStep1Confirm() {
  const body = document.getElementById('restore-modal-body');
  const footer = document.getElementById('restore-modal-footer');

  if (!body || !footer) return;

  body.innerHTML = '<p class="text-muted">Запрос подтверждения...</p>';
  footer.innerHTML = '';

  try {
    const data = await apiPost(
      `/restore/${encodeURIComponent(restoreFilename)}`
    );

    if (data.status === 'confirm_required') {
      restoreToken = data.token;
      openRestoreStep2();
    } else {
      body.innerHTML = `<p style="color:var(--color-danger)">Неожиданный ответ сервера: ${escapeHtml(JSON.stringify(data))}</p>`;
      footer.innerHTML =
        '<button class="btn btn--secondary" id="restore-modal-cancel">Закрыть</button>';
      document
        .getElementById('restore-modal-cancel')
        ?.addEventListener('click', closeRestoreModal);
    }
  } catch (error) {
    body.innerHTML = `<p style="color:var(--color-danger)">Ошибка: ${escapeHtml(error.message)}</p>`;
    footer.innerHTML =
      '<button class="btn btn--secondary" id="restore-modal-cancel">Закрыть</button>';
    document
      .getElementById('restore-modal-cancel')
      ?.addEventListener('click', closeRestoreModal);
  }
}

/**
 * Шаг 2: финальное подтверждение с токеном.
 */
function openRestoreStep2() {
  const body = document.getElementById('restore-modal-body');
  const footer = document.getElementById('restore-modal-footer');

  if (!body || !footer) return;

  body.innerHTML = `
    <div class="backup-modal__warning backup-modal__warning--critical">
      <p><strong>Последнее предупреждение!</strong></p>
      <p>Файл: <code>${escapeHtml(restoreFilename)}</code></p>
      <p class="backup-modal__warning-text">
        Восстановление <strong>необратимо</strong>. Текущая база данных будет полностью заменена
        содержимым бэкапа. Убедитесь, что вы выбрали правильный файл.
      </p>
      <p class="backup-modal__warning-text">
        Токен подтверждения действителен 5 минут.
      </p>
    </div>
  `;

  footer.innerHTML = `
    <button class="btn btn--secondary" id="restore-modal-cancel">Отмена</button>
    <button class="btn btn--danger" id="restore-modal-final-confirm">Я понимаю последствия, восстановить</button>
  `;

  document
    .getElementById('restore-modal-cancel')
    ?.addEventListener('click', closeRestoreModal);
  document
    .getElementById('restore-modal-final-confirm')
    ?.addEventListener('click', onRestoreFinalConfirm);
}

/**
 * Финальное подтверждение — вызов restore с токеном.
 */
async function onRestoreFinalConfirm() {
  const body = document.getElementById('restore-modal-body');
  const footer = document.getElementById('restore-modal-footer');

  if (!body || !footer) return;

  body.innerHTML = '<p class="text-muted">Выполняется восстановление...</p>';
  footer.innerHTML = '';

  try {
    const data = await apiPost(
      `/restore/${encodeURIComponent(restoreFilename)}?token=${encodeURIComponent(restoreToken)}`
    );

    if (data.status === 'ok') {
      body.innerHTML =
        '<p style="color:var(--status-available)">Восстановление успешно завершено.</p>';
      showNotification('База данных восстановлена из бэкапа', 'success');
      await Promise.all([loadStatus(), loadBackups()]);
    } else {
      body.innerHTML = `<p style="color:var(--color-danger)">Ошибка восстановления: ${escapeHtml(data.message || 'Неизвестная ошибка')}</p>`;
    }
  } catch (error) {
    body.innerHTML = `<p style="color:var(--color-danger)">Ошибка: ${escapeHtml(error.message)}</p>`;
  }

  footer.innerHTML =
    '<button class="btn btn--secondary" id="restore-modal-close-btn">Закрыть</button>';
  document
    .getElementById('restore-modal-close-btn')
    ?.addEventListener('click', closeRestoreModal);
}

/**
 * Показывает модальное окно.
 */
function showRestoreModal() {
  const overlay = document.getElementById('restore-modal-overlay');
  if (overlay) {
    overlay.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
  }
}

/**
 * Скрывает модальное окно и сбрасывает состояние.
 */
function closeRestoreModal() {
  const overlay = document.getElementById('restore-modal-overlay');
  if (overlay) {
    overlay.classList.add('hidden');
    document.body.style.overflow = '';
  }
  restoreToken = null;
  restoreFilename = null;
}

// ── Уведомления ──────────────────────────────────────────────

/**
 * Показывает временное уведомление.
 *
 * @param {string} message — текст уведомления
 * @param {'success'|'error'|'warning'} type — тип
 */
function showNotification(message, type = 'success') {
  // Удаляем предыдущее уведомление, если есть
  const existing = document.querySelector('.backup-notification');
  if (existing) existing.remove();

  const notification = document.createElement('div');
  notification.className = `backup-notification backup-notification--${type}`;
  notification.textContent = message;
  document.body.appendChild(notification);

  // Анимация появления
  requestAnimationFrame(() => {
    notification.classList.add('backup-notification--visible');
  });

  // Автоскрытие через 4 секунды
  setTimeout(() => {
    notification.classList.remove('backup-notification--visible');
    setTimeout(() => notification.remove(), 300);
  }, 4000);
}

// ── Утилиты ──────────────────────────────────────────────────

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

// ── Запуск ───────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', init);
