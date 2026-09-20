// Действия над пользователем (DASH-8).
//
// Кнопка активна только после отметки подтверждения: флаг confirm уходит
// на сервер, и без него действие не выполняется. После успеха страница
// перезагружается — состояние мониторинга читается из БД, а не правится
// на клиенте.
document.addEventListener("DOMContentLoaded", function () {
  var card = document.querySelector("[data-user]");
  if (!card) return;
  var uid = card.dataset.user;

  card.querySelectorAll("[data-user-action]").forEach(function (block) {
    var action = block.dataset.userAction;
    var confirmBox = block.querySelector(".confirm-box");
    var button = block.querySelector(".action-run");
    var status = block.querySelector(".action-status");

    if (confirmBox && button) {
      confirmBox.addEventListener("change", function () {
        button.disabled = !confirmBox.checked;
      });
    }

    button.addEventListener("click", async function () {
      var params = {};
      block.querySelectorAll("input[name]").forEach(function (input) {
        params[input.name] = input.value;
      });

      button.disabled = true;
      if (status) status.textContent = "Выполняется…";

      try {
        var response = await fetch(
          "/api/dashboard/user-actions/" +
            encodeURIComponent(uid) +
            "/" +
            encodeURIComponent(action),
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              params: params,
              confirm: !!(confirmBox && confirmBox.checked),
            }),
          },
        );
        var data = await response.json().catch(function () {
          return {};
        });

        if (!response.ok) {
          if (status)
            status.textContent = data.detail || "Ошибка " + response.status;
          button.disabled = false;
          return;
        }

        if (status) status.textContent = data.message || "Готово";
        if (window.showToast) window.showToast(data.message || "Готово", "ok");
        window.location.reload();
      } catch (error) {
        if (status) status.textContent = "Сеть недоступна";
        button.disabled = false;
      }
    });
  });
});
