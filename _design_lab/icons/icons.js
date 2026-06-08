/**
 * Icons Design Lab — 44 иконки проекта zdrav.lenreg, отрисованные на Canvas.
 * 10 стилевых вариаций, минималистичный геометрический стиль.
 *
 * Все координаты в системе сетки 24×24. Масштабирование через size/24.
 * Физические пиксели: size × dpr; CSS-размер: size px.
 *
 * Паттерн отрисовки:
 *   ctx.save() → applyStyle() → ctx.beginPath() → draw → fill/stroke → ctx.restore()
 *   Каждый цвет/стиль — в своём save/restore блоке.
 *
 * Публичное API:
 *   window.IconDrawers       — объект с функциями отрисовки (44 шт.)
 *   window.IconStyles        — объект с 10 стилями
 *   window.IconHelpers       — хелперы (applyStyle, drawRoundedRect, etc.)
 *   window.ICON_LIST         — массив [{id, name, group, fn}] всех иконок
 *   window.ICON_GROUPS       — объект с группами иконок
 *
 * @license MIT
 * @version 1.1.0
 */

(function () {
  'use strict';

  // =========================================================================
  // Константы сетки 24×24
  // =========================================================================

  /** Размер сетки (логические пиксели). */
  var GRID = 24;

  // =========================================================================
  // Хелпер-функции
  // =========================================================================

  /**
   * Применить стиль к контексту Canvas (без save/restore).
   * @param {CanvasRenderingContext2D} ctx - 2D-контекст.
   * @param {object} style - Объект стиля.
   * @param {number} s - Масштабный коэффициент (size/GRID).
   */
  function applyStyle(ctx, style, s) {
    ctx.strokeStyle = style.stroke || 'transparent';
    ctx.fillStyle = style.fill || 'transparent';
    ctx.lineWidth = (style.strokeWidth || 1.5) * s;
    ctx.lineCap = style.lineCap || 'butt';
    ctx.lineJoin = style.lineJoin || 'miter';

    if (style.shadowBlur && style.shadowColor) {
      ctx.shadowBlur = style.shadowBlur * s;
      ctx.shadowColor = style.shadowColor;
    } else {
      ctx.shadowBlur = 0;
      ctx.shadowColor = 'transparent';
    }

    if (style.dashPattern) {
      ctx.setLineDash(
        style.dashPattern.map(function (v) {
          return v * s;
        })
      );
    } else {
      ctx.setLineDash([]);
    }
  }

  /**
   * Применить акцентный стиль (для duotone).
   * @param {CanvasRenderingContext2D} ctx - 2D-контекст.
   * @param {object} style - Объект стиля.
   * @param {number} s - Масштабный коэффициент.
   */
  function applyAccentStyle(ctx, style, s) {
    ctx.strokeStyle = style.accentStroke || style.stroke || 'transparent';
    ctx.fillStyle = style.accentFill || style.fill || 'transparent';
    ctx.lineWidth = (style.strokeWidth || 1.5) * s;
    ctx.lineCap = style.lineCap || 'butt';
    ctx.lineJoin = style.lineJoin || 'miter';
    ctx.shadowBlur = 0;
    ctx.shadowColor = 'transparent';
    ctx.setLineDash([]);
  }

  /**
   * Завершить путь: fill (если есть) + stroke (если есть).
   * @param {CanvasRenderingContext2D} ctx - 2D-контекст.
   * @param {object} style - Объект стиля.
   */
  function fillAndStroke(ctx, style) {
    if (style.fill && style.fill !== 'none') {
      ctx.fill();
    }
    if (style.stroke && style.stroke !== 'none') {
      ctx.stroke();
    }
  }

  /**
   * Скруглённый прямоугольник через moveTo/lineTo/arcTo.
   * @param {CanvasRenderingContext2D} ctx - 2D-контекст.
   * @param {number} x - Левый верхний X.
   * @param {number} y - Левый верхний Y.
   * @param {number} w - Ширина.
   * @param {number} h - Высота.
   * @param {number} r - Радиус скругления.
   */
  function drawRoundedRect(ctx, x, y, w, h, r) {
    r = Math.min(r, w / 2, h / 2);
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.lineTo(x + w - r, y);
    ctx.arcTo(x + w, y, x + w, y + r, r);
    ctx.lineTo(x + w, y + h - r);
    ctx.arcTo(x + w, y + h, x + w - r, y + h, r);
    ctx.lineTo(x + r, y + h);
    ctx.arcTo(x, y + h, x, y + h - r, r);
    ctx.lineTo(x, y + r);
    ctx.arcTo(x, y, x + r, y, r);
    ctx.closePath();
  }

  /**
   * Нарисовать и заполнить прямоугольник со скруглением одним вызовом.
   * @param {CanvasRenderingContext2D} ctx - 2D-контекст.
   * @param {number} x - Левый верхний X.
   * @param {number} y - Левый верхний Y.
   * @param {number} w - Ширина.
   * @param {number} h - Высота.
   * @param {number} r - Радиус скругления.
   * @param {object} style - Объект стиля.
   */
  function roundedRect(ctx, x, y, w, h, r, style) {
    drawRoundedRect(ctx, x, y, w, h, r);
    fillAndStroke(ctx, style);
  }

  // =========================================================================
  // Определения 10 стилей
  // =========================================================================

  var STYLES = {
    /** Стиль 1: Outline Thin — лёгкий контурный. */
    outline_thin: {
      name: 'Outline Thin',
      stroke: '#334155',
      fill: 'none',
      strokeWidth: 1.5,
      cornerRadius: 2,
      lineCap: 'butt',
      lineJoin: 'miter',
      shadowBlur: 0,
      shadowColor: null,
      dashPattern: null,
      bgFill: null,
      bgRadius: 0,
      accentStroke: null,
      accentFill: null
    },

    /** Стиль 2: Outline Bold — жирный, уверенный. */
    outline_bold: {
      name: 'Outline Bold',
      stroke: '#0f172a',
      fill: 'none',
      strokeWidth: 2.5,
      cornerRadius: 3,
      lineCap: 'round',
      lineJoin: 'round',
      shadowBlur: 0,
      shadowColor: null,
      dashPattern: null,
      bgFill: null,
      bgRadius: 0,
      accentStroke: null,
      accentFill: null
    },

    /** Стиль 3: Filled Solid — силуэтный. */
    filled_solid: {
      name: 'Filled Solid',
      stroke: 'none',
      fill: '#334155',
      strokeWidth: 0,
      cornerRadius: 2,
      lineCap: 'butt',
      lineJoin: 'miter',
      shadowBlur: 0,
      shadowColor: null,
      dashPattern: null,
      bgFill: null,
      bgRadius: 0,
      accentStroke: null,
      accentFill: null
    },

    /** Стиль 4: Filled Soft — мягкий, пастельный. */
    filled_soft: {
      name: 'Filled Soft',
      stroke: '#64748b',
      fill: '#cbd5e1',
      strokeWidth: 1,
      cornerRadius: 2,
      lineCap: 'butt',
      lineJoin: 'miter',
      shadowBlur: 0,
      shadowColor: null,
      dashPattern: null,
      bgFill: null,
      bgRadius: 0,
      accentStroke: null,
      accentFill: null
    },

    /** Стиль 5: Duotone Blue-Orange — двухцветный. */
    duotone_blue_orange: {
      name: 'Duotone Blue-Orange',
      stroke: '#2563eb',
      fill: 'rgba(37, 99, 235, 0.15)',
      strokeWidth: 2,
      cornerRadius: 3,
      lineCap: 'round',
      lineJoin: 'round',
      shadowBlur: 0,
      shadowColor: null,
      dashPattern: null,
      bgFill: null,
      bgRadius: 0,
      accentStroke: '#ea580c',
      accentFill: 'rgba(234, 88, 12, 0.15)'
    },

    /** Стиль 6: Neon — свечение для тёмного фона. */
    neon: {
      name: 'Neon',
      stroke: '#22d3ee',
      fill: 'rgba(34, 211, 238, 0.12)',
      strokeWidth: 2,
      cornerRadius: 3,
      lineCap: 'round',
      lineJoin: 'round',
      shadowBlur: 6,
      shadowColor: '#22d3ee',
      dashPattern: null,
      bgFill: null,
      bgRadius: 0,
      accentStroke: null,
      accentFill: null
    },

    /** Стиль 7: Rounded Bold — дружелюбный. */
    rounded_bold: {
      name: 'Rounded Bold',
      stroke: '#7c3aed',
      fill: 'rgba(124, 58, 237, 0.08)',
      strokeWidth: 3,
      cornerRadius: 6,
      lineCap: 'round',
      lineJoin: 'round',
      shadowBlur: 0,
      shadowColor: null,
      dashPattern: null,
      bgFill: null,
      bgRadius: 0,
      accentStroke: null,
      accentFill: null
    },

    /** Стиль 8: Geometric Sharp — строгий, технический. */
    geometric_sharp: {
      name: 'Geometric Sharp',
      stroke: '#1e293b',
      fill: 'none',
      strokeWidth: 2,
      cornerRadius: 1,
      lineCap: 'square',
      lineJoin: 'miter',
      shadowBlur: 0,
      shadowColor: null,
      dashPattern: null,
      bgFill: null,
      bgRadius: 0,
      accentStroke: null,
      accentFill: null
    },

    /** Стиль 9: Minimal Dot — пунктир, «водяной знак». */
    minimal_dot: {
      name: 'Minimal Dot',
      stroke: '#94a3b8',
      fill: 'none',
      strokeWidth: 1,
      cornerRadius: 2,
      lineCap: 'butt',
      lineJoin: 'miter',
      shadowBlur: 0,
      shadowColor: null,
      dashPattern: [1.5, 2.5],
      bgFill: null,
      bgRadius: 0,
      accentStroke: null,
      accentFill: null
    },

    /** Стиль 10: Dark Inverse — светлые иконки на тёмном фоне. */
    dark_inverse: {
      name: 'Dark Inverse',
      stroke: '#e2e8f0',
      fill: 'none',
      strokeWidth: 1.5,
      cornerRadius: 2,
      lineCap: 'butt',
      lineJoin: 'miter',
      shadowBlur: 0,
      shadowColor: null,
      dashPattern: null,
      bgFill: '#1e293b',
      bgRadius: 4,
      accentStroke: null,
      accentFill: null
    }
  };

  // =========================================================================
  // Функции отрисовки иконок
  // =========================================================================
  // Каждая функция: (ctx, cx, cy, size, style)
  // Использует save/restore для изоляции стилей.
  // =========================================================================

  var s = 1; // масштаб, устанавливается в каждой функции

  // -------------------------------------------------------------------------
  // Группа: Люди (people)
  // -------------------------------------------------------------------------

  function drawPatient(ctx, cx, cy, size, style) {
    s = size / GRID;
    ctx.save();
    applyStyle(ctx, style, s);
    ctx.beginPath();
    ctx.arc(cx, cy - 4 * s, 3.5 * s, 0, Math.PI * 2);
    ctx.arc(cx, cy + 5.5 * s, 6 * s, Math.PI, 0, false);
    fillAndStroke(ctx, style);
    ctx.restore();
  }

  function drawDoctor(ctx, cx, cy, size, style) {
    s = size / GRID;
    // Силуэт человека
    ctx.save();
    applyStyle(ctx, style, s);
    ctx.beginPath();
    ctx.arc(cx, cy - 4 * s, 3.5 * s, 0, Math.PI * 2);
    ctx.arc(cx, cy + 5.5 * s, 6 * s, Math.PI, 0, false);
    fillAndStroke(ctx, style);
    ctx.restore();

    // Медицинский крест (акцент для duotone)
    ctx.save();
    if (style.accentStroke) {
      applyAccentStyle(ctx, style, s);
    } else {
      applyStyle(ctx, style, s);
    }
    var kx = cx + 6 * s;
    var ky = cy - 7 * s;
    var kw = 1.5 * s;
    var kh = 6 * s;
    ctx.fillStyle = ctx.strokeStyle;
    ctx.fillRect(kx - kw / 2, ky, kw, kh);
    var khh = 4 * s;
    ctx.fillRect(kx - khh / 2, ky + (kh - kw) / 2, khh, kw);
    ctx.restore();
  }

  function drawClinic(ctx, cx, cy, size, style) {
    s = size / GRID;
    // Здание
    ctx.save();
    applyStyle(ctx, style, s);
    roundedRect(
      ctx,
      cx - 7 * s,
      cy - 2 * s,
      14 * s,
      10 * s,
      style.cornerRadius * s,
      style
    );
    ctx.restore();

    // Крыша
    ctx.save();
    applyStyle(ctx, style, s);
    ctx.beginPath();
    ctx.moveTo(cx - 9 * s, cy - 2 * s);
    ctx.lineTo(cx, cy - 9 * s);
    ctx.lineTo(cx + 9 * s, cy - 2 * s);
    ctx.closePath();
    fillAndStroke(ctx, style);
    ctx.restore();

    // Крест внутри
    ctx.save();
    if (style.accentStroke) {
      applyAccentStyle(ctx, style, s);
    } else {
      applyStyle(ctx, style, s);
    }
    var cw2 = 1.2 * s;
    var ch2 = 5 * s;
    ctx.fillStyle = ctx.strokeStyle;
    ctx.fillRect(cx - cw2 / 2, cy + 2 * s - ch2 / 2, cw2, ch2);
    ctx.fillRect(cx - ch2 / 2, cy + 2 * s - cw2 / 2, ch2, cw2);
    ctx.restore();

    // Дверь
    ctx.save();
    applyStyle(ctx, style, s);
    var doorW = 4 * s;
    var doorH = 4 * s;
    if (style.fill && style.fill !== 'none') {
      ctx.fillStyle = ctx.strokeStyle;
      ctx.fillRect(cx - doorW / 2, cy + 4 * s, doorW, doorH);
    } else {
      ctx.strokeRect(cx - doorW / 2, cy + 4 * s, doorW, doorH);
    }
    ctx.restore();
  }

  function drawSpecialty(ctx, cx, cy, size, style) {
    s = size / GRID;
    ctx.save();
    applyStyle(ctx, style, s);

    // База
    ctx.beginPath();
    ctx.moveTo(cx - 8 * s, cy + 8 * s);
    ctx.lineTo(cx + 4 * s, cy + 8 * s);
    ctx.stroke();

    // Стойка
    ctx.beginPath();
    ctx.moveTo(cx - 2 * s, cy + 8 * s);
    ctx.lineTo(cx - 2 * s, cy - 4 * s);
    ctx.stroke();

    // Тубус
    ctx.beginPath();
    ctx.moveTo(cx - 2 * s, cy - 4 * s);
    ctx.lineTo(cx + 5 * s, cy - 6 * s);
    ctx.stroke();

    // Линза
    ctx.beginPath();
    ctx.arc(cx + 5 * s, cy - 6 * s, 3 * s, 0, Math.PI * 2);
    fillAndStroke(ctx, style);

    // Предметный столик
    ctx.fillStyle = ctx.strokeStyle;
    ctx.fillRect(cx - 6 * s, cy + 2 * s, 8 * s, 1.5 * s);

    ctx.restore();
  }

  // -------------------------------------------------------------------------
  // Группа: Пользователи (users)
  // -------------------------------------------------------------------------

  function drawUsers(ctx, cx, cy, size, style) {
    s = size / GRID;
    ctx.save();
    applyStyle(ctx, style, s);

    // Задний силуэт
    ctx.beginPath();
    ctx.arc(cx - 4 * s, cy - 5.5 * s, 2.8 * s, 0, Math.PI * 2);
    ctx.arc(cx - 4 * s, cy + 2 * s, 4.5 * s, Math.PI, 0, false);
    fillAndStroke(ctx, style);

    // Передний силуэт
    ctx.beginPath();
    ctx.arc(cx + 3 * s, cy - 3.5 * s, 2.8 * s, 0, Math.PI * 2);
    ctx.arc(cx + 3 * s, cy + 3.5 * s, 4.5 * s, Math.PI, 0, false);
    fillAndStroke(ctx, style);

    ctx.restore();
  }

  function drawPersonShrug(ctx, cx, cy, size, style) {
    s = size / GRID;
    ctx.save();
    applyStyle(ctx, style, s);

    // Голова
    ctx.beginPath();
    ctx.arc(cx, cy - 5 * s, 3 * s, 0, Math.PI * 2);
    fillAndStroke(ctx, style);

    // Тело
    ctx.beginPath();
    ctx.moveTo(cx, cy - 2 * s);
    ctx.lineTo(cx, cy + 5 * s);
    ctx.stroke();

    // Левая рука
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(cx - 7 * s, cy - 6 * s);
    ctx.stroke();

    // Правая рука
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(cx + 7 * s, cy - 6 * s);
    ctx.stroke();

    // Левая нога
    ctx.beginPath();
    ctx.moveTo(cx, cy + 5 * s);
    ctx.lineTo(cx - 3 * s, cy + 9 * s);
    ctx.stroke();

    // Правая нога
    ctx.beginPath();
    ctx.moveTo(cx, cy + 5 * s);
    ctx.lineTo(cx + 3 * s, cy + 9 * s);
    ctx.stroke();

    ctx.restore();
  }

  // -------------------------------------------------------------------------
  // Группа: Статусы (status)
  // -------------------------------------------------------------------------

  function drawSuccess(ctx, cx, cy, size, style) {
    s = size / GRID;
    ctx.save();
    applyStyle(ctx, style, s);

    ctx.beginPath();
    ctx.arc(cx, cy, 8.5 * s, 0, Math.PI * 2);
    fillAndStroke(ctx, style);

    // Галочка
    ctx.beginPath();
    ctx.moveTo(cx - 3.5 * s, cy);
    ctx.lineTo(cx - 1 * s, cy + 3 * s);
    ctx.lineTo(cx + 4.5 * s, cy - 3.5 * s);
    ctx.stroke();

    ctx.restore();
  }

  function drawError(ctx, cx, cy, size, style) {
    s = size / GRID;
    ctx.save();
    applyStyle(ctx, style, s);

    ctx.beginPath();
    ctx.arc(cx, cy, 8.5 * s, 0, Math.PI * 2);
    fillAndStroke(ctx, style);

    // Крестик
    ctx.beginPath();
    ctx.moveTo(cx - 3.5 * s, cy - 3.5 * s);
    ctx.lineTo(cx + 3.5 * s, cy + 3.5 * s);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(cx + 3.5 * s, cy - 3.5 * s);
    ctx.lineTo(cx - 3.5 * s, cy + 3.5 * s);
    ctx.stroke();

    ctx.restore();
  }

  function drawWarning(ctx, cx, cy, size, style) {
    s = size / GRID;
    // Треугольник
    ctx.save();
    applyStyle(ctx, style, s);
    ctx.beginPath();
    ctx.moveTo(cx, cy - 8 * s);
    ctx.lineTo(cx - 8.5 * s, cy + 5.5 * s);
    ctx.lineTo(cx + 8.5 * s, cy + 5.5 * s);
    ctx.closePath();
    fillAndStroke(ctx, style);
    ctx.restore();

    // Восклицательный знак (акцент для duotone)
    ctx.save();
    if (style.accentStroke) {
      applyAccentStyle(ctx, style, s);
    } else {
      applyStyle(ctx, style, s);
    }
    ctx.fillStyle = ctx.strokeStyle;
    ctx.fillRect(cx - 0.8 * s, cy - 3 * s, 1.6 * s, 4.5 * s);
    ctx.beginPath();
    ctx.arc(cx, cy + 3.5 * s, 0.9 * s, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }

  function drawGreenCircle(ctx, cx, cy, size, style) {
    s = size / GRID;
    ctx.save();
    applyStyle(ctx, style, s);
    ctx.beginPath();
    ctx.arc(cx, cy, 7 * s, 0, Math.PI * 2);
    fillAndStroke(ctx, style);
    ctx.restore();
  }

  function drawRedCircle(ctx, cx, cy, size, style) {
    s = size / GRID;
    ctx.save();
    applyStyle(ctx, style, s);
    ctx.beginPath();
    ctx.arc(cx, cy, 7 * s, 0, Math.PI * 2);
    fillAndStroke(ctx, style);
    ctx.restore();
  }

  function drawEmptySquare(ctx, cx, cy, size, style) {
    s = size / GRID;
    ctx.save();
    applyStyle(ctx, style, s);
    roundedRect(
      ctx,
      cx - 6.5 * s,
      cy - 6.5 * s,
      13 * s,
      13 * s,
      style.cornerRadius * s,
      style
    );
    ctx.restore();
  }

  function drawLoading(ctx, cx, cy, size, style) {
    s = size / GRID;
    ctx.save();
    applyStyle(ctx, style, s);

    // Верхний треугольник
    ctx.beginPath();
    ctx.moveTo(cx - 5.5 * s, cy - 8 * s);
    ctx.lineTo(cx + 5.5 * s, cy - 8 * s);
    ctx.lineTo(cx, cy);
    ctx.closePath();
    fillAndStroke(ctx, style);

    // Нижний треугольник
    ctx.beginPath();
    ctx.moveTo(cx - 5.5 * s, cy + 8 * s);
    ctx.lineTo(cx + 5.5 * s, cy + 8 * s);
    ctx.lineTo(cx, cy);
    ctx.closePath();
    fillAndStroke(ctx, style);

    // Рамки
    ctx.beginPath();
    ctx.moveTo(cx - 6 * s, cy - 8 * s);
    ctx.lineTo(cx + 6 * s, cy - 8 * s);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(cx - 6 * s, cy + 8 * s);
    ctx.lineTo(cx + 6 * s, cy + 8 * s);
    ctx.stroke();

    ctx.restore();
  }

  function drawNewLabel(ctx, cx, cy, size, style) {
    s = size / GRID;
    ctx.save();
    applyStyle(ctx, style, s);

    // Бейдж
    roundedRect(
      ctx,
      cx - 7 * s,
      cy - 5 * s,
      14 * s,
      10 * s,
      style.cornerRadius * s,
      style
    );

    // Звёздочка
    ctx.beginPath();
    ctx.moveTo(cx, cy - 3 * s);
    ctx.lineTo(cx + 0.8 * s, cy - 0.8 * s);
    ctx.lineTo(cx + 3 * s, cy);
    ctx.lineTo(cx + 0.8 * s, cy + 0.8 * s);
    ctx.lineTo(cx, cy + 3 * s);
    ctx.lineTo(cx - 0.8 * s, cy + 0.8 * s);
    ctx.lineTo(cx - 3 * s, cy);
    ctx.lineTo(cx - 0.8 * s, cy - 0.8 * s);
    ctx.closePath();
    if (style.fill && style.fill !== 'none') {
      ctx.fill();
    }
    ctx.stroke();

    ctx.restore();
  }

  function drawNoData(ctx, cx, cy, size, style) {
    s = size / GRID;
    ctx.save();
    applyStyle(ctx, style, s);

    // Поднос: трапеция
    ctx.beginPath();
    ctx.moveTo(cx - 7 * s, cy - 2 * s);
    ctx.lineTo(cx + 7 * s, cy - 2 * s);
    ctx.lineTo(cx + 5 * s, cy + 7 * s);
    ctx.lineTo(cx - 5 * s, cy + 7 * s);
    ctx.closePath();
    fillAndStroke(ctx, style);

    // Линия верха
    ctx.beginPath();
    ctx.moveTo(cx - 8 * s, cy - 2 * s);
    ctx.lineTo(cx + 8 * s, cy - 2 * s);
    ctx.stroke();

    ctx.restore();
  }

  // -------------------------------------------------------------------------
  // Группа: Навигация (navigation)
  // -------------------------------------------------------------------------

  function drawArrowLeft(ctx, cx, cy, size, style) {
    s = size / GRID;
    ctx.save();
    applyStyle(ctx, style, s);
    ctx.beginPath();
    ctx.moveTo(cx + 7 * s, cy);
    ctx.lineTo(cx - 6 * s, cy);
    ctx.moveTo(cx - 6 * s, cy);
    ctx.lineTo(cx - 3 * s, cy - 4 * s);
    ctx.moveTo(cx - 6 * s, cy);
    ctx.lineTo(cx - 3 * s, cy + 4 * s);
    ctx.stroke();
    ctx.restore();
  }

  function drawArrowRight(ctx, cx, cy, size, style) {
    s = size / GRID;
    ctx.save();
    applyStyle(ctx, style, s);
    ctx.beginPath();
    ctx.moveTo(cx - 7 * s, cy);
    ctx.lineTo(cx + 6 * s, cy);
    ctx.moveTo(cx + 6 * s, cy);
    ctx.lineTo(cx + 3 * s, cy - 4 * s);
    ctx.moveTo(cx + 6 * s, cy);
    ctx.lineTo(cx + 3 * s, cy + 4 * s);
    ctx.stroke();
    ctx.restore();
  }

  function drawArrowLeftBold(ctx, cx, cy, size, style) {
    s = size / GRID;
    ctx.save();
    applyStyle(ctx, style, s);
    ctx.beginPath();
    ctx.moveTo(cx + 6 * s, cy - 2 * s);
    ctx.lineTo(cx - 3 * s, cy - 2 * s);
    ctx.lineTo(cx - 3 * s, cy - 5 * s);
    ctx.lineTo(cx - 9 * s, cy);
    ctx.lineTo(cx - 3 * s, cy + 5 * s);
    ctx.lineTo(cx - 3 * s, cy + 2 * s);
    ctx.lineTo(cx + 6 * s, cy + 2 * s);
    ctx.closePath();
    fillAndStroke(ctx, style);
    ctx.restore();
  }

  function drawArrowDown(ctx, cx, cy, size, style) {
    s = size / GRID;
    ctx.save();
    applyStyle(ctx, style, s);

    // Рука (горизонтальная черта)
    ctx.beginPath();
    ctx.moveTo(cx - 6 * s, cy - 6 * s);
    ctx.lineTo(cx + 6 * s, cy - 6 * s);
    ctx.stroke();

    // Стрелка вниз
    ctx.beginPath();
    ctx.moveTo(cx, cy - 6 * s);
    ctx.lineTo(cx, cy + 6 * s);
    ctx.stroke();

    // Наконечник
    ctx.beginPath();
    ctx.moveTo(cx, cy + 6 * s);
    ctx.lineTo(cx - 4 * s, cy + 1 * s);
    ctx.moveTo(cx, cy + 6 * s);
    ctx.lineTo(cx + 4 * s, cy + 1 * s);
    ctx.stroke();

    ctx.restore();
  }

  function drawLocation(ctx, cx, cy, size, style) {
    s = size / GRID;
    ctx.save();
    applyStyle(ctx, style, s);

    // Пин
    ctx.beginPath();
    ctx.arc(cx, cy - 2 * s, 5.5 * s, Math.PI, 0, false);
    ctx.lineTo(cx, cy + 8 * s);
    ctx.closePath();
    fillAndStroke(ctx, style);

    // Внутренний круг
    if (style.fill === 'none' || !style.fill) {
      ctx.beginPath();
      ctx.arc(cx, cy - 2 * s, 2.5 * s, 0, Math.PI * 2);
      ctx.stroke();
    }

    ctx.restore();
  }

  // -------------------------------------------------------------------------
  // Группа: Действия (actions)
  // -------------------------------------------------------------------------

  function drawDelete(ctx, cx, cy, size, style) {
    s = size / GRID;
    ctx.save();
    applyStyle(ctx, style, s);

    // Крышка
    ctx.beginPath();
    ctx.moveTo(cx - 7 * s, cy - 6 * s);
    ctx.lineTo(cx + 7 * s, cy - 6 * s);
    ctx.stroke();

    // Ручка
    ctx.beginPath();
    ctx.moveTo(cx - 2.5 * s, cy - 6 * s);
    ctx.lineTo(cx - 2.5 * s, cy - 8.5 * s);
    ctx.lineTo(cx + 2.5 * s, cy - 8.5 * s);
    ctx.lineTo(cx + 2.5 * s, cy - 6 * s);
    ctx.stroke();

    // Корпус
    ctx.beginPath();
    ctx.moveTo(cx - 6 * s, cy - 5.5 * s);
    ctx.lineTo(cx + 6 * s, cy - 5.5 * s);
    ctx.lineTo(cx + 4.5 * s, cy + 7 * s);
    ctx.lineTo(cx - 4.5 * s, cy + 7 * s);
    ctx.closePath();
    fillAndStroke(ctx, style);

    // Полосы
    ctx.beginPath();
    ctx.moveTo(cx - 3 * s, cy - 1 * s);
    ctx.lineTo(cx + 3 * s, cy - 1 * s);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(cx - 2 * s, cy + 2.5 * s);
    ctx.lineTo(cx + 2 * s, cy + 2.5 * s);
    ctx.stroke();

    ctx.restore();
  }

  function drawAdd(ctx, cx, cy, size, style) {
    s = size / GRID;
    ctx.save();
    applyStyle(ctx, style, s);

    // Квадрат
    roundedRect(
      ctx,
      cx - 8 * s,
      cy - 8 * s,
      16 * s,
      16 * s,
      style.cornerRadius * s,
      style
    );

    // Плюс
    ctx.beginPath();
    ctx.moveTo(cx - 4 * s, cy);
    ctx.lineTo(cx + 4 * s, cy);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(cx, cy - 4 * s);
    ctx.lineTo(cx, cy + 4 * s);
    ctx.stroke();

    ctx.restore();
  }

  function drawRefresh(ctx, cx, cy, size, style) {
    s = size / GRID;
    ctx.save();
    applyStyle(ctx, style, s);

    // Верхняя дуга
    ctx.beginPath();
    ctx.arc(cx, cy, 6 * s, -Math.PI * 0.7, Math.PI * 0.2);
    ctx.stroke();

    // Наконечник верхней стрелки
    var ax1 = cx + 6 * s * Math.cos(Math.PI * 0.2);
    var ay1 = cy + 6 * s * Math.sin(Math.PI * 0.2);
    ctx.beginPath();
    ctx.moveTo(ax1, ay1);
    ctx.lineTo(ax1 - 3.5 * s, ay1 - 2 * s);
    ctx.moveTo(ax1, ay1);
    ctx.lineTo(ax1 + 1 * s, ay1 - 3.5 * s);
    ctx.stroke();

    // Нижняя дуга
    ctx.beginPath();
    ctx.arc(cx, cy, 6 * s, Math.PI * 0.8, Math.PI * 1.7, false);
    ctx.stroke();

    // Наконечник нижней стрелки
    var ax2 = cx + 6 * s * Math.cos(Math.PI * 1.7);
    var ay2 = cy + 6 * s * Math.sin(Math.PI * 1.7);
    ctx.beginPath();
    ctx.moveTo(ax2, ay2);
    ctx.lineTo(ax2 + 3.5 * s, ay2 + 2 * s);
    ctx.moveTo(ax2, ay2);
    ctx.lineTo(ax2 - 1 * s, ay2 + 3.5 * s);
    ctx.stroke();

    ctx.restore();
  }

  function drawSearch(ctx, cx, cy, size, style) {
    s = size / GRID;
    ctx.save();
    applyStyle(ctx, style, s);

    // Круг лупы
    ctx.beginPath();
    ctx.arc(cx - 2 * s, cy - 2 * s, 6 * s, 0, Math.PI * 2);
    fillAndStroke(ctx, style);

    // Ручка
    ctx.beginPath();
    ctx.moveTo(cx + 2.5 * s, cy + 2.5 * s);
    ctx.lineTo(cx + 8 * s, cy + 8 * s);
    ctx.stroke();

    ctx.restore();
  }

  function drawStop(ctx, cx, cy, size, style) {
    s = size / GRID;
    ctx.save();
    applyStyle(ctx, style, s);

    // Восьмиугольник
    var sides = 8;
    var r = 8.5 * s;
    ctx.beginPath();
    for (var i = 0; i < sides; i++) {
      var angle = (Math.PI * 2 * i) / sides - Math.PI / sides;
      var vx = cx + r * Math.cos(angle);
      var vy = cy + r * Math.sin(angle);
      if (i === 0) {
        ctx.moveTo(vx, vy);
      } else {
        ctx.lineTo(vx, vy);
      }
    }
    ctx.closePath();
    fillAndStroke(ctx, style);

    // Стилизованная S
    ctx.beginPath();
    ctx.moveTo(cx + 2 * s, cy - 3 * s);
    ctx.lineTo(cx - 2 * s, cy - 3 * s);
    ctx.lineTo(cx - 2 * s, cy);
    ctx.lineTo(cx + 2 * s, cy);
    ctx.lineTo(cx + 2 * s, cy + 3 * s);
    ctx.lineTo(cx - 2 * s, cy + 3 * s);
    ctx.stroke();

    ctx.restore();
  }

  // -------------------------------------------------------------------------
  // Группа: Данные (data)
  // -------------------------------------------------------------------------

  function drawClipboard(ctx, cx, cy, size, style) {
    s = size / GRID;
    ctx.save();
    applyStyle(ctx, style, s);

    // Планшет
    roundedRect(
      ctx,
      cx - 7 * s,
      cy - 7 * s,
      14 * s,
      16 * s,
      style.cornerRadius * s,
      style
    );

    // Заголовок
    ctx.fillStyle = ctx.strokeStyle;
    ctx.fillRect(cx - 6 * s, cy - 5 * s, 12 * s, 3 * s);

    // Линии
    for (var li = 0; li < 3; li++) {
      ctx.beginPath();
      ctx.moveTo(cx - 5 * s, cy + li * 3.5 * s);
      ctx.lineTo(cx + 5 * s, cy + li * 3.5 * s);
      ctx.stroke();
    }

    ctx.restore();
  }

  function drawChart(ctx, cx, cy, size, style) {
    s = size / GRID;
    ctx.save();
    applyStyle(ctx, style, s);

    // Базовая линия
    ctx.beginPath();
    ctx.moveTo(cx - 8 * s, cy + 7 * s);
    ctx.lineTo(cx + 8 * s, cy + 7 * s);
    ctx.stroke();

    // Столбцы
    var bars = [
      { x: cx - 6 * s, w: 3 * s, h: 5 * s },
      { x: cx - 1.5 * s, w: 3 * s, h: 9 * s },
      { x: cx + 3 * s, w: 3 * s, h: 7 * s }
    ];
    for (var bi = 0; bi < bars.length; bi++) {
      var bar = bars[bi];
      if (style.fill && style.fill !== 'none') {
        ctx.fillStyle = ctx.strokeStyle;
        ctx.fillRect(bar.x, cy + 7 * s - bar.h, bar.w, bar.h);
      }
      ctx.strokeRect(bar.x, cy + 7 * s - bar.h, bar.w, bar.h);
    }

    ctx.restore();
  }

  function drawDocument(ctx, cx, cy, size, style) {
    s = size / GRID;
    ctx.save();
    applyStyle(ctx, style, s);

    // Тело документа с загнутым углом
    ctx.beginPath();
    ctx.moveTo(cx - 7 * s, cy - 8 * s);
    ctx.lineTo(cx + 3 * s, cy - 8 * s);
    ctx.lineTo(cx + 3 * s, cy - 2 * s);
    ctx.lineTo(cx + 7 * s, cy - 2 * s);
    ctx.lineTo(cx + 7 * s, cy + 8 * s);
    ctx.lineTo(cx - 7 * s, cy + 8 * s);
    ctx.closePath();
    fillAndStroke(ctx, style);

    // Линия сгиба
    ctx.beginPath();
    ctx.moveTo(cx + 3 * s, cy - 8 * s);
    ctx.lineTo(cx + 3 * s, cy - 2 * s);
    ctx.lineTo(cx + 7 * s, cy - 2 * s);
    ctx.stroke();

    // Линии текста
    for (var dli = 0; dli < 4; dli++) {
      ctx.beginPath();
      ctx.moveTo(cx - 5 * s, cy - 4 * s + dli * 3 * s);
      ctx.lineTo(cx + 1 * s, cy - 4 * s + dli * 3 * s);
      ctx.stroke();
    }

    ctx.restore();
  }

  function drawCalendarTear(ctx, cx, cy, size, style) {
    s = size / GRID;
    ctx.save();
    applyStyle(ctx, style, s);

    // Нижние листы (смещены)
    for (var sheet = 2; sheet >= 0; sheet--) {
      var ox = (sheet - 1) * 1.5 * s;
      var oy = (sheet - 1) * 1 * s;
      ctx.beginPath();
      ctx.rect(cx - 6 * s + ox, cy + 1.5 * s + oy, 12 * s, 7 * s);
      if (style.fill && style.fill !== 'none') {
        ctx.fill();
      }
      ctx.stroke();
    }

    // Кольца
    for (var ring = -1; ring <= 1; ring++) {
      ctx.beginPath();
      ctx.arc(cx + ring * 4 * s, cy - 2 * s, 1.2 * s, Math.PI, 0, false);
      ctx.stroke();
    }

    ctx.restore();
  }

  function drawCalendar(ctx, cx, cy, size, style) {
    s = size / GRID;
    ctx.save();
    applyStyle(ctx, style, s);

    // Тело календаря
    roundedRect(
      ctx,
      cx - 7 * s,
      cy - 4 * s,
      14 * s,
      13 * s,
      style.cornerRadius * s,
      style
    );

    // Верхняя полоса
    ctx.fillStyle = ctx.strokeStyle;
    ctx.fillRect(cx - 7 * s, cy - 4 * s, 14 * s, 3.5 * s);

    // Число (геометрическое)
    ctx.beginPath();
    ctx.moveTo(cx - 2 * s, cy + 1 * s);
    ctx.lineTo(cx + 2 * s, cy + 1 * s);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(cx, cy + 1 * s);
    ctx.lineTo(cx, cy + 5 * s);
    ctx.stroke();

    ctx.restore();
  }

  function drawTag(ctx, cx, cy, size, style) {
    s = size / GRID;
    ctx.save();
    applyStyle(ctx, style, s);

    // Тело ярлыка
    ctx.beginPath();
    ctx.moveTo(cx - 6 * s, cy - 6 * s);
    ctx.lineTo(cx + 4 * s, cy - 6 * s);
    ctx.lineTo(cx + 8 * s, cy);
    ctx.lineTo(cx + 4 * s, cy + 6 * s);
    ctx.lineTo(cx - 6 * s, cy + 6 * s);
    ctx.closePath();
    fillAndStroke(ctx, style);

    // Отверстие
    ctx.beginPath();
    ctx.arc(cx - 3.5 * s, cy, 1.5 * s, 0, Math.PI * 2);
    if (style.fill && style.fill !== 'none') {
      ctx.save();
      ctx.globalCompositeOperation = 'destination-out';
      ctx.fill();
      ctx.restore();
    }
    ctx.stroke();

    ctx.restore();
  }

  // -------------------------------------------------------------------------
  // Группа: Платформа (platform)
  // -------------------------------------------------------------------------

  function drawRobot(ctx, cx, cy, size, style) {
    s = size / GRID;
    ctx.save();
    applyStyle(ctx, style, s);

    // Голова
    roundedRect(
      ctx,
      cx - 7 * s,
      cy - 6 * s,
      14 * s,
      12 * s,
      style.cornerRadius * s,
      style
    );

    // Антенна
    ctx.beginPath();
    ctx.moveTo(cx, cy - 6 * s);
    ctx.lineTo(cx, cy - 9 * s);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(cx, cy - 9.5 * s, 0.8 * s, 0, Math.PI * 2);
    if (style.fill && style.fill !== 'none') {
      ctx.fill();
    }
    ctx.stroke();

    // Глаза
    ctx.beginPath();
    ctx.arc(cx - 3 * s, cy - 1 * s, 1.5 * s, 0, Math.PI * 2);
    if (style.fill && style.fill !== 'none') {
      ctx.fill();
    }
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(cx + 3 * s, cy - 1 * s, 1.5 * s, 0, Math.PI * 2);
    if (style.fill && style.fill !== 'none') {
      ctx.fill();
    }
    ctx.stroke();

    // Рот
    ctx.beginPath();
    ctx.moveTo(cx - 2.5 * s, cy + 3 * s);
    ctx.lineTo(cx + 2.5 * s, cy + 3 * s);
    ctx.stroke();

    ctx.restore();
  }

  function drawCelebration(ctx, cx, cy, size, style) {
    s = size / GRID;
    ctx.save();
    applyStyle(ctx, style, s);

    // Пятиконечная звезда
    var outerR = 8 * s;
    var innerR = 3.5 * s;
    var points = 5;
    ctx.beginPath();
    for (var si = 0; si < points * 2; si++) {
      var sa = (Math.PI * 2 * si) / (points * 2) - Math.PI / 2;
      var sr = si % 2 === 0 ? outerR : innerR;
      var svx = cx + sr * Math.cos(sa);
      var svy = cy + sr * Math.sin(sa);
      if (si === 0) {
        ctx.moveTo(svx, svy);
      } else {
        ctx.lineTo(svx, svy);
      }
    }
    ctx.closePath();
    fillAndStroke(ctx, style);

    // Конфетти
    ctx.fillStyle = ctx.strokeStyle;
    var confetti = [
      { x: cx + 7 * s, y: cy - 6 * s, a: 0.3 },
      { x: cx - 8 * s, y: cy + 4 * s, a: -0.5 },
      { x: cx + 8 * s, y: cy + 5 * s, a: 0.7 }
    ];
    for (var ci = 0; ci < confetti.length; ci++) {
      var c = confetti[ci];
      ctx.save();
      ctx.translate(c.x, c.y);
      ctx.rotate(c.a);
      ctx.fillRect(-1.5 * s, -0.6 * s, 3 * s, 1.2 * s);
      ctx.restore();
    }

    ctx.restore();
  }

  function drawWave(ctx, cx, cy, size, style) {
    s = size / GRID;
    ctx.save();
    applyStyle(ctx, style, s);

    // Ладонь
    ctx.beginPath();
    ctx.arc(cx - 1 * s, cy + 1 * s, 5 * s, 0, Math.PI * 2);
    fillAndStroke(ctx, style);

    // Пальцы
    var fingers = [
      { bx: cx - 4 * s, by: cy - 3 * s, ex: cx - 4 * s, ey: cy - 8 * s },
      { bx: cx - 1.5 * s, by: cy - 4 * s, ex: cx - 1.5 * s, ey: cy - 8.5 * s },
      { bx: cx + 1 * s, by: cy - 4 * s, ex: cx + 1 * s, ey: cy - 8 * s },
      { bx: cx + 3 * s, by: cy - 3 * s, ex: cx + 3 * s, ey: cy - 7 * s }
    ];
    for (var fi = 0; fi < fingers.length; fi++) {
      var f = fingers[fi];
      ctx.beginPath();
      ctx.moveTo(f.bx, f.by);
      ctx.lineTo(f.ex, f.ey);
      ctx.stroke();
    }

    // Запястье
    ctx.beginPath();
    ctx.moveTo(cx - 3 * s, cy + 5 * s);
    ctx.lineTo(cx - 3 * s, cy + 8 * s);
    ctx.moveTo(cx + 1 * s, cy + 5 * s);
    ctx.lineTo(cx + 1 * s, cy + 8 * s);
    ctx.stroke();

    ctx.restore();
  }

  function drawIdea(ctx, cx, cy, size, style) {
    s = size / GRID;
    // Колба
    ctx.save();
    applyStyle(ctx, style, s);
    ctx.beginPath();
    ctx.arc(cx, cy - 2.5 * s, 6.5 * s, 0, Math.PI * 2);
    fillAndStroke(ctx, style);
    ctx.restore();

    // Цоколь
    ctx.save();
    applyStyle(ctx, style, s);
    roundedRect(
      ctx,
      cx - 3 * s,
      cy + 3.5 * s,
      6 * s,
      3 * s,
      style.cornerRadius * s,
      style
    );
    ctx.restore();

    // Контакт
    ctx.save();
    applyStyle(ctx, style, s);
    ctx.beginPath();
    ctx.arc(cx, cy + 7 * s, 0.8 * s, 0, Math.PI * 2);
    if (style.fill && style.fill !== 'none') {
      ctx.fill();
    }
    ctx.stroke();
    ctx.restore();

    // Лучи свечения (акцент для duotone)
    ctx.save();
    if (style.accentStroke) {
      applyAccentStyle(ctx, style, s);
    } else {
      applyStyle(ctx, style, s);
    }
    ctx.beginPath();
    ctx.moveTo(cx, cy - 9 * s);
    ctx.lineTo(cx, cy - 10 * s);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(cx - 5 * s, cy - 7 * s);
    ctx.lineTo(cx - 6 * s, cy - 8.5 * s);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(cx + 5 * s, cy - 7 * s);
    ctx.lineTo(cx + 6 * s, cy - 8.5 * s);
    ctx.stroke();
    ctx.restore();
  }

  function drawGlobe(ctx, cx, cy, size, style) {
    s = size / GRID;
    ctx.save();
    applyStyle(ctx, style, s);

    // Круг глобуса
    ctx.beginPath();
    ctx.arc(cx, cy, 7.5 * s, 0, Math.PI * 2);
    fillAndStroke(ctx, style);

    // Экватор
    ctx.beginPath();
    ctx.ellipse(cx, cy, 7.5 * s, 2.5 * s, 0, 0, Math.PI * 2);
    ctx.stroke();

    // Меридиан
    ctx.beginPath();
    ctx.ellipse(cx, cy, 2.5 * s, 7.5 * s, 0, 0, Math.PI * 2);
    ctx.stroke();

    // Подставка
    ctx.beginPath();
    ctx.moveTo(cx - 3 * s, cy + 7.5 * s);
    ctx.lineTo(cx - 3 * s, cy + 9 * s);
    ctx.lineTo(cx + 3 * s, cy + 9 * s);
    ctx.lineTo(cx + 3 * s, cy + 7.5 * s);
    ctx.stroke();

    ctx.restore();
  }

  function drawPlug(ctx, cx, cy, size, style) {
    s = size / GRID;
    ctx.save();
    applyStyle(ctx, style, s);

    // Корпус
    roundedRect(
      ctx,
      cx - 5 * s,
      cy - 2 * s,
      10 * s,
      8 * s,
      style.cornerRadius * s,
      style
    );

    // Штырьки
    ctx.fillStyle = ctx.strokeStyle;
    ctx.fillRect(cx - 3 * s, cy - 8 * s, 2 * s, 6 * s);
    ctx.fillRect(cx + 1 * s, cy - 8 * s, 2 * s, 6 * s);

    // Провод
    ctx.beginPath();
    ctx.moveTo(cx, cy + 6 * s);
    ctx.lineTo(cx, cy + 9 * s);
    ctx.stroke();

    ctx.restore();
  }

  function drawLink(ctx, cx, cy, size, style) {
    s = size / GRID;

    // Левое звено (вертикальное)
    ctx.save();
    applyStyle(ctx, style, s);
    roundedRect(
      ctx,
      cx - 7 * s,
      cy - 5 * s,
      7 * s,
      10 * s,
      style.cornerRadius * s,
      style
    );

    if (style.fill && style.fill !== 'none') {
      ctx.save();
      ctx.globalCompositeOperation = 'destination-out';
      roundedRect(
        ctx,
        cx - 5.5 * s,
        cy - 3.5 * s,
        4 * s,
        7 * s,
        style.cornerRadius * s,
        style
      );
      ctx.restore();
    }
    ctx.restore();

    // Правое звено (горизонтальное)
    ctx.save();
    applyStyle(ctx, style, s);
    roundedRect(
      ctx,
      cx + 0.5 * s,
      cy - 3 * s,
      7 * s,
      6 * s,
      style.cornerRadius * s,
      style
    );

    if (style.fill && style.fill !== 'none') {
      ctx.save();
      ctx.globalCompositeOperation = 'destination-out';
      roundedRect(
        ctx,
        cx + 2 * s,
        cy - 1.5 * s,
        4 * s,
        3 * s,
        style.cornerRadius * s,
        style
      );
      ctx.restore();
    }
    ctx.restore();
  }

  function drawLock(ctx, cx, cy, size, style) {
    s = size / GRID;
    ctx.save();
    applyStyle(ctx, style, s);

    // Дужка
    ctx.beginPath();
    ctx.arc(cx, cy - 3 * s, 4 * s, Math.PI, 0, false);
    ctx.stroke();

    // Тело замка
    roundedRect(
      ctx,
      cx - 5 * s,
      cy - 1 * s,
      10 * s,
      9 * s,
      style.cornerRadius * s,
      style
    );

    // Замочная скважина
    ctx.beginPath();
    ctx.arc(cx, cy + 3 * s, 1.2 * s, 0, Math.PI * 2);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(cx, cy + 4.2 * s);
    ctx.lineTo(cx, cy + 6 * s);
    ctx.stroke();

    ctx.restore();
  }

  function drawMobile(ctx, cx, cy, size, style) {
    s = size / GRID;
    ctx.save();
    applyStyle(ctx, style, s);

    // Корпус
    roundedRect(
      ctx,
      cx - 5 * s,
      cy - 8 * s,
      10 * s,
      16 * s,
      style.cornerRadius * s,
      style
    );

    // Экран
    roundedRect(
      ctx,
      cx - 3.5 * s,
      cy - 6 * s,
      7 * s,
      10 * s,
      Math.max(0, style.cornerRadius - 1) * s,
      style
    );

    // Кнопка home
    ctx.beginPath();
    ctx.arc(cx, cy + 5.5 * s, 1 * s, 0, Math.PI * 2);
    ctx.stroke();

    ctx.restore();
  }

  function drawSettings(ctx, cx, cy, size, style) {
    s = size / GRID;
    ctx.save();
    applyStyle(ctx, style, s);

    // Центральный круг
    ctx.beginPath();
    ctx.arc(cx, cy, 3.5 * s, 0, Math.PI * 2);
    fillAndStroke(ctx, style);

    // Зубья (8 шт.)
    var teeth = 8;
    for (var ti = 0; ti < teeth; ti++) {
      var ta = (Math.PI * 2 * ti) / teeth - Math.PI / 2;
      var tix = cx + 6 * s * Math.cos(ta);
      var tiy = cy + 6 * s * Math.sin(ta);
      ctx.save();
      ctx.translate(tix, tiy);
      ctx.rotate(ta);
      if (style.fill && style.fill !== 'none') {
        ctx.fillStyle = ctx.strokeStyle;
        ctx.fillRect(-1.2 * s, -1.2 * s, 2.4 * s, 2.4 * s);
      }
      ctx.strokeRect(-1.2 * s, -1.2 * s, 2.4 * s, 2.4 * s);
      ctx.restore();
    }

    // Внешнее кольцо (для outline стилей)
    if (style.fill === 'none' || !style.fill) {
      ctx.beginPath();
      ctx.arc(cx, cy, 6 * s, 0, Math.PI * 2);
      ctx.stroke();
    }

    ctx.restore();
  }

  function drawUptime(ctx, cx, cy, size, style) {
    s = size / GRID;
    ctx.save();
    applyStyle(ctx, style, s);

    // Корпус
    ctx.beginPath();
    ctx.arc(cx, cy, 7.5 * s, 0, Math.PI * 2);
    fillAndStroke(ctx, style);

    // Кнопка
    ctx.beginPath();
    ctx.moveTo(cx - 1.5 * s, cy - 7.5 * s);
    ctx.lineTo(cx - 1.5 * s, cy - 9.5 * s);
    ctx.lineTo(cx + 1.5 * s, cy - 9.5 * s);
    ctx.lineTo(cx + 1.5 * s, cy - 7.5 * s);
    ctx.stroke();

    ctx.restore();

    // Большая стрелка (акцент для duotone)
    ctx.save();
    if (style.accentStroke) {
      applyAccentStyle(ctx, style, s);
    } else {
      applyStyle(ctx, style, s);
    }
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(cx + 3 * s, cy - 5 * s);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(cx, cy, 0.8 * s, 0, Math.PI * 2);
    if (style.fill && style.fill !== 'none') {
      ctx.fill();
    }
    ctx.stroke();
    ctx.restore();

    // Маленькая стрелка
    ctx.save();
    applyStyle(ctx, style, s);
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(cx - 4 * s, cy - 2 * s);
    ctx.stroke();
    ctx.restore();
  }

  // -------------------------------------------------------------------------
  // Группа: Базовые (basic)
  // -------------------------------------------------------------------------

  function drawCheck(ctx, cx, cy, size, style) {
    s = size / GRID;
    ctx.save();
    applyStyle(ctx, style, s);
    ctx.beginPath();
    ctx.moveTo(cx - 5 * s, cy + 0.5 * s);
    ctx.lineTo(cx - 1.5 * s, cy + 4.5 * s);
    ctx.lineTo(cx + 6 * s, cy - 5 * s);
    ctx.stroke();
    ctx.restore();
  }

  function drawCross(ctx, cx, cy, size, style) {
    s = size / GRID;
    ctx.save();
    applyStyle(ctx, style, s);
    ctx.beginPath();
    ctx.moveTo(cx - 5 * s, cy - 5 * s);
    ctx.lineTo(cx + 5 * s, cy + 5 * s);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(cx + 5 * s, cy - 5 * s);
    ctx.lineTo(cx - 5 * s, cy + 5 * s);
    ctx.stroke();
    ctx.restore();
  }

  // =========================================================================
  // Список всех иконок с метаданными
  // =========================================================================

  var ICON_LIST = [
    // Люди
    { id: 'patient', name: 'Пациент', group: 'people', fn: drawPatient },
    { id: 'doctor', name: 'Врач', group: 'people', fn: drawDoctor },
    { id: 'clinic', name: 'Клиника', group: 'people', fn: drawClinic },
    {
      id: 'specialty',
      name: 'Специальность',
      group: 'people',
      fn: drawSpecialty
    },
    { id: 'users', name: 'Пользователи', group: 'people', fn: drawUsers },
    {
      id: 'person_shrug',
      name: 'Нет результатов',
      group: 'people',
      fn: drawPersonShrug
    },

    // Статусы
    { id: 'success', name: 'Успех', group: 'status', fn: drawSuccess },
    { id: 'error', name: 'Ошибка', group: 'status', fn: drawError },
    { id: 'warning', name: 'Предупреждение', group: 'status', fn: drawWarning },
    {
      id: 'green_circle',
      name: 'Есть слоты',
      group: 'status',
      fn: drawGreenCircle
    },
    {
      id: 'red_circle',
      name: 'Нет слотов',
      group: 'status',
      fn: drawRedCircle
    },
    {
      id: 'empty_square',
      name: 'Не отслеживается',
      group: 'status',
      fn: drawEmptySquare
    },
    { id: 'loading', name: 'Загрузка', group: 'status', fn: drawLoading },
    { id: 'new_label', name: 'Новое', group: 'status', fn: drawNewLabel },
    { id: 'no_data', name: 'Нет данных', group: 'status', fn: drawNoData },

    // Навигация
    {
      id: 'arrow_left',
      name: 'Стрелка влево',
      group: 'navigation',
      fn: drawArrowLeft
    },
    {
      id: 'arrow_right',
      name: 'Стрелка вправо',
      group: 'navigation',
      fn: drawArrowRight
    },
    {
      id: 'arrow_left_bold',
      name: 'Стрелка влево (толстая)',
      group: 'navigation',
      fn: drawArrowLeftBold
    },
    {
      id: 'arrow_down',
      name: 'Указатель вниз',
      group: 'navigation',
      fn: drawArrowDown
    },
    { id: 'location', name: 'Локация', group: 'navigation', fn: drawLocation },

    // Действия
    { id: 'delete', name: 'Удалить', group: 'actions', fn: drawDelete },
    { id: 'add', name: 'Добавить', group: 'actions', fn: drawAdd },
    { id: 'refresh', name: 'Обновить', group: 'actions', fn: drawRefresh },
    { id: 'search', name: 'Поиск', group: 'actions', fn: drawSearch },
    { id: 'stop', name: 'Стоп', group: 'actions', fn: drawStop },

    // Данные
    { id: 'clipboard', name: 'Список', group: 'data', fn: drawClipboard },
    { id: 'chart', name: 'График', group: 'data', fn: drawChart },
    { id: 'document', name: 'Документ', group: 'data', fn: drawDocument },
    {
      id: 'calendar_tear',
      name: 'Календарь отрывной',
      group: 'data',
      fn: drawCalendarTear
    },
    { id: 'calendar', name: 'Календарь', group: 'data', fn: drawCalendar },
    { id: 'tag', name: 'Метка', group: 'data', fn: drawTag },

    // Платформа
    { id: 'robot', name: 'Робот/Бот', group: 'platform', fn: drawRobot },
    {
      id: 'celebration',
      name: 'Праздник',
      group: 'platform',
      fn: drawCelebration
    },
    { id: 'wave', name: 'Приветствие', group: 'platform', fn: drawWave },
    { id: 'idea', name: 'Подсказка', group: 'platform', fn: drawIdea },
    { id: 'globe', name: 'Веб/Ссылка', group: 'platform', fn: drawGlobe },
    { id: 'plug', name: 'API/Подключение', group: 'platform', fn: drawPlug },
    { id: 'link', name: 'Ссылка', group: 'platform', fn: drawLink },
    { id: 'lock', name: 'Аутентификация', group: 'platform', fn: drawLock },
    { id: 'mobile', name: 'Мобильный', group: 'platform', fn: drawMobile },
    { id: 'settings', name: 'Настройки', group: 'platform', fn: drawSettings },
    { id: 'uptime', name: 'Аптайм', group: 'platform', fn: drawUptime },

    // Базовые
    { id: 'check', name: 'Готово (галочка)', group: 'basic', fn: drawCheck },
    { id: 'cross', name: 'Отмена (крестик)', group: 'basic', fn: drawCross }
  ];

  /**
   * Группы иконок.
   */
  var ICON_GROUPS = {
    people: { name: 'Люди', icons: [] },
    status: { name: 'Статусы', icons: [] },
    navigation: { name: 'Навигация', icons: [] },
    actions: { name: 'Действия', icons: [] },
    data: { name: 'Данные', icons: [] },
    platform: { name: 'Платформа', icons: [] },
    basic: { name: 'Базовые', icons: [] }
  };

  for (var gi = 0; gi < ICON_LIST.length; gi++) {
    var icon = ICON_LIST[gi];
    if (ICON_GROUPS[icon.group]) {
      ICON_GROUPS[icon.group].icons.push(icon);
    }
  }

  // =========================================================================
  // Публичное API
  // =========================================================================

  /** Объект с функциями отрисовки всех иконок (по id). */
  var drawers = {};
  for (var di = 0; di < ICON_LIST.length; di++) {
    drawers[ICON_LIST[di].id] = ICON_LIST[di].fn;
  }

  window.IconDrawers = drawers;
  window.IconStyles = STYLES;
  window.IconHelpers = {
    applyStyle: applyStyle,
    applyAccentStyle: applyAccentStyle,
    fillAndStroke: fillAndStroke,
    drawRoundedRect: drawRoundedRect,
    roundedRect: roundedRect
  };
  window.ICON_LIST = ICON_LIST;
  window.ICON_GROUPS = ICON_GROUPS;
  window.GRID_SIZE = GRID;
})();
