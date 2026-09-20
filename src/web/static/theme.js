// Тема дашборда (DASH-9).
//
// Выбор хранится в localStorage и применяется до первой отрисовки: скрипт
// подключён в <head>, поэтому страница не мигает тёмной темой при загрузке
// светлой. Без сохранённого выбора берётся системная настройка.
(function () {
  var STORAGE_KEY = "dashboard-theme";

  function storedTheme() {
    try {
      return localStorage.getItem(STORAGE_KEY);
    } catch (error) {
      return null;
    }
  }

  function systemTheme() {
    if (
      window.matchMedia &&
      window.matchMedia("(prefers-color-scheme: light)").matches
    ) {
      return "light";
    }
    return "dark";
  }

  function apply(theme) {
    document.documentElement.dataset.theme = theme;
    var button = document.getElementById("theme-toggle");
    if (button) {
      button.textContent = theme === "light" ? "🌙" : "☀️";
      button.setAttribute(
        "aria-label",
        theme === "light" ? "Включить тёмную тему" : "Включить светлую тему",
      );
    }
  }

  apply(storedTheme() || systemTheme());

  document.addEventListener("DOMContentLoaded", function () {
    var button = document.getElementById("theme-toggle");
    if (!button) return;
    apply(
      storedTheme() || document.documentElement.dataset.theme || systemTheme(),
    );
    button.addEventListener("click", function () {
      var next =
        document.documentElement.dataset.theme === "light" ? "dark" : "light";
      try {
        localStorage.setItem(STORAGE_KEY, next);
      } catch (error) {
        // Приватный режим: тема просто не запомнится.
      }
      apply(next);
    });
  });
})();
