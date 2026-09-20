// Подтверждение алертов (DASH-5).
//
// Отмечает выбранные строки как "acked" (или "resolved" при data-state).
// После успеха страница перезагружается: список и бейдж в сайдбаре
// пересчитываются на сервере, а не подменяются на клиенте.
document.addEventListener("DOMContentLoaded", function () {
  var button = document.getElementById("ack-selected");
  var status = document.getElementById("ack-status");
  if (!button) return;

  button.addEventListener("click", async function () {
    var checked = Array.prototype.slice.call(
      document.querySelectorAll(".alert-check:checked"),
    );
    if (checked.length === 0) {
      if (status) status.textContent = "Ничего не выбрано";
      return;
    }

    var ids = checked.map(function (box) {
      return parseInt(box.value, 10);
    });

    button.disabled = true;
    if (status) status.textContent = "Отправка…";

    try {
      var response = await fetch("/api/alerts/ack", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ids: ids,
          state: button.dataset.state || "acked",
        }),
      });
      var data = await response.json().catch(function () {
        return {};
      });

      if (!response.ok) {
        if (status)
          status.textContent = data.detail || "Ошибка " + response.status;
        button.disabled = false;
        return;
      }

      if (status) status.textContent = "Обновлено: " + data.changed;
      if (window.showToast)
        window.showToast("Обновлено: " + data.changed, "ok");
      window.location.reload();
    } catch (error) {
      if (status) status.textContent = "Сеть недоступна";
      button.disabled = false;
    }
  });
});
