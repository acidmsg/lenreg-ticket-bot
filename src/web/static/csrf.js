// CSRF для POST-запросов дашборда (DASH-10).
//
// Токен лежит в мета-теге страницы (привязан к сессии). Обёртка над fetch
// добавляет его ко всем небезопасным same-origin запросам, поэтому каждый
// скрипт страницы не обязан помнить про заголовок.
(function () {
  var meta = document.querySelector('meta[name="csrf-token"]');
  var token = meta ? meta.getAttribute("content") : "";
  if (!token || typeof window.fetch !== "function") return;

  var originalFetch = window.fetch.bind(window);
  var SAFE = ["GET", "HEAD", "OPTIONS"];

  window.fetch = function (input, init) {
    var options = init || {};
    var method = (options.method || "GET").toUpperCase();
    if (SAFE.indexOf(method) !== -1) return originalFetch(input, options);

    var target = typeof input === "string" ? input : input.url;
    var sameOrigin =
      target.indexOf("http") !== 0 ||
      target.indexOf(window.location.origin) === 0;

    if (sameOrigin) {
      options.headers = Object.assign({}, options.headers, {
        "X-CSRF-Token": token,
      });
    }
    return originalFetch(input, options);
  };
})();
