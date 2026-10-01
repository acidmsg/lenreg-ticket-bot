/**
 * Экран «Мои записи» — список активных и архивных бронирований.
 *
 * @module views/bookings
 */

import { createBookingCard } from "../components/card.js";
import { lucideIcon } from "../components/icon.js";
import { apiGet } from "../api.js";
import { buildGoogleCalendarUrl } from "../calendar.js";

/** Период синхронизации со временем: пересчёт границы «прошедшая/актуальная». */
const TIME_SYNC_INTERVAL_MS = 30_000;

/** Текущий список и контейнер — нужны периодическому пересчёту класса. */
const timeSyncState = { timer: null, container: null, bookings: null };

/**
 * Разбирает дату («ДД.ММ.ГГГГ») и время («ЧЧ:ММ») записи в `Date`.
 *
 * @param {object} booking — запись из `GET /api/user/bookings`
 * @returns {Date|null} момент приёма; `null`, если дата или время не сохранены
 */
export function bookingInstant(booking) {
  const date = /^(\d{2})\.(\d{2})\.(\d{4})$/.exec(booking.date || "");
  const time = /^(\d{2}):(\d{2})$/.exec(booking.time || "");
  if (!date || !time) return null;
  const instant = new Date(
    Number(date[3]),
    Number(date[2]) - 1,
    Number(date[1]),
    Number(time[1]),
    Number(time[2]),
  );
  return Number.isNaN(instant.getTime()) ? null : instant;
}

/**
 * Делит записи на прошедшие и актуальные, сортируя каждую группу по времени.
 *
 * @param {Array<object>} bookings — записи пользователя
 * @param {Date} [now] — текущий момент (параметр для тестов)
 * @returns {{past: Array<object>, upcoming: Array<object>, unknown: Array<object>}}
 */
export function orderBookings(bookings, now = new Date()) {
  const dated = [];
  const unknown = [];
  for (const booking of bookings) {
    const instant = bookingInstant(booking);
    if (instant) dated.push({ booking, instant });
    else unknown.push(booking);
  }
  dated.sort((a, b) => a.instant - b.instant);
  return {
    past: dated.filter((x) => x.instant < now).map((x) => x.booking),
    upcoming: dated.filter((x) => x.instant >= now).map((x) => x.booking),
    unknown,
  };
}

/**
 * HTML карточек: прошедшие сверху и тусклые, следом актуальные, в конце — без даты.
 *
 * @param {Array<object>} bookings — записи пользователя
 * @param {Date} now — текущий момент
 * @returns {string} разметка карточек
 */
function bookingsCardsHtml(bookings, now) {
  const { past, upcoming, unknown } = orderBookings(bookings, now);
  return [
    ...past.map((b) => createBookingCard(b, { past: true })),
    ...upcoming.map((b) => createBookingCard(b)),
    ...unknown.map((b) => createBookingCard(b, { undated: true })),
  ].join("");
}

/**
 * Пересчитывает класс «прошедшая» по текущему времени, не пересобирая список:
 * скролл и обработчики сохраняются.
 */
function applyPastFlags() {
  const { container, bookings } = timeSyncState;
  if (!container) return;
  if (!container.isConnected) {
    // Экран закрыт — снимаем интервал и отпускаем отсоединённое DOM-дерево.
    stopTimeSync();
    return;
  }
  if (!bookings) return;
  const now = new Date();
  const byId = new Map(bookings.map((b) => [String(b.booking_id), b]));
  container.querySelectorAll(".booking-card").forEach((card) => {
    const booking = byId.get(card.dataset.bookingId);
    const instant = booking ? bookingInstant(booking) : null;
    card.classList.toggle(
      "booking-card--past",
      Boolean(instant && instant < now),
    );
  });
}

/** Запускает периодическую синхронизацию времени для открытого списка. */
function startTimeSync(container, bookings) {
  stopTimeSync();
  timeSyncState.container = container;
  timeSyncState.bookings = bookings;
  timeSyncState.timer = setInterval(applyPastFlags, TIME_SYNC_INTERVAL_MS);
}

/** Останавливает синхронизацию (пустой список или уход с экрана). */
function stopTimeSync() {
  if (timeSyncState.timer !== null) {
    clearInterval(timeSyncState.timer);
  }
  timeSyncState.timer = null;
  timeSyncState.container = null;
  timeSyncState.bookings = null;
}

