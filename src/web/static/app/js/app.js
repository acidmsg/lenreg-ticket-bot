/**
 * Главный модуль Mini App.
 * Инициализация Telegram.WebApp, SPA-роутер, управление темой.
 *
 * @module app
 */

import { isInTelegram, getUserInfo } from './auth.js';
import { renderDoctors } from './views/doctors.js';
import { renderAddDoctor } from './views/add.js';
import { renderSlots } from './views/slots.js';
import { renderHeader } from './components/header.js';

// ============================================================
// Глобальное состояние приложения
// ============================================================

/**
 * @typedef {object} AppState
 * @property {string} route — текущий маршрут ('doctors', 'add', 'slots')
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
    destructive_text_color: '--tg-destructive-color'
  };

  Object.entries(mapping).forEach(([tgKey, cssVar]) => {
    if (themeParams[tgKey]) {
      root.style.setProperty(cssVar, themeParams[tgKey]);
    }
  });

  // Устанавливаем color-scheme для нативной тёмной темы
  if (window.Telegram && window.Telegram.WebApp) {
    const colorScheme = window.Telegram.WebApp.colorScheme;
    root.style.setProperty('color-scheme', colorScheme);
  }
}

// ============================================================
// SPA-роутер
// ============================================================

/**
 * Навигация между экранами Mini App.
 *
 * @param {string} route — имя маршрута ('doctors', 'add', 'slots')
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
        <button class="fab" id="fab-add">➕ Добавить врача</button>
      `;
      break;

    case 'add':
      content = `
        ${renderHeader('Добавление врача', true, userName)}
        <div class="app-content" id="add-content" style="padding: 0;"></div>
      `;
      break;

    case 'slots':
      content = `
        ${renderHeader('Свободные слоты', true, userName)}
        <div class="app-content" id="slots-content"></div>
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
        <div class="outside-telegram__icon">📱</div>
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

  // Применяем тему
  applyTheme(tg.themeParams);

  // Обработчик изменения темы (тёмная/светлая)
  tg.onEvent('themeChanged', () => {
    applyTheme(tg.themeParams);
  });

  // Кнопка «Назад» в шапке Telegram
  tg.BackButton.onClick(() => {
    goBack();
  });

  // Главная кнопка — не показываем на главном экране
  tg.MainButton.hide();

  // Начальный рендер
  render();
}

// Запуск при загрузке DOM
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
