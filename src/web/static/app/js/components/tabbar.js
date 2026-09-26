/**
 * Компонент нижней панели навигации Mini App.
 * Панель зафиксирована внизу экрана, отображается на каждом маршруте,
 * активный пункт выделяется цветом акцента, пункты — только иконки.
 *
 * @module components/tabbar
 */

import { lucideIcon } from "./icon.js";
import { escapeHtml } from "../utils/escape.js";
import { navigate } from "../app.js";

/**
 * Пункты панели: маршрут, иконка Lucide, доступное имя.
 * Первым идёт главный экран — список отслеживаемых врачей.
 */
const TAB_ITEMS = [
  { route: "doctors", icon: "stethoscope", label: "Мониторинг" },
  { route: "patients", icon: "users", label: "Пациенты" },
  { route: "bookings", icon: "calendar", label: "Мои записи" },
  { route: "add", icon: "circle-plus", label: "Поиск врача" },
];

/**
 * Соответствие маршрута и пункта панели.
 * Подэкраны подсвечивают пункт родительского экрана.
 */
const ROUTE_TO_TAB = {
  doctors: "doctors",
  slots: "doctors",
  add: "add",
  patients: "patients",
  "patient-add": "patients",
  "patient-edit": "patients",
  bookings: "bookings",
  "bookings-archive": "bookings",
};

/**
 * Рендерит HTML нижней панели навигации.
 *
 * @param {string} route — текущий маршрут Mini App
 * @returns {string} HTML-строка панели
 */
export function renderTabbar(route) {
  const activeTab = ROUTE_TO_TAB[route] || "";

  const items = TAB_ITEMS.map((item) => {
    const isActive = item.route === activeTab;
    const activeClass = isActive ? " tabbar__item--active" : "";
    const ariaCurrent = isActive ? ' aria-current="page"' : "";
    return `
        <button
          type="button"
          class="tabbar__item${activeClass}"
          data-route="${item.route}"
          aria-label="${escapeHtml(item.label)}"
          ${ariaCurrent}
        ><span class="tabbar__icon">${lucideIcon(item.icon, 24)}</span></button>`;
  }).join("");

  return `
    <nav class="tabbar" id="tabbar" aria-label="Основная навигация">${items}
    </nav>
  `;
}

/**
 * Привязывает обработчики клика к пунктам панели.
 *
 * @param {HTMLElement} app — корневой элемент приложения
 */
export function bindTabbar(app) {
  if (!app) return;

  const items = app.querySelectorAll(".tabbar__item");
  items.forEach((item) => {
    item.addEventListener("click", () => {
      const route = item.dataset.route;
      if (route) navigate(route);
    });
  });
}
