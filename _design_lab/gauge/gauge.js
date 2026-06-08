/**
 * Gauge Widget — Canvas-виджет мониторинга для Telegram Mini App.
 *
 * 5 состояний: active, searching, paused, error, no_data.
 * Канвас 280×280 px (логические 140×140 для retina).
 * Анимация через requestAnimationFrame, morph-переходы между состояниями.
 *
 * Публичное API:
 *   window.renderGauge(canvas, state, options) — инициализация
 *   window.setState(newState)                  — переключение состояния
 *   window.getCurrentState()                   — текущее состояние
 *   window.updateOptions(opts)                 — частичное обновление options
 *
 * @license MIT
 * @version 1.0.0
 */

(function () {
  'use strict';

  // =========================================================================
  // Константы
  // =========================================================================

  /** Логический размер канваса (физический = логический × dpr). */
  var SIZE = 280;

  /** CSS-размер канваса (логические пиксели). */
  var DISPLAY_SIZE = 140;

  /** Толщина линии дуги. */
  var LINE_WIDTH = 7;

  /** Радиус дуги. */
  var RADIUS = 95;

  /** Центр канваса (смещён вверх для текста снизу). */
  var CX = 140;
  var CY = 130;

  /** Длительность morph-перехода между состояниями (мс). */
  var MORPH_DURATION = 300;

  /** Углы дуги в радианах: начало (135° = верхний левый), полный размах 270°. */
  var ARC_START = (135 * Math.PI) / 180; // 135° → радианы
  var ARC_SWEEP = (270 * Math.PI) / 180; // 270° → радианы

  /** Период осцилляции для active (мс). */
  var ACTIVE_OSCILLATION_PERIOD = 1500;

  /** Амплитуда осцилляции дуги active (радианы). */
  var ACTIVE_OSCILLATION_AMP = (10 * Math.PI) / 180;

  /** Период мигания error (мс). */
  var ERROR_BLINK_PERIOD = 800;

  /** Длина дуги-спиннера searching (радианы). */
  var SEARCHING_ARC_LENGTH = (80 * Math.PI) / 180;

  /** Скорость вращения спиннера (радиан/мс). */
  var SEARCHING_SPEED = 0.004;

  /** Размер дуги paused (радианы). */
  var PAUSED_ARC_LENGTH = (60 * Math.PI) / 180;

  /** Центр дуги paused (середина разрыва, снизу). */
  var PAUSED_ARC_CENTER = (270 * Math.PI) / 180;

  // =========================================================================
  // Глобальное состояние модуля
  // =========================================================================

  /** Текущее состояние виджета. */
  var currentState = 'no_data';

  /** Предыдущее состояние (для morph-перехода). */
  var previousState = 'no_data';

  /** Текущие опции рендеринга. */
  var currentOptions = {};

  /** Предыдущие опции (для morph-перехода). */
  var previousOptions = {};

  /** Флаг активного morph-перехода. */
  var morphing = false;

  /** Время начала morph-перехода (timestamp). */
  var morphStart = 0;

  /** Прогресс morph-перехода 0..1. */
  var morphProgress = 0;

  /** ID текущего requestAnimationFrame. */
  var animFrameId = null;

  /** Ссылка на canvas-элемент. */
  var canvasEl = null;

  /** 2D-контекст канваса. */
  var ctx = null;

  /** Физический размер канваса = SIZE × devicePixelRatio. */
  var physicalSize = SIZE;

  /** Время последнего кадра. */
  var lastTimestamp = 0;

  /** Накопленный угол для спиннера searching. */
  var searchingAngle = 0;

  // =========================================================================
  // Вспомогательные функции
  // =========================================================================

  /**
   * Линейная интерполяция.
   * @param {number} a - Начальное значение.
   * @param {number} b - Конечное значение.
   * @param {number} t - Прогресс 0..1.
   * @returns {number} Интерполированное значение.
   */
  function lerp(a, b, t) {
    return a + (b - a) * t;
  }

  /**
   * Ease-out кубическая функция для плавных переходов.
   * @param {number} t - Прогресс 0..1.
   * @returns {number} Сглаженный прогресс.
   */
  function easeOutCubic(t) {
    return 1 - Math.pow(1 - t, 3);
  }

  /**
   * Очистка канваса (прозрачный фон).
   * Координаты уже в логических пикселях после ctx.scale(dpr, dpr).
   */
  function clearCanvas() {
    ctx.clearRect(0, 0, SIZE, SIZE);
  }

  /**
   * Рисование фоновой (неактивной) дуги — тонкая серая направляющая.
   * Используется в active, paused, error.
   * @param {number} alpha - Прозрачность 0..1.
   */
  function drawBackgroundArc(alpha) {
    ctx.save();
    ctx.globalAlpha = alpha * 0.15;
    ctx.strokeStyle = '#ffffff';
    ctx.lineWidth = LINE_WIDTH;
    ctx.lineCap = 'round';
    ctx.beginPath();
    ctx.arc(CX, CY, RADIUS, ARC_START, ARC_START + ARC_SWEEP);
    ctx.stroke();
    ctx.restore();
  }

  /**
   * Рисование цветной дуги.
   * @param {string} color - CSS-цвет дуги.
   * @param {number} alpha - Прозрачность 0..1.
   * @param {number} startAngle - Начальный угол (радианы).
   * @param {number} endAngle - Конечный угол (радианы).
   * @param {number} [glow=false] - Добавить свечение.
   */
  function drawArc(color, alpha, startAngle, endAngle, glow) {
    ctx.save();
    ctx.globalAlpha = alpha;
    ctx.strokeStyle = color;
    ctx.lineWidth = LINE_WIDTH;
    ctx.lineCap = 'round';

    if (glow) {
      ctx.shadowColor = color;
      ctx.shadowBlur = 12;
    }

    ctx.beginPath();
    ctx.arc(CX, CY, RADIUS, startAngle, endAngle);
    ctx.stroke();
    ctx.restore();
  }

  /**
   * Рисование текста по центру канваса.
   * @param {string} text - Текст для отображения.
   * @param {string} color - CSS-цвет.
   * @param {number} alpha - Прозрачность.
   * @param {number} fontSize - Размер шрифта (px).
   * @param {string} [fontWeight='600'] - Толщина шрифта.
   */
  function drawCenterText(text, color, alpha, fontSize, fontWeight) {
    fontWeight = fontWeight || '600';
    ctx.save();
    ctx.globalAlpha = alpha;
    ctx.fillStyle = color;
    ctx.font =
      fontWeight +
      ' ' +
      fontSize +
      "px -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(text, CX, CY);
    ctx.restore();
  }

  /**
   * Рисование подписи под дугой.
   * @param {string} text - Текст подписи.
   * @param {string} color - CSS-цвет.
   * @param {number} alpha - Прозрачность.
   */
  function drawLabel(text, color, alpha) {
    ctx.save();
    ctx.globalAlpha = alpha;
    ctx.fillStyle = color;
    ctx.font =
      "400 13px -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillText(text, CX, CY + RADIUS + 16);
    ctx.restore();
  }

  /**
   * Рисование таймера «След. проверка: N сек».
   * @param {number} seconds - Количество секунд.
   * @param {number} alpha - Прозрачность.
   */
  function drawTimer(seconds, alpha) {
    var text = 'След. проверка: ' + seconds + ' сек';
    ctx.save();
    ctx.globalAlpha = alpha * 0.7;
    ctx.fillStyle = '#9ca3af';
    ctx.font =
      "400 11px -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillText(text, CX, CY + RADIUS + 34);
    ctx.restore();
  }

  // =========================================================================
  // Рендер-функции состояний
  // =========================================================================

  /**
   * Рендер состояния active: пульсирующая дуга 270°, счётчик слотов в центре.
   * @param {number} timestamp - Время кадра.
   * @param {number} alpha - Прозрачность (для morph).
   */
  function renderActive(timestamp, alpha) {
    var opts = currentOptions;
    var elapsed = timestamp % ACTIVE_OSCILLATION_PERIOD;
    var phase = elapsed / ACTIVE_OSCILLATION_PERIOD; // 0..1
    var oscillation = Math.sin(phase * Math.PI * 2) * ACTIVE_OSCILLATION_AMP;

    // Пульсация прозрачности дуги 0.6 → 1.0
    var pulseAlpha = 0.6 + 0.4 * ((Math.sin(phase * Math.PI * 2) + 1) / 2);

    // Конечный угол дуги осциллирует вокруг 270°
    var endAngle = ARC_START + ARC_SWEEP + oscillation;

    drawBackgroundArc(alpha);
    drawArc('#22c55e', alpha * pulseAlpha, ARC_START, endAngle, true);

    // Счётчик слотов
    var slots = opts.slotsCount !== undefined ? opts.slotsCount : 0;
    drawCenterText(String(slots), '#22c55e', alpha, 36, '700');

    // Подпись
    var label = opts.label || 'Мониторинг активен';
    drawLabel(label, '#e0e0e0', alpha);

    // Таймер
    if (opts.nextCheckIn !== undefined) {
      drawTimer(opts.nextCheckIn, alpha);
    }
  }

  /**
   * Рендер состояния searching: вращающаяся дуга-спиннер, текст «Поиск...».
   * @param {number} timestamp - Время кадра.
   * @param {number} alpha - Прозрачность.
   */
  function renderSearching(timestamp, alpha) {
    // Обновление угла спиннера с ease
    if (lastTimestamp > 0) {
      var dt = timestamp - lastTimestamp;
      searchingAngle += SEARCHING_SPEED * dt;
    }
    // Нормализация угла
    searchingAngle = searchingAngle % (Math.PI * 2);

    var startAngle = searchingAngle;
    var endAngle = startAngle + SEARCHING_ARC_LENGTH;

    drawBackgroundArc(alpha);
    drawArc('#3b82f6', alpha, startAngle, endAngle, true);

    // Текст «Поиск...»
    var label = currentOptions.label || 'Поиск...';
    drawCenterText(label, '#3b82f6', alpha, 16, '500');

    // Подсказка под дугой
    var hint = currentOptions.hint || 'Ищем доступные слоты';
    drawLabel(hint, '#9ca3af', alpha);
  }

  /**
   * Рендер состояния paused: статичная дуга ~60°, значок паузы.
   * @param {number} alpha - Прозрачность.
   */
  function renderPaused(alpha) {
    var halfSweep = PAUSED_ARC_LENGTH / 2;
    var startAngle = PAUSED_ARC_CENTER - halfSweep;
    var endAngle = PAUSED_ARC_CENTER + halfSweep;

    drawBackgroundArc(alpha);
    drawArc('#f59e0b', alpha, startAngle, endAngle, true);

    // Значок паузы ‖ (две вертикальные линии)
    var barWidth = 5;
    var barHeight = 22;
    var barGap = 8;
    var barY = CY - barHeight / 2;

    ctx.save();
    ctx.globalAlpha = alpha;
    ctx.fillStyle = '#f59e0b';
    ctx.fillRect(CX - barGap / 2 - barWidth, barY, barWidth, barHeight);
    ctx.fillRect(CX + barGap / 2, barY, barWidth, barHeight);
    ctx.restore();

    var label = currentOptions.label || 'Мониторинг на паузе';
    drawLabel(label, '#e0e0e0', alpha);
  }

  /**
   * Рендер состояния error: красная дуга, ✕ в центре, мигание.
   * @param {number} timestamp - Время кадра.
   * @param {number} alpha - Прозрачность.
   */
  function renderError(timestamp, alpha) {
    // Мигание с периодом ERROR_BLINK_PERIOD
    var blinkPhase = (timestamp % ERROR_BLINK_PERIOD) / ERROR_BLINK_PERIOD;
    var blinkAlpha = 0.3 + 0.7 * ((Math.sin(blinkPhase * Math.PI * 2) + 1) / 2);

    drawBackgroundArc(alpha);
    drawArc(
      '#ef4444',
      alpha * blinkAlpha,
      ARC_START,
      ARC_START + ARC_SWEEP,
      true
    );

    // Крестик ✕
    drawCenterText('✕', '#ef4444', alpha * blinkAlpha, 32, '600');

    var label = currentOptions.label || 'Ошибка мониторинга';
    drawLabel(label, '#ef4444', alpha * 0.8);
  }

  /**
   * Рендер состояния no_data: серая окружность, «—» в центре.
   * @param {number} alpha - Прозрачность.
   */
  function renderNoData(alpha) {
    // Полная окружность тонкой серой линией
    ctx.save();
    ctx.globalAlpha = alpha * 0.4;
    ctx.strokeStyle = '#6b7280';
    ctx.lineWidth = LINE_WIDTH * 0.7;
    ctx.lineCap = 'round';
    ctx.setLineDash([6, 6]);
    ctx.beginPath();
    ctx.arc(CX, CY, RADIUS, 0, Math.PI * 2);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.restore();

    // Прочерк в центре
    drawCenterText('—', '#6b7280', alpha, 28, '500');

    var label = currentOptions.label || 'Нет данных';
    drawLabel(label, '#9ca3af', alpha * 0.8);
  }

  // =========================================================================
  // Главный цикл анимации
  // =========================================================================

  /**
   * Главный цикл рендеринга через requestAnimationFrame.
   * Обрабатывает morph-переходы и делегирует рендер конкретному состоянию.
   * @param {number} timestamp - Время кадра от requestAnimationFrame.
   */
  function renderLoop(timestamp) {
    animFrameId = requestAnimationFrame(renderLoop);

    // Вычисление delta-time
    if (lastTimestamp === 0) {
      lastTimestamp = timestamp;
    }
    var dt = timestamp - lastTimestamp;
    lastTimestamp = timestamp;

    clearCanvas();

    // Обработка morph-перехода
    if (morphing) {
      var elapsed = timestamp - morphStart;
      if (elapsed >= MORPH_DURATION) {
        // Morph завершён
        morphing = false;
        morphProgress = 1;
        previousState = currentState;
        previousOptions = Object.assign({}, currentOptions);
      } else {
        morphProgress = easeOutCubic(Math.min(elapsed / MORPH_DURATION, 1));
        // Рендер старого состояния с затуханием
        var oldAlpha = 1 - morphProgress;
        var savedState = currentState;
        var savedOptions = currentOptions;

        currentState = previousState;
        currentOptions = previousOptions;
        renderState(timestamp, oldAlpha);

        currentState = savedState;
        currentOptions = savedOptions;
        // Рендер нового состояния с нарастанием
        var newAlpha = morphProgress;
        renderState(timestamp, newAlpha);
        return;
      }
    }

    // Обычный рендер текущего состояния
    renderState(timestamp, 1);
  }

  /**
   * Делегирует рендер конкретному состоянию.
   * @param {number} timestamp - Время кадра.
   * @param {number} alpha - Прозрачность (для morph).
   */
  function renderState(timestamp, alpha) {
    switch (currentState) {
      case 'active':
        renderActive(timestamp, alpha);
        break;
      case 'searching':
        renderSearching(timestamp, alpha);
        break;
      case 'paused':
        renderPaused(alpha);
        break;
      case 'error':
        renderError(timestamp, alpha);
        break;
      case 'no_data':
        renderNoData(alpha);
        break;
      default:
        renderNoData(alpha);
        break;
    }
  }

  /**
   * Запуск анимационного цикла (если ещё не запущен).
   */
  function startLoop() {
    if (animFrameId === null) {
      lastTimestamp = 0;
      searchingAngle = 0;
      animFrameId = requestAnimationFrame(renderLoop);
    }
  }

  /**
   * Остановка анимационного цикла.
   */
  function stopLoop() {
    if (animFrameId !== null) {
      cancelAnimationFrame(animFrameId);
      animFrameId = null;
    }
  }

  // =========================================================================
  // Публичное API
  // =========================================================================

  /**
   * Инициализация виджета на canvas-элементе.
   *
   * @param {HTMLCanvasElement} canvas - Canvas-элемент для рендеринга.
   * @param {string} state - Начальное состояние: 'active'|'searching'|'paused'|'error'|'no_data'.
   * @param {object} [opts] - Опции рендеринга.
   * @param {number} [opts.slotsCount] - Количество слотов (для active).
   * @param {string} [opts.label] - Текстовая метка под дугой.
   * @param {number} [opts.nextCheckIn] - Секунд до следующей проверки.
   * @param {string} [opts.hint] - Подсказка для searching.
   */
  window.renderGauge = function (canvas, state, opts) {
    if (!canvas) {
      console.warn('[gauge] renderGauge: canvas is null');
      return;
    }

    canvasEl = canvas;
    opts = opts || {};

    // Настройка retina
    var dpr = window.devicePixelRatio || 1;
    physicalSize = Math.floor(SIZE * dpr);

    canvas.width = physicalSize;
    canvas.height = physicalSize;
    canvas.style.width = DISPLAY_SIZE + 'px';
    canvas.style.height = DISPLAY_SIZE + 'px';

    ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);

    // Установка начального состояния
    currentState = state || 'no_data';
    previousState = currentState;
    currentOptions = Object.assign({}, opts);
    previousOptions = Object.assign({}, opts);
    morphing = false;

    // Запуск цикла анимации
    stopLoop();
    startLoop();
  };

  /**
   * Переключение состояния виджета с плавным morph-переходом.
   * @param {string} newState - Новое состояние.
   */
  window.setState = function (newState) {
    if (!canvasEl || !ctx) {
      console.warn(
        '[gauge] setState: gauge not initialized, call renderGauge first'
      );
      return;
    }

    if (newState === currentState && !morphing) {
      return; // Уже в этом состоянии
    }

    // Сохраняем текущее как предыдущее для morph
    previousState = currentState;
    previousOptions = Object.assign({}, currentOptions);

    // Устанавливаем новое состояние
    currentState = newState;

    // Запускаем morph
    morphing = true;
    morphStart = performance.now();
    morphProgress = 0;

    // Сброс угла спиннера при входе в searching
    if (newState === 'searching') {
      searchingAngle = 0;
    }
  };

  /**
   * Частичное обновление опций рендеринга (без morph-перехода).
   * @param {object} opts - Новые значения опций (сливаются с текущими).
   */
  window.updateOptions = function (opts) {
    if (!opts) return;
    Object.assign(currentOptions, opts);
  };

  /**
   * Возвращает текущее состояние виджета.
   * @returns {string} Текущее состояние.
   */
  window.getCurrentState = function () {
    return currentState;
  };

  /**
   * Возвращает признак активности morph-перехода.
   * @returns {boolean} true если morph активен.
   */
  window.isMorphing = function () {
    return morphing;
  };
})();
