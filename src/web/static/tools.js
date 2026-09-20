// Запуск инструментов обслуживания (DASH-7).
//
// Read-only инструменты и dry-run выполняются сразу; «Применить» доступно
// только после отметки подтверждения, а флаг confirm уходит на сервер —
// без него мутация не запускается.
document.addEventListener("DOMContentLoaded", function () {
  var cards = document.querySelectorAll("[data-tool]");

  cards.forEach(function (card) {
    var name = card.dataset.tool;
    var status = card.querySelector(".tool-status");
    var output = card.querySelector(".tool-output");
    var confirmBox = card.querySelector(".tool-confirm-box");
    var buttons = card.querySelectorAll(".tool-run");

    if (confirmBox) {
      var applyButton = card.querySelector('[data-apply="true"]');
      confirmBox.addEventListener("change", function () {
        if (applyButton) applyButton.disabled = !confirmBox.checked;
      });
    }

    function collectParams() {
      var params = {};
      card
        .querySelectorAll(".tool-field input[name]")
        .forEach(function (input) {
          params[input.name] = input.value;
        });
      return params;
    }

    buttons.forEach(function (button) {
      button.addEventListener("click", async function () {
        var apply = button.dataset.apply === "true";
        buttons.forEach(function (item) {
          item.disabled = true;
        });
        if (status) status.textContent = apply ? "Применение…" : "Запуск…";

        try {
          var response = await fetch(
            "/api/tools/" + encodeURIComponent(name) + "/run",
            {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                params: collectParams(),
                apply: apply,
                confirm: !!(confirmBox && confirmBox.checked),
              }),
            },
          );
          var data = await response.json().catch(function () {
            return {};
          });

          if (status) {
            if (data.status === "confirm_required") {
              status.textContent = "Нужно подтверждение";
            } else if (response.ok) {
              status.textContent =
                (data.applied ? "Применено" : "Dry-run") +
                " · код " +
                data.exit_code +
                " · " +
                data.duration_seconds +
                "с";
            } else {
              status.textContent = data.detail || "Ошибка " + response.status;
            }
          }

          if (window.showToast && response.ok) {
            window.showToast(
              data.applied ? "Инструмент применён" : "Dry-run завершён",
              data.applied ? "ok" : "ok",
            );
          }

          if (output) {
            // textContent: вывод скрипта не должен исполняться как HTML.
            output.textContent = data.output || data.message || "";
            output.hidden = !output.textContent;
          }
        } catch (error) {
          if (status) status.textContent = "Сеть недоступна";
        } finally {
          buttons.forEach(function (item) {
            item.disabled = false;
          });
          if (confirmBox) {
            var applyBtn = card.querySelector('[data-apply="true"]');
            if (applyBtn) applyBtn.disabled = !confirmBox.checked;
          }
        }
      });
    });
  });
});
