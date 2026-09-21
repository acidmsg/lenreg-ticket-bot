/* Страница «Логи»: компактная витрина.
   Фильтры применяются сразу, старые записи подгружаются при прокрутке,
   режим «следить» дочитывает новые строки сверху. */
(() => {
  const form = document.getElementById("logs-filter");
  const body = document.getElementById("logs-body");
  const status = document.getElementById("logs-status");
  const hint = document.getElementById("logs-hint");
  const empty = document.getElementById("logs-empty");
  const sentinel = document.getElementById("logs-sentinel");
  const toggle = document.getElementById("follow-toggle");
  if (!form || !body) return;

  document.documentElement.classList.add("js");

  const POLL_MS = 3000;
  const limit = Number(body.dataset.limit || 200);
  const rowsUrl = body.dataset.rowsUrl;
  const tailUrl = body.dataset.tailUrl;

  let loaded = Number(body.dataset.loaded || 0);
  let hasMore = body.dataset.hasMore === "true";
  let tailOffset = Number(body.dataset.tailOffset || 0);
  let loading = false;
  let pendingReload = false;
  let followTimer = null;
  let followBusy = false;
  let searchTimer = null;

  function query() {
    const params = new URLSearchParams();
    for (const [key, value] of new FormData(form)) {
      if (String(value).trim()) params.append(key, value);
    }
    params.set("limit", limit);
    return params;
  }

  function setStatus(text) {
    if (hint) hint.textContent = text || "";
  }

  function updateEmpty() {
    if (!empty) return;
    empty.hidden = body.querySelector(".log-row") !== null;
  }

  function counts() {
    return body.querySelectorAll(".log-row").length;
  }

  /* Позиция в файле приходит с каждым ответом: после перезагрузки списка
     слежение должно стартовать с конца файла, а не с устаревшей позиции. */
  function syncTailOffset(response) {
    const next = response.headers.get("X-Log-Offset");
    if (next === null) return;
    tailOffset = Number(next);
    body.dataset.tailOffset = String(tailOffset);
  }

  /* ── Фильтры: применяются без кнопки ───────────────────────── */

  async function reload() {
    if (loading) {
      // Фильтр переключили во время запроса — повторим после него.
      pendingReload = true;
      return;
    }
    loading = true;
    setStatus("обновляю…");
    try {
      const params = query();
      const response = await fetch(`${rowsUrl}?${params}`);
      syncTailOffset(response);
      body.innerHTML = await response.text();
      loaded = counts();
      hasMore = loaded >= limit;
      body.dataset.loaded = String(loaded);
      body.dataset.hasMore = hasMore ? "true" : "false";
      history.replaceState(null, "", `/logs?${params}`);
      if (status) status.textContent = `показано ${loaded}`;
      setStatus(hasMore ? "" : "это все записи по фильтру");
      updateEmpty();
    } catch (error) {
      setStatus("не удалось обновить список");
    } finally {
      loading = false;
      if (pendingReload) {
        pendingReload = false;
        reload();
      }
    }
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    reload();
  });
  form.addEventListener("change", (event) => {
    if (event.target === toggle) return;
    reload();
  });

  const search = form.querySelector('input[name="q"]');
  if (search) {
    search.addEventListener("input", () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(reload, 350);
    });
  }

  /* ── Динамическая подгрузка старых записей ─────────────────── */

  async function loadMore() {
    if (!hasMore || loading) return;
    loading = true;
    try {
      const params = query();
      params.set("offset", String(loaded));
      const response = await fetch(`${rowsUrl}?${params}`);
      syncTailOffset(response);
      const html = await response.text();
      body.insertAdjacentHTML("beforeend", html);
      const added = counts() - loaded;
      loaded += added;
      hasMore = added >= limit;
      body.dataset.loaded = String(loaded);
      body.dataset.hasMore = hasMore ? "true" : "false";
      if (!hasMore) setStatus("это все записи по фильтру");
    } catch (error) {
      setStatus("подгрузка прервана");
    } finally {
      loading = false;
      updateEmpty();
    }
  }

  if (sentinel && "IntersectionObserver" in window) {
    new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) loadMore();
      },
      { rootMargin: "300px" },
    ).observe(sentinel);
  }

  /* ── Разворот длинного сообщения по клику ──────────────────── */

  body.addEventListener("click", (event) => {
    const row = event.target.closest(".log-row");
    if (row) row.classList.toggle("log-row--open");
  });

  /* ── Режим «следить» ───────────────────────────────────────── */

  async function tick() {
    // Пока идёт перезагрузка списка, дочитывать нечего: строки уже перезапишутся.
    if (followBusy || loading) return;
    followBusy = true;
    try {
      const params = query();
      params.delete("limit");
      params.set("after", String(tailOffset));
      const response = await fetch(`${tailUrl}?${params}`);
      const html = await response.text();
      const rotated = response.headers.get("X-Log-Rotated") === "1";
      syncTailOffset(response);
      if (rotated) {
        await reload();
      } else if (html.trim()) {
        if (!loading) {
          body.insertAdjacentHTML("afterbegin", html);
          loaded = counts();
          updateEmpty();
          if (status) status.textContent = `показано ${loaded}`;
        }
      }
    } catch (error) {
      setStatus("слежение прервано: нет ответа");
      toggle.checked = false;
      stopFollow();
    } finally {
      followBusy = false;
    }
  }

  function stopFollow() {
    if (followTimer) clearInterval(followTimer);
    followTimer = null;
  }

  toggle.addEventListener("change", () => {
    if (toggle.checked) {
      tick();
      followTimer = setInterval(tick, POLL_MS);
    } else {
      stopFollow();
    }
  });

  updateEmpty();
})();
