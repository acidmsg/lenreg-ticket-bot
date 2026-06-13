/**
 * Главный модуль Mini App.
 * Инициализация Telegram.WebApp, SPA-роутер, управление темой.
 *
 * @module app
 */

import { isInTelegram, getUserInfo, getInitDataError } from './auth.js';
import { renderDoctors } from './views/doctors.js';
import { renderAddDoctor } from './views/add.js';
import { renderSlots } from './views/slots.js';
import { renderPatients, renderPatientAddForm } from './views/patients.js';
import { renderHeader } from './components/header.js';
import { lucideIcon } from './components/icon.js';
import './components/toast.js'; // Сайд-эффект: устанавливает window.showToast

// ============================================================
// Глобальное состояние приложения
// ============================================================

/**
 * @typedef {object} AppState
 * @property {string} route — текущий маршрут ('doctors', 'add', 'slots', 'patients')
 * @property {object|null} routeParams — параметры маршрута (например, { monitoringId })
 * @property {Array<{route: string, params: object|null}>} history — история навигации
 */

/** @type {AppState} */
const state = {
  route: 'doctors',
  routeParams: null,
  history: []
};

// ============================================================
// Управление темой
// ============================================================

/**
 * Применяет цветовую схему Telegram через CSS-переменные.
 *
 * @param {object} themeParams — Telegram.WebApp.themeParams
 */
function applyTheme(themeParams) {
  if (!themeParams) return;

  const root = document.documentElement;
  const mapping = {
    bg_color: '--tg-bg-color',
    text_color: '--tg-text-color',
    hint_color: '--tg-hint-color',
    button_color: '--tg-button-color',
    button_text_color: '--tg-button-text-color',
    secondary_bg_color: '--tg-secondary-bg-color',
    section_header_text_color: '--tg-section-header-color',
    subtitle_text_color: '--tg-subtitle-color',
    destructive_text_color: '--tg-destructive-color',
    link_color: '--tg-link-color'
  };

  Object.entries(mapping).forEach(([tgKey, cssVar]) => {
    if (themeParams[tgKey]) {
      root.style.setProperty(cssVar, themeParams[tgKey], 'important');
    }
  });

  // Устанавливаем color-scheme для нативной тёмной темы
  if (window.Telegram && window.Telegram.WebApp) {
    const colorScheme = window.Telegram.WebApp.colorScheme;
    root.style.setProperty('color-scheme', colorScheme);
  }
}

/**
 * Принудительное переопределение цветовой схемы.
 * Обходит инлайн-стили Telegram WebView на мобильных устройствах,
 * используя третий аргумент 'important' в setProperty.
 */
function forceThemeOverride() {
  const theme = {
    bg_color: '#0a0a10',
    secondary_bg_color: '#12121c',
    text_color: '#e0e8f8',
    hint_color: '#89b',
    button_color: '#09b653',
    button_text_color: '#0a0a10',
    destructive_text_color: '#ea336f',
    section_header_text_color: '#09b653',
    subtitle_text_color: '#89b',
    link_color: '#09b653'
  };

  const root = document.documentElement;
  Object.entries(theme).forEach(([key, val]) => {
    root.style.setProperty('--tg-' + key, val, 'important');
  });
}

// ============================================================
// SPA-роутер
// ============================================================

/**
 * Навигация между экранами Mini App.
 *
 * @param {string} route — имя маршрута ('doctors', 'add', 'slots', 'patients')
 * @param {object|null} [params=null] — параметры маршрута
 */
export function navigate(route, params = null) {
  // Сохраняем текущий маршрут в историю
  state.history.push({ route: state.route, params: state.routeParams });
  state.route = route;
  state.routeParams = params;
  render();
}

/**
 * Возврат на предыдущий экран.
 */
function goBack() {
  if (state.history.length === 0) {
    // Если истории нет — закрываем Mini App
    if (isInTelegram()) {
      window.Telegram.WebApp.close();
    }
    return;
  }

  const prev = state.history.pop();
  state.route = prev.route;
  state.routeParams = prev.params;
  render();
}

// ============================================================
// Рендеринг
// ============================================================

/**
 * Рендерит текущий экран на основе состояния маршрута.
 */