/**
 * Прокручивает список так, чтобы первая актуальная запись была сверху экрана.
 *
 * @param {HTMLElement} container — прокручиваемый контейнер экрана
 */
function scrollToFirstUpcoming(container) {
  // Скроллим только когда сверху есть прошедшие: иначе список остаётся сверху.
  if (!container.querySelector(".booking-card--past")) return;
  const first = container.querySelector(
    ".booking-card:not(.booking-card--past):not(.booking-card--undated)",
  );
  if (!first) return;
  const offset =
    first.getBoundingClientRect().top -
    container.getBoundingClientRect().top +
    container.scrollTop;
  if (offset > 0) container.scrollTop = offset;
}

// Возврат в приложение из свёрнутого состояния — пересчитываем границу сразу.
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) applyPastFlags();
});

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
      container.innerHTML = `
        <div class="bookings-list">${bookingsCardsHtml(bookings, new Date())}</div>
        <div class="bookings-archive-link">
          <button class="btn btn--sm btn--ghost" id="btn-view-archive">
            <span class="lucide-icon">${lucideIcon("archive", 14)}</span> Архив записей
          </button>
        </div>
      `;
    }

    if (bookings.length > 0) {
      // Экран открывается на первой актуальной записи; прошедшие — скроллом вверх.
      scrollToFirstUpcoming(container);
      startTimeSync(container, bookings);
    } else {
      stopTimeSync();
    }

    // Привязываем обработчики экспорта
    bindExportButtons(container);
    // Привязываем добавление в календарь
    bindCalendarButtons(container);
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
    bindCalendarButtons(container);
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
        // Файл отдаёт публичный /api/export/* по короткоживущей подписанной
        // ссылке: скачивание через blob в WebView Telegram не срабатывает,
        // а к обычной ссылке нельзя приложить заголовок initData.
        const link = await apiGet(
          `/bookings/${encodeURIComponent(bookingId)}/export-link`,
          { format },
        );
        if (!link || !link.url) {
          if (window.showToast) {
            window.showToast("❌ Не удалось получить ссылку на файл", "error");
          }
          return;
        }
        openDownload(
          link.url,
          link.file_name || `booking_${bookingId}.${format}`,
        );
        if (window.showToast) {
          window.showToast("✅ Файл сохраняется", "success");
        }
      } catch (err) {
        console.error("Ошибка экспорта:", err);
        if (window.showToast) {
          window.showToast(
            `❌ ${(err && err.message) || "Ошибка при скачивании"}`,
            "error",
          );
        }
      }
    });
  });
}

/**
 * Отдаёт файл на устройство: сначала нативное скачивание Telegram, затем
 * внешний браузер (в WebView скачивание blob не работает).
 *
 * @param {string} url — подписанная ссылка на файл
 * @param {string} fileName — предлагаемое имя файла
 */
function openDownload(url, fileName) {
  const webApp = window.Telegram && window.Telegram.WebApp;
  if (webApp && typeof webApp.downloadFile === "function") {
    try {
      webApp.downloadFile({ url, file_name: fileName });
      return;
    } catch (err) {
      console.error("downloadFile недоступен, открываю ссылку:", err);
    }
  }
  if (webApp && typeof webApp.openLink === "function") {
    webApp.openLink(url);
    return;
  }
  window.open(url, "_blank", "noopener");
}

/**
 * Открывает форму добавления записи во внешнем календаре (Google Calendar).
 *
 * @param {HTMLElement} container — DOM-элемент контейнера
 */
function bindCalendarButtons(container) {
  const buttons = container.querySelectorAll(".booking-calendar-btn");
  buttons.forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      const url = buildGoogleCalendarUrl({
        booking_id: btn.dataset.bookingId,
        date: btn.dataset.date,
        time: btn.dataset.time,
        doctor_name: btn.dataset.doctor,
        clinic_name: btn.dataset.clinic,
        patient_name: btn.dataset.patient,
        specialty: btn.dataset.specialty,
        specialty_short: btn.dataset.specialtyShort,
      });
      if (!url) {
        if (window.showToast) {
          window.showToast("❌ Дата приёма не сохранена", "error");
        }
        return;
      }
      const webApp = window.Telegram && window.Telegram.WebApp;
      if (webApp && typeof webApp.openLink === "function") {
        webApp.openLink(url);
        return;
      }
      window.open(url, "_blank", "noopener");
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
