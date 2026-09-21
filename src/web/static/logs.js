/* Страница «Логи»: режим «следить» — дочитывает новые строки и кладёт их сверху. */
(() => {
  const toggle = document.getElementById("follow-toggle");
  const body = document.getElementById("logs-body");
  const status = document.getElementById("logs-status");
  if (!toggle || !body) return;

  const POLL_MS = 3000;
  let offset = Number(body.dataset.offset || 0);
  let timer = null;
  let busy = false;

  // Фильтры страницы переносим в запрос: иначе «следить» подмешивало бы
  // строки, которые пользователь отфильтровал (уровень, источник, поиск).
  function filters() {
    const page = new URLSearchParams(window.location.search);
    const forwarded = new URLSearchParams();
    for (const key of ["level", "source", "q"]) {
      const value = page.get(key);
      if (value) forwarded.set(key, value);
    }
    return forwarded;
  }

  function cell(label, text, extraClass) {
    const node = document.createElement("div");
    node.className = extraClass ? `dg-cell ${extraClass}` : "dg-cell";
    node.setAttribute("role", "cell");
    node.dataset.label = label;
    node.textContent = text;
    return node;
  }

  function makeRow(record) {
    const row = document.createElement("div");
    row.className = "dg-row";
    row.setAttribute("role", "row");
    row.append(cell("Время", record.ts, "cell-nowrap"));

    const levelCell = document.createElement("div");
    levelCell.className = "dg-cell";
    levelCell.setAttribute("role", "cell");
    levelCell.dataset.label = "Уровень";
    const badge = document.createElement("span");
    badge.className = `level level--${record.level.toLowerCase()}`;
    badge.textContent = record.level;
    levelCell.append(badge);
    row.append(levelCell);

    row.append(cell("Источник", record.source));
    row.append(cell("Сообщение", record.message, "log-message"));
    return row;
  }

  async function tick() {
    // Предыдущий запрос ещё не вернулся — второй с той же позицией
    // задвоил бы строки в таблице.
    if (busy) return;
    busy = true;
    try {
      const url = new URL("/api/logs/tail", window.location.origin);
      url.searchParams.set("after", offset);
      for (const [key, value] of filters()) url.searchParams.set(key, value);

      const response = await fetch(url);
      const data = await response.json();
      offset = data.offset;
      // Записи приходят от старых к новым, а prepend кладёт следующую выше —
      // поэтому вставляем в исходном порядке, и новые строки оказываются сверху.
      for (const record of data.records) {
        body.prepend(makeRow(record));
      }
      if (data.records.length && status) {
        status.textContent = `следом подгружено ${data.records.length} строк`;
      }
    } catch (error) {
      if (status) status.textContent = "слежение прервано: нет ответа";
      toggle.checked = false;
      stop();
    } finally {
      busy = false;
    }
  }

  function stop() {
    if (timer) clearInterval(timer);
    timer = null;
  }

  toggle.addEventListener("change", () => {
    if (toggle.checked) {
      tick();
      timer = setInterval(tick, POLL_MS);
    } else {
      stop();
    }
  });
})();
