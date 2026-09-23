/**
 * Главный модуль Mini App.
 * Инициализация Telegram.WebApp, SPA-роутер, управление темой.
 *
 * @module app
 */

import { isInTelegram, getUserInfo, getInitDataError } from "./auth.js";
import { escapeHtml } from "./utils/escape.js";
import { renderDoctors } from "./views/doctors.js";
import { renderAddDoctor } from "./views/add.js";
import { renderSlots } from "./views/slots.js";
import { renderPatients, renderPatientAddForm } from "./views/patients.js";
import { renderBookingsList, renderArchiveList } from "./views/bookings.js";
import { renderHeader } from "./components/header.js";
import { renderTabbar, bindTabbar } from "./components/tabbar.js";
import { openThemeSheet } from "./components/theme-sheet.js";
import { initTheme } from "./theme.js";
import { lucideIcon } from "./components/icon.js";
import "./components/toast.js"; // Сайд-эффект: устанавливает window.showToast

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
  route: "doctors",
  routeParams: null,
  history: [],
};

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
 * Управляет видимостью кнопки «Назад» Telegram в зависимости от маршрута.
 *
 * @param {string} route — текущий маршрут
 */
function setupBackButton(route) {
  const tg = window.Telegram?.WebApp;
  if (!tg) return;
  if (route !== "doctors") {
    tg.BackButton.show();
  } else {
    tg.BackButton.hide();
  }
}

/**
 * Формирует HTML-разметку для текущего маршрута.
 *
 * @param {string} route — текущий маршрут
 * @returns {string} HTML-разметка
 */
function buildRouteHTML(route) {
  const userInfo = getUserInfo();
  const userName = userInfo ? userInfo.first_name || "Пользователь" : "";

  let content;

  switch (route) {
    case "doctors":
      content = `
        ${renderHeader("Мониторинг врачей", state.history.length > 0, userName)}
        <div class="app-content" id="doctors-content"></div>
      `;
      break;
    case "add":
      content = `
        ${renderHeader("Новый мониторинг", true, userName)}
        <div class="app-view" id="add-content"></div>
      `;
      break;
    case "slots":
      content = `
        ${renderHeader("Свободные номерки", true, userName)}
        <div class="app-content" id="slots-content"></div>
      `;
      break;
    case "patients":
      content = `
        ${renderHeader("Пациенты", true, userName)}
        <div class="app-content" id="patients-content"></div>
      `;
      break;
    case "patient-add":
      content = `
        ${renderHeader("Новый пациент", true, userName)}
        <div class="app-view" id="patient-add-content"></div>
      `;
      break;
    case "bookings":
      content = `
        ${renderHeader("Мои записи", true, userName)}
        <div class="app-content" id="bookings-content"></div>
      `;
      break;
    case "bookings-archive":
      content = `
        ${renderHeader("Архив записей", true, userName)}
        <div class="app-content" id="archive-content"></div>
      `;
      break;
    default:
      content = "<p>Страница не найдена</p>";
      break;
  }

  // Нижняя панель навигации отображается на каждом экране
  return `${content}${renderTabbar(route)}`;
}

/**
 * Привязывает обработчики элементов шапки: кнопки «Назад» и выбора темы.
 *
 * @param {HTMLElement} app — корневой элемент приложения
 */
function bindHeaderEvents(app) {
  const headerBackBtn = app.querySelector("#header-back");
  if (headerBackBtn) {
    headerBackBtn.addEventListener("click", goBack);
  }

  const themeBtn = app.querySelector("#header-theme");
  if (themeBtn) {
    themeBtn.addEventListener("click", openThemeSheet);
  }
}

/**
 * Рендерит содержимое для конкретного маршрута в соответствующий контейнер.
 *
 * @param {string} route — текущий маршрут
 */
async function renderRouteContent(route) {
  let container;

  switch (route) {
    case "doctors":
      container = document.getElementById("doctors-content");
      if (container) await renderDoctors(container);
      break;
    case "add":
      container = document.getElementById("add-content");
      if (container) await renderAddDoctor(container);
      break;
    case "slots":
      container = document.getElementById("slots-content");
      if (container) await renderSlots(container, state.routeParams);
      break;
    case "patients":
      container = document.getElementById("patients-content");
      if (container) await renderPatients(container);
      break;
    case "patient-add":
      container = document.getElementById("patient-add-content");
      if (container) await renderPatientAddForm(container);
      break;
    case "bookings":
      container = document.getElementById("bookings-content");
      if (container) await renderBookingsList(container);
      break;
    case "bookings-archive":
      container = document.getElementById("archive-content");
      if (container) await renderArchiveList(container);
      break;
  }
}

/**
 * Рендерит текущий экран на основе состояния маршрута.
 */
async function render() {
  const app = document.getElementById("app");
  if (!app) return;

  const route = state.route;

  setupBackButton(route);
  app.innerHTML = buildRouteHTML(route);
  bindHeaderEvents(app);
  bindTabbar(app);

  // Скрываем MainButton — больше не используется ни на одном экране
  if (isInTelegram() && window.Telegram?.WebApp?.MainButton) {
    window.Telegram.WebApp.MainButton.hide();
  }

  await renderRouteContent(route);
}

// ============================================================
// Инициализация
// ============================================================

/**
 * Точка входа приложения.
 */
function init() {
  const app = document.getElementById("app");

  if (!isInTelegram()) {
    // Показываем сообщение, если открыто вне Telegram
    app.innerHTML = `
      <div class="outside-telegram">
        <div class="outside-telegram__icon">${lucideIcon("smartphone", 64)}</div>
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

  // Применяем сохранённый режим темы (системная / тёмная / светлая)
  initTheme();

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
        <div class="outside-telegram__icon">${lucideIcon("lock", 64)}</div>
        <p class="outside-telegram__text">${escapeHtml(initDataError)}</p>
        <button class="btn btn--primary mt-md" id="initdata-close-btn">
          Закрыть
        </button>
      </div>
    `;
    const closeBtn = document.getElementById("initdata-close-btn");
    if (closeBtn) {
      closeBtn.addEventListener("click", () => {
        window.Telegram.WebApp.close();
      });
    }
    return;
  }

  // Начальный рендер
  render();
}

// Запуск при загрузке DOM
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