function render() {
  const app = document.getElementById('app');
  if (!app) return;

  // Управление кнопкой «Назад»
  if (isInTelegram()) {
    const backButton = window.Telegram.WebApp.BackButton;
    if (state.history.length > 0) {
      backButton.show();
    } else {
      backButton.hide();
    }
  }

  const userInfo = getUserInfo();
  const userName = userInfo ? userInfo.first_name || 'Пользователь' : '';

  let content = '';

  switch (state.route) {
    case 'doctors':
      content = `
        ${renderHeader('Мониторинг врачей', state.history.length > 0, userName)}
        <div class="app-content" id="doctors-content"></div>
        <div class="fab-group">
          <button class="btn btn--secondary btn--sm" id="btn-patients"><span class="lucide-icon">${lucideIcon('users', 16)}</span> Пациенты</button>
          <button class="fab" id="fab-add"><span class="lucide-icon">${lucideIcon('circle-plus', 18)}</span> Новый мониторинг</button>
        </div>
      `;
      break;

    case 'add':
      content = `
        ${renderHeader('Новый мониторинг', true, userName)}
        <div class="app-view" id="add-content"></div>
      `;
      break;

    case 'slots':
      content = `
        ${renderHeader('Свободные номерки', true, userName)}
        <div class="app-content" id="slots-content"></div>
      `;
      break;

    case 'patients':
      content = `
        ${renderHeader('Пациенты', true, userName)}
        <div class="app-content" id="patients-content"></div>
      `;
      break;

    case 'patient-add':
      content = `
        ${renderHeader('Новый пациент', true, userName)}
        <div class="app-view" id="patient-add-content"></div>
      `;
      break;

    default:
      navigate('doctors');
      return;
  }

  app.innerHTML = content;

  // Привязываем обработчик к стрелочной кнопке «← Назад» в шапке
  const headerBackBtn = document.getElementById('header-back');
  if (headerBackBtn) {
    headerBackBtn.addEventListener('click', goBack);
  }

  // Рендерим содержимое конкретного экрана
  switch (state.route) {
    case 'doctors':
      renderDoctors(document.getElementById('doctors-content'));
      bindDoctorsEvents();
      break;

    case 'add':
      renderAddDoctor(document.getElementById('add-content'));
      break;

    case 'slots':
      renderSlots(document.getElementById('slots-content'), state.routeParams);
      break;

    case 'patients':
      renderPatients(document.getElementById('patients-content'));
      break;

    case 'patient-add':
      renderPatientAddForm(document.getElementById('patient-add-content'));
      break;
  }

  // Скрываем MainButton — больше не используется ни на одном экране
  if (isInTelegram() && window.Telegram?.WebApp?.MainButton) {
    window.Telegram.WebApp.MainButton.hide();
  }
}

/**
 * Привязывает обработчики событий для главного экрана.
 */
function bindDoctorsEvents() {
  const fab = document.getElementById('fab-add');
  if (fab) {
    fab.addEventListener('click', () => {
      navigate('add');
    });
  }

  const patientsBtn = document.getElementById('btn-patients');
  if (patientsBtn) {
    patientsBtn.addEventListener('click', () => {
      navigate('patients');
    });
  }
}

// ============================================================
// Инициализация
// ============================================================

/**
 * Точка входа приложения.
 */
function init() {
  const app = document.getElementById('app');

  if (!isInTelegram()) {
    // Показываем сообщение, если открыто вне Telegram
    app.innerHTML = `
      <div class="outside-telegram">
        <div class="outside-telegram__icon">${lucideIcon('smartphone', 64)}</div>
        <p class="outside-telegram__text">
          Откройте это приложение через Telegram Mini App.
        </p>
      </div>
    `;
    return;
  }

  // Инициализация Telegram.WebApp
  const tg = window.Telegram.WebApp;
  tg.ready();
  tg.expand();

  // Применяем форсированную тему (с MutationObserver-защитой от перезаписи Telegram)
  forceThemeOverride();

  // При смене темы в Telegram — переприменить форсированные цвета
  tg.onEvent('themeChanged', () => {
    forceThemeOverride();
  });

  // Кнопка «Назад» в шапке Telegram
  tg.BackButton.onClick(() => {
    goBack();
  });

  // Главная кнопка — не показываем на главном экране
  tg.MainButton.hide();

  // Если initData пуст (например, открыто напрямую, а не через кнопку бота) —
  // показываем понятное сообщение вместо попытки загрузить данные
  const initDataError = getInitDataError();
  if (initDataError) {
    app.innerHTML = `
      <div class="outside-telegram">
        <div class="outside-telegram__icon">${lucideIcon('lock', 64)}</div>
        <p class="outside-telegram__text">${escapeHtml(initDataError)}</p>
        <button class="btn btn--primary mt-md" id="initdata-close-btn">
          Закрыть
        </button>
      </div>
    `;
    const closeBtn = document.getElementById('initdata-close-btn');
    if (closeBtn) {
      closeBtn.addEventListener('click', () => {
        window.Telegram.WebApp.close();
      });
    }
    return;
  }

  // Начальный рендер
  render();
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

// Запуск при загрузке DOM
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
