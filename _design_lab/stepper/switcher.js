/**
 * Stepper Design Lab — Переключатель палитр, шрифтов и индикаторов
 *
 * Управляет переключением CSS-классов темы, шрифта и стиля индикатора на <body>,
 * визуальным состоянием кнопок, сохранением выбора в localStorage.
 *
 * @module switcher
 */

(function () {
  'use strict';

  // ── Палитры ────────────────────────────────────────────────

  /** @type {Record<string, string>} Названия палитр для отображения в футере */
  var THEME_NAMES = {
    'theme-biochrome': 'Биохром',
    'theme-quantum-hitech': 'Квантовый хайтек',
    'theme-neon-diagnostic': 'Неоновая диагностика',
    'theme-blood-cyan': 'Кровавый бирюзовый',
    'theme-emerald-neuro': 'Изумрудный нейрохирург',
    'theme-blue-cyber': 'Голубой киберпанк',
    'theme-purple-stasis': 'Фиолетовый стазис',
    'theme-aurora': 'Полярное сияние',
    'theme-clinical': 'Клинический контраст',
    'theme-sunset': 'Неоновый закат',
    'theme-techno-copper': 'Техно-медь',
    'theme-surgical': 'Хирургический хром',
    'theme-digital-ruby': 'Цифровой рубин',
    'theme-photon-purple': 'Фотонный фиолет',
    'theme-ozone': 'Озоновый слой',
    'theme-energy': 'Энергетический шёпот',
    'theme-cryo': 'Криогенный сон',
    'theme-mint-impulse': 'Мятный импульс',
    'theme-azure-code': 'Лазурный код',
    'theme-ruby-surf': 'Рубиновый прибой',
    'theme-deep-diagnostic': 'Глубинная диагностика',
    'theme-violet-transfer': 'Фиолетовый трансфер',
    'theme-fire-biome': 'Огненный биом',
    'theme-neon-plasma': 'Неоновая плазма',
    'theme-chrome-ruby': 'Хром-рубин',
    'theme-cyan-horizon': 'Бирюзовый горизонт',
    'theme-quantum-whisper': 'Квантовый шёпот'
  };

  /** @type {string[]} Все доступные темы */
  var ALL_THEMES = Object.keys(THEME_NAMES);

  // ── Шрифты ─────────────────────────────────────────────────

  /** @type {Record<string, string>} Названия шрифтов для отображения */
  var FONT_NAMES = {
    'font-inter': 'Inter',
    'font-space': 'Space Grotesk',
    'font-jetbrains': 'JetBrains Mono',
    'font-ibm': 'IBM Plex Sans',
    'font-sharetech': 'Share Tech Mono',
    'font-roboto': 'Roboto',
    'font-opensans': 'Open Sans',
    'font-raleway': 'Raleway',
    'font-googlesans': 'Google Sans',
    'font-notosans': 'Noto Sans',
    'font-gilroy': 'Gilroy',
    'font-default': 'По умолчанию'
  };

  /** @type {string[]} Все доступные шрифты */
  var ALL_FONTS = Object.keys(FONT_NAMES);

  // ── Индикаторы ─────────────────────────────────────────────

  /** @type {Record<string, string>} Названия стилей индикатора */
  var INDICATOR_NAMES = {
    'stepper-indicator--inline': 'Инлайн-терминал',
    'stepper-indicator--cursor': 'Курсор-терминал',
    'stepper-indicator--tabs': 'Терминал-табы',
    'stepper-indicator--dots': 'Пиксельные точки',
    'stepper-indicator--brackets': 'Угловые скобки'
  };

  /** @type {string[]} Все доступные стили индикатора */
  var ALL_INDICATORS = Object.keys(INDICATOR_NAMES);

  // ── DOM-элементы ───────────────────────────────────────────

  /** @type {HTMLDivElement|null} Контейнер с кнопками палитр */
  var paletteSwitcher = document.getElementById('palette-switcher');

  /** @type {HTMLDivElement|null} Контейнер с кнопками шрифтов */
  var fontSwitcher = document.getElementById('font-switcher');

  /** @type {HTMLDivElement|null} Контейнер с кнопками индикаторов */
  var indicatorSwitcher = document.getElementById('indicator-switcher');

  /** @type {HTMLElement|null} Элемент для отображения названия темы в футере */
  var themeNameEl = document.getElementById('current-theme-name');

  /** @type {HTMLElement|null} Контейнер интерактивного степпера (phone-frame) */
  var stepperPreview = document.getElementById('stepper-preview');

  // ── Функции переключения палитр ────────────────────────────

  /**
   * Устанавливает активную тему (палитру).
   *
   * @param {string} theme — CSS-класс темы (theme-biochrome, etc.)
   */
  function setTheme(theme) {
    // Убираем все темы с body
    for (var i = 0; i < ALL_THEMES.length; i++) {
      document.body.classList.remove(ALL_THEMES[i]);
    }
    // Устанавливаем новую
    document.body.classList.add(theme);

    // Обновляем кнопки палитр
    if (paletteSwitcher) {
      var buttons = paletteSwitcher.querySelectorAll('.palette-btn');
      for (var j = 0; j < buttons.length; j++) {
        var btn = buttons[j];
        if (btn.getAttribute('data-theme') === theme) {
          btn.classList.add('palette-btn--active');
        } else {
          btn.classList.remove('palette-btn--active');
        }
      }
    }

    // Обновляем футер
    if (themeNameEl) {
      themeNameEl.textContent = THEME_NAMES[theme] || theme;
    }

    // Сохраняем выбор в localStorage
    try {
      localStorage.setItem('stepper-lab-theme', theme);
    } catch (_) {
      // Игнорируем ошибки localStorage
    }
  }

  // ── Функции переключения шрифтов ───────────────────────────

  /**
   * Устанавливает активный шрифт.
   *
   * @param {string} font — CSS-класс шрифта (font-inter, etc.)
   */
  function setFont(font) {
    // Убираем все шрифты с body
    for (var i = 0; i < ALL_FONTS.length; i++) {
      document.body.classList.remove(ALL_FONTS[i]);
    }
    // Устанавливаем новый (font-default не добавляет класс)
    if (font !== 'font-default') {
      document.body.classList.add(font);
    }

    // Обновляем кнопки шрифтов
    if (fontSwitcher) {
      var buttons = fontSwitcher.querySelectorAll('.palette-btn');
      for (var j = 0; j < buttons.length; j++) {
        var btn = buttons[j];
        if (btn.getAttribute('data-font') === font) {
          btn.classList.add('palette-btn--active');
        } else {
          btn.classList.remove('palette-btn--active');
        }
      }
    }

    // Сохраняем выбор в localStorage
    try {
      localStorage.setItem('stepper-lab-font', font);
    } catch (_) {
      // Игнорируем ошибки localStorage
    }
  }

  // ── Функции переключения индикаторов ───────────────────────

  /**
   * Устанавливает стиль индикатора степпера.
   *
   * @param {string} indicatorType — CSS-класс индикатора (stepper-indicator--inline, etc.)
   */
  function setIndicator(indicatorType) {
    // Убираем все классы индикаторов с body
    for (var i = 0; i < ALL_INDICATORS.length; i++) {
      document.body.classList.remove(ALL_INDICATORS[i]);
    }
    // Устанавливаем новый
    document.body.classList.add(indicatorType);

    // Обновляем кнопки индикаторов
    if (indicatorSwitcher) {
      var buttons = indicatorSwitcher.querySelectorAll('.palette-btn');
      for (var j = 0; j < buttons.length; j++) {
        var btn = buttons[j];
        if (btn.getAttribute('data-indicator') === indicatorType) {
          btn.classList.add('palette-btn--active');
        } else {
          btn.classList.remove('palette-btn--active');
        }
      }
    }

    // Уведомляем live-stepper о смене индикатора
    if (stepperPreview && stepperPreview._stepperInstance) {
      stepperPreview._stepperInstance.setIndicatorType(indicatorType);
    }

    // Сохраняем выбор в localStorage
    try {
      localStorage.setItem('stepper-lab-indicator', indicatorType);
    } catch (_) {
      // Игнорируем ошибки localStorage
    }
  }

  // ── Обработчики событий ────────────────────────────────────

  /**
   * Обработчик клика по кнопке палитры.
   *
   * @param {Event} event — событие клика
   */
  function handlePaletteClick(event) {
    var target = /** @type {HTMLElement} */ (event.target);
    var btn = target.closest('.palette-btn');
    if (!btn) return;

    var theme = btn.getAttribute('data-theme');
    if (theme) {
      setTheme(theme);
    }
  }

  /**
   * Обработчик клика по кнопке шрифта.
   *
   * @param {Event} event — событие клика
   */
  function handleFontClick(event) {
    var target = /** @type {HTMLElement} */ (event.target);
    var btn = target.closest('.palette-btn');
    if (!btn) return;

    var font = btn.getAttribute('data-font');
    if (font) {
      setFont(font);
    }
  }

  /**
   * Обработчик клика по кнопке индикатора.
   *
   * @param {Event} event — событие клика
   */
  function handleIndicatorClick(event) {
    var target = /** @type {HTMLElement} */ (event.target);
    var btn = target.closest('.palette-btn');
    if (!btn) return;

    var indicatorType = btn.getAttribute('data-indicator');
    if (indicatorType) {
      setIndicator(indicatorType);
    }
  }

  // ── Инициализация ──────────────────────────────────────────

  function init() {
    // Вешаем обработчики
    if (paletteSwitcher) {
      paletteSwitcher.addEventListener('click', handlePaletteClick);
    }
    if (fontSwitcher) {
      fontSwitcher.addEventListener('click', handleFontClick);
    }
    if (indicatorSwitcher) {
      indicatorSwitcher.addEventListener('click', handleIndicatorClick);
    }

    // Восстанавливаем сохранённую тему
    var savedTheme = null;
    try {
      savedTheme = localStorage.getItem('stepper-lab-theme');
    } catch (_) {
      /* игнорируем */
    }

    if (savedTheme && THEME_NAMES[savedTheme]) {
      setTheme(savedTheme);
    }
    // Иначе остаётся класс theme-biochrome, заданный в HTML по умолчанию

    // Восстанавливаем сохранённый шрифт
    var savedFont = null;
    try {
      savedFont = localStorage.getItem('stepper-lab-font');
    } catch (_) {
      /* игнорируем */
    }

    if (savedFont && FONT_NAMES[savedFont]) {
      setFont(savedFont);
    }
    // Иначе остаётся класс font-inter, заданный в HTML по умолчанию

    // Восстанавливаем сохранённый индикатор
    var savedIndicator = null;
    try {
      savedIndicator = localStorage.getItem('stepper-lab-indicator');
    } catch (_) {
      /* игнорируем */
    }

    if (savedIndicator && INDICATOR_NAMES[savedIndicator]) {
      setIndicator(savedIndicator);
    }
    // Иначе остаётся класс по умолчанию из HTML (stepper-indicator--inline)
  }

  // Запуск после полной загрузки DOM
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
