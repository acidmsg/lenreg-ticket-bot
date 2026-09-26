/**
 * Поллинг состояния списков Mini App.
 *
 * Единая механика фонового обновления: интервал, экспоненциальный backoff при
 * ошибках, пауза при скрытом WebView и мгновенный запрос при возврате в него.
 * Модуль не знает про сеть — задача передаётся снаружи колбэком.
 *
 * @module utils/polling
 */

/** @type {Set<{stop: function(): void}>} */
const activePollers = new Set();

/**
 * Запускает периодическое выполнение задачи.
 *
 * Задача может быть асинхронной. При ошибке интервал умножается на
 * `backoffFactor` (но не больше `maxIntervalMs`), при успехе — сбрасывается к
 * базовому. Пока документ скрыт, тики пропускаются; возврат во вкладку/WebView
 * выполняется немедленно, без ожидания остатка интервала.
 *
 * @param {function(): (void|Promise<void>)} task — задача одного тика
 * @param {object} [options] — параметры поллинга
 * @param {number} [options.intervalMs=45000] — базовый интервал, мс
 * @param {number} [options.maxIntervalMs=300000] — верхняя граница интервала, мс
 * @param {number} [options.backoffFactor=2] — множитель интервала при ошибке
 * @returns {{stop: function(): void}} дескриптор поллера
 */
export function startPolling(
  task,
  { intervalMs = 45000, maxIntervalMs = 300000, backoffFactor = 2 } = {},
) {
  let stopped = false;
  let timer = null;
  let currentInterval = intervalMs;

  const clearTimer = () => {
    if (timer !== null) {
      clearTimeout(timer);
      timer = null;
    }
  };

  const schedule = (delay) => {
    clearTimer();
    if (stopped) return;
    timer = setTimeout(tick, delay);
  };

  async function tick() {
    if (stopped) return;
    if (isHidden()) {
      schedule(intervalMs);
      return;
    }
    try {
      await task();
      currentInterval = intervalMs;
      schedule(currentInterval);
    } catch {
      currentInterval = Math.min(currentInterval * backoffFactor, maxIntervalMs);
      schedule(currentInterval);
    }
  }

  function handleVisibility() {
    if (stopped || isHidden()) return;
    currentInterval = intervalMs;
    schedule(0);
  }

  if (hasDocument()) {
    document.addEventListener("visibilitychange", handleVisibility);
  }

  schedule(intervalMs);

  const handle = {
    stop() {
      if (stopped) return;
      stopped = true;
      clearTimer();
      if (hasDocument()) {
        document.removeEventListener("visibilitychange", handleVisibility);
      }
      activePollers.delete(handle);
    },
  };

  activePollers.add(handle);
  return handle;
}

/**
 * Останавливает все запущенные поллеры.
 *
 * Вызывается роутером перед сменой экрана: ушедшая вьюха не должна продолжать
 * дёргать API и обновлять отсутствующий в DOM контейнер.
 */
export function stopAllPollers() {
  for (const poller of [...activePollers]) {
    poller.stop();
  }
}

/**
 * Проверяет, что документ скрыт (WebView свёрнут или ушёл в фон).
 *
 * @returns {boolean} true, если тики нужно пропускать
 */
function isHidden() {
  return hasDocument() && document.hidden === true;
}

/**
 * Проверяет доступность `document` (модуль тестируется и вне браузера).
 *
 * @returns {boolean} true, если `document` доступен
 */
function hasDocument() {
  return typeof document !== "undefined" && document !== null;
}
