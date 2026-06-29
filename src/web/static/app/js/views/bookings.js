/**
 * Экран «Мои записи» — список активных и архивных бронирований.
 *
 * @module views/bookings
 */

import { createBookingCard } from "../components/card.js";
import { lucideIcon } from "../components/icon.js";
import { apiGet } from "../api.js";

/**
 * Рендерит список активных записей пользователя.
 *
 * @param {HTMLElement} container — DOM-элемент контейнера
 * @returns {Promise<void>}
 */
export async function renderBookingsList(container) {
  try {
    const data = await apiGet("/bookings");
    const bookings = data.bookings || [];

    if (bookings.length === 0) {
      container.innerHTML = `
        <div class="empty-state">
          <div class="empty-state__icon">${lucideIcon("calendar-x", 48)}</div>
          <p class="empty-state__text">У вас пока нет записей к врачам.</p>
        </div>
        <div class="bookings-archive-link">
          <button class="btn btn--sm btn--ghost" id="btn-view-archive">
            <span class="lucide-icon">${lucideIcon("archive", 14)}</span> Архив записей
          </button>
        </div>
      `;
    } else {
      const cards = bookings.map((b) => createBookingCard(b)).join("");
      container.innerHTML = `
        <div class="bookings-list">${cards}</div>
        <div class="bookings-archive-link">
          <button class="btn btn--sm btn--ghost" id="btn-view-archive">
            <span class="lucide-icon">${lucideIcon("archive", 14)}</span> Архив записей
          </button>
        </div>
      `;
    }

    // Привязываем обработчики экспорта
    bindExportButtons(container);
    // Привязываем переход в архив
    bindArchiveButton(container);
  } catch (err) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-state__icon">${lucideIcon("alert-triangle", 48)}</div>
        <p class="empty-state__text">Не удалось загрузить записи.</p>
        <p class="empty-state__hint">Проверьте соединение и попробуйте снова.</p>
      </div>
    `;
    console.error("Ошибка загрузки записей:", err);
  }
}

/**
 * Рендерит список архивных записей пользователя.
 *
 * @param {HTMLElement} container — DOM-элемент контейнера
 * @returns {Promise<void>}
 */
export async function renderArchiveList(container) {
  try {
    const data = await apiGet("/bookings/archive");
    const bookings = data.bookings || [];

    if (bookings.length === 0) {
      container.innerHTML = `
        <div class="empty-state">
          <div class="empty-state__icon">${lucideIcon("archive-x", 48)}</div>
          <p class="empty-state__text">В архиве пока нет записей.</p>
        </div>
        <div class="bookings-archive-link">
          <button class="btn btn--sm btn--ghost" id="btn-view-active">
            <span class="lucide-icon">${lucideIcon("list", 14)}</span> Активные записи
          </button>
        </div>
      `;
    } else {
      const cards = bookings.map((b) => createBookingCard(b)).join("");
      container.innerHTML = `
        <div class="bookings-list">${cards}</div>
        <div class="bookings-archive-link">
          <button class="btn btn--sm btn--ghost" id="btn-view-active">
            <span class="lucide-icon">${lucideIcon("list", 14)}</span> Активные записи
          </button>
        </div>
      `;
    }

    bindExportButtons(container);
    bindActiveButton(container);
  } catch (err) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-state__icon">${lucideIcon("alert-triangle", 48)}</div>
        <p class="empty-state__text">Не удалось загрузить архив.</p>
      </div>
    `;
    console.error("Ошибка загрузки архива:", err);
  }
}

/**
 * Привязывает обработчики к кнопкам экспорта (PNG / ICS).
 *
 * @param {HTMLElement} container — DOM-элемент контейнера
 */
function bindExportButtons(container) {
  const buttons = container.querySelectorAll(".booking-export-btn");
  buttons.forEach((btn) => {
    btn.addEventListener("click", async (e) => {
      e.preventDefault();
      const bookingId = btn.dataset.bookingId;
      const format = btn.dataset.format;

      if (!bookingId || !format) return;

      try {
        // Скачиваем файл через API
        const response = await fetch(
          `/api/user/bookings/${encodeURIComponent(bookingId)}/export?format=${format}`,
          {
            headers: {
              "X-Telegram-Init-Data": window.Telegram?.WebApp?.initData || "",
            },
          },
        );

        if (!response.ok) {
          const errData = await response.json().catch(() => ({}));
          const detail = errData.detail || "Не удалось скачать файл.";
          if (window.showToast) {
            window.showToast(`❌ ${detail}`, "error");
          }
          return;
        }

        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        const ext = format === "ics" ? "ics" : "png";
        a.download = `booking_${bookingId}.${ext}`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);

        if (window.showToast) {
          window.showToast("✅ Файл сохранён", "success");
        }
      } catch (err) {
        console.error("Ошибка экспорта:", err);
        if (window.showToast) {
          window.showToast("❌ Ошибка при скачивании", "error");
        }
      }
    });
  });
}

/**
 * Привязывает обработчик кнопки перехода в архив.
 *
 * @param {HTMLElement} container — DOM-элемент контейнера
 */
function bindArchiveButton(container) {
  const btn = container.querySelector("#btn-view-archive");
  if (btn) {
    btn.addEventListener("click", () => {
      // Динамически импортируем navigate для избежания циклических зависимостей
      import("../app.js").then((app) => {
        app.navigate("bookings-archive");
      });
    });
  }
}

/**
 * Привязывает обработчик кнопки возврата к активным записям.
 *
 * @param {HTMLElement} container — DOM-элемент контейнера
 */
function bindActiveButton(container) {
  const btn = container.querySelector("#btn-view-active");
  if (btn) {
    btn.addEventListener("click", () => {
      import("../app.js").then((app) => {
        app.navigate("bookings");
      });
    });
  }
}
