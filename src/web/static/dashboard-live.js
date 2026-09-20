// dashboard-live.js — живое обновление сводки через SSE (DASH-1).
//
// Подключается к /api/dashboard/stream (EventSource), патчит значения по
// атрибутам data-live, перерисовывает блоки задач и алертов готовым HTML с
// сервера (разметка живёт в шаблонах). При обрыве — переподключение с
// индикатором; если EventSource недоступен или рвётся трижды подряд —
// переходит на опрос /api/dashboard/summary.
(() => {
  "use strict";

  const indicator = document.getElementById("live-indicator");
  const root = document.querySelector('[data-live-root="summary"]');
  if (!indicator || !root) return; // не сводка — не мешаем другим страницам

  const textEl = document.getElementById("live-indicator-text");
  const STALE_MULTIPLIER = 3;
  const MAX_ERRORS = 3;

  let source = null;
  let pollingTimer = null;
  let interval = 10;
  let lastTs = 0;
  let errorStreak = 0;

  function setState(state, text) {
    indicator.dataset.state = state;
    if (textEl) textEl.textContent = text;
  }

  function patchDisplay(display) {
    if (!display) return;
    root.querySelectorAll("[data-live]").forEach((el) => {
      const key = el.dataset.live;
      const value = display[key];
      // Значение может отсутствовать (частичный ответ) — тогда не трогаем DOM.
      if (value !== undefined && value !== null) {
        el.textContent = String(value);
      }
    });
  }

  function patchApiBadge(flags, display) {
    const badge = document.getElementById("live-api-badge");
    if (!badge) return;
    if (display && display.api_health) badge.textContent = display.api_health;
    const ok = !!(flags && flags.api_ok);
    badge.classList.toggle("badge-ok", ok);
    badge.classList.toggle("badge-err", !ok);
  }

  // Форматирует значение с суффиксом; null/undefined — не трогаем DOM.
  function withSuffix(value, suffix) {
    if (value === undefined || value === null) return null;
    return `${value}${suffix}`;
  }

  function patchHtml(id, html) {
    const node = document.getElementById(id);
    if (node && typeof html === "string" && html) node.innerHTML = html;
  }

  function apply(payload) {
    if (!payload || payload.error) return;
    lastTs = Date.now();
    if (payload.interval) interval = payload.interval;
    patchDisplay(payload.display);
    patchApiBadge(payload.flags, payload.display);
    patchHtml("live-tasks", payload.tasks_html);
    patchHtml("live-alerts", payload.alerts_html);
    setState("live", "live");
  }

  async function pollOnce() {
    try {
      const resp = await fetch("/api/dashboard/summary", {
        headers: { Accept: "application/json" },
      });
      if (!resp.ok) throw new Error(String(resp.status));
      const data = await resp.json();
      const api = data.api_status || {};
      // JSON API отдаёт числа и секунды — приводим к тем же строкам, что в SSE.
      patchDisplay({
        uptime: data.uptime,
        total_users: data.total_users,
        total_patients: data.total_patients,
        total_monitored_doctors: data.total_monitored_doctors,
        active_monitorings: data.active_monitorings,
        doctors_discovered: data.doctors_discovered,
        api_checks: api.total_checks,
        api_errors: api.total_errors,
        api_availability: withSuffix(api.availability_pct, " %"),
        api_last_check: withSuffix(api.last_check_seconds_ago, " с назад"),
      });
      patchApiBadge(
        { api_ok: !!api.accessible },
        { api_health: api.accessible ? "Доступен" : "Недоступен" },
      );
      lastTs = Date.now();
      setState("polling", "опрос (SSE недоступен)");
    } catch (err) {
      setState("offline", "нет связи");
    }
  }

  function startPolling() {
    if (pollingTimer) return;
    pollOnce();
    pollingTimer = setInterval(pollOnce, Math.max(interval, 15) * 1000);
  }

  function startStream() {
    if (typeof window.EventSource !== "function") {
      startPolling();
      return;
    }
    try {
      source = new EventSource("/api/dashboard/stream");
    } catch (err) {
      startPolling();
      return;
    }

    source.onopen = () => {
      errorStreak = 0;
      setState("live", "live");
    };

    source.onmessage = (event) => {
      try {
        apply(JSON.parse(event.data));
      } catch (err) {
        /* мусорный кадр — игнорируем, следующий придёт через интервал */
      }
    };

    source.onerror = () => {
      errorStreak += 1;
      if (errorStreak >= MAX_ERRORS) {
        source.close();
        source = null;
        startPolling();
        return;
      }
      setState("reconnecting", "переподключение…");
    };
  }

  // Тикер: возраст данных в индикаторе и признак «протухания».
  setInterval(() => {
    if (!lastTs) return;
    const age = Math.round((Date.now() - lastTs) / 1000);
    if (age > interval * STALE_MULTIPLIER) {
      setState("stale", `данные устарели (${age} с)`);
    } else if (indicator.dataset.state === "live") {
      setState("live", `live · ${age} с назад`);
    }
  }, 1000);

  // Возврат во вкладку: если поток закрылся в фоне, переподключаемся сразу.
  document.addEventListener("visibilitychange", () => {
    if (document.hidden || pollingTimer) return;
    if (source && source.readyState === EventSource.CLOSED) {
      source = null;
    }
    if (!source) {
      errorStreak = 0;
      startStream();
    }
  });

  startStream();
})();
