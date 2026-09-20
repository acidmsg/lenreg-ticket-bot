// Тосты (DASH-9).
//
// Короткие уведомления для действий: сообщение показывается поверх страницы
// и исчезает само, поэтому строка статуса не остаётся единственным следом
// результата.
window.showToast = function (message, kind) {
  if (!message) return;

  var container = document.querySelector(".toast-container");
  if (!container) {
    container = document.createElement("div");
    container.className = "toast-container";
    // Скринридеры должны озвучивать уведомление, не уводя фокус.
    container.setAttribute("role", "status");
    container.setAttribute("aria-live", "polite");
    document.body.appendChild(container);
  }

  var toast = document.createElement("div");
  toast.className = "toast" + (kind ? " toast--" + kind : "");
  toast.setAttribute("role", "status");
  // textContent: сообщение может содержать данные из БД и не должно
  // интерпретироваться как разметка.
  toast.textContent = message;
  container.appendChild(toast);

  window.setTimeout(function () {
    toast.remove();
  }, 4000);
};
