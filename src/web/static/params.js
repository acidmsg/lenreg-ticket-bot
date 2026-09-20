/**
 * Страница «Параметры» (DASH-3): сохранение параметров конфигурации.
 *
 * Формы отправляются в POST /api/config/{key}; ответ сервера определяет
 * статус строки. Ошибки валидации показываются текстом, без перезагрузки.
 */
(function () {
  "use strict";

  /**
   * Показывает статус операции рядом с формой параметра.
   *
   * @param {string} key Ключ параметра.
   * @param {string} text Текст статуса.
   * @param {boolean|null} ok true — успех, false — ошибка, null — в процессе.
   */
  function setStatus(key, text, ok) {
    var el = document.querySelector('[data-param-status="' + key + '"]');
    if (!el) return;
    el.textContent = text;
    el.classList.toggle("badge-ok", ok === true);
    el.classList.toggle("badge-err", ok === false);
  }

  document.querySelectorAll("form.param-form").forEach(function (form) {
    form.addEventListener("submit", async function (event) {
      event.preventDefault();
      var key = form.dataset.paramKey;
      var input = form.querySelector("input[name='value']");
      if (!key || !input) return;

      setStatus(key, "Сохранение…", null);

      try {
        var response = await fetch("/api/config/" + encodeURIComponent(key), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ value: input.value }),
        });
        var data = await response.json().catch(function () {
          return {};
        });

        if (!response.ok) {
          setStatus(key, data.detail || "Ошибка " + response.status, false);
          return;
        }

        // Секрет не держим в DOM после успешной записи: поле очищается,
        // чтобы значение не осталось на экране до перезагрузки страницы.
        if (input.type === "password") {
          input.value = "";
        }

        var valueEl = document.querySelector(
          '[data-param-value="' + key + '"]',
        );
        if (valueEl) valueEl.textContent = data.value;

        var sourceEl = document.querySelector(
          '[data-param-source="' + key + '"]',
        );
        if (sourceEl) {
          sourceEl.textContent = data.source;
          sourceEl.classList.add("badge-ok");
        }

        var warnings = (data.warnings || []).join("; ");
        setStatus(
          key,
          "Сохранено (" +
            data.applied +
            ")" +
            (warnings ? ": " + warnings : ""),
          true,
        );
      } catch (error) {
        setStatus(key, "Сеть недоступна: " + error, false);
      }
    });
  });
})();
