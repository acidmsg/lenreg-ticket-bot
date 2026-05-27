/**
 * Stepper Design Lab — Интерактивный степпер с мок-данными
 *
 * Реализует упрощённый 4-шаговый степпер (пациент → клиника → врач → подтверждение)
 * с переключением стиля индикатора через сайдбар.
 *
 * @module live-stepper
 */

(function () {
  "use strict";

  // ── Мок-данные ─────────────────────────────────────────────

  /** @type {Array<{patient_id: number, fio: string, birthday: string}>} */
  var MOCK_PATIENTS = [
    {
      patient_id: 2343192,
      fio: "Казановский Артём Игоревич",
      birthday: "1990-01-01",
    },
    {
      patient_id: 2509768,
      fio: "Петрова Анна Сергеевна",
      birthday: "1985-05-15",
    },
  ];

  /** @type {Array<{clinic_id: number, name: string, short_name: string, city: string}>} */
  var MOCK_CLINICS = [
    {
      clinic_id: 272,
      name: 'ГБУЗ ЛО "Всеволожская КМБ" Амбулатория Павлово',
      short_name: "Амбулатория Павлово",
      city: "Всеволожск",
    },
    {
      clinic_id: 150,
      name: 'ГБУЗ ЛО "Сертоловская ГБ"',
      short_name: "Сертоловская ГБ",
      city: "Сертолово",
    },
    {
      clinic_id: 310,
      name: 'ГБУЗ ЛО "Токсовская РБ"',
      short_name: "Токсовская РБ",
      city: "Токсово",
    },
  ];

  /** @type {Record<number, Array<{doctor_id: number, name: string, specialty_name: string, free_tickets: number}>>} */
  var MOCK_DOCTORS = {
    272: [
      {
        doctor_id: 12345,
        name: "Мельникова Светлана Владимировна",
        specialty_name: "Стоматология (средний медперсонал)",
        free_tickets: 3,
      },
      {
        doctor_id: 12346,
        name: "Иванов Пётр Сергеевич",
        specialty_name: "Терапия",
        free_tickets: 7,
      },
      {
        doctor_id: 12347,
        name: "Смирнова Елена Васильевна",
        specialty_name: "Неврология",
        free_tickets: 2,
      },
    ],
    150: [
      {
        doctor_id: 22345,
        name: "Кузнецов Алексей Дмитриевич",
        specialty_name: "Хирургия",
        free_tickets: 5,
      },
      {
        doctor_id: 22346,
        name: "Фёдорова Мария Игоревна",
        specialty_name: "Кардиология",
        free_tickets: 1,
      },
    ],
    310: [
      {
        doctor_id: 32345,
        name: "Васильев Дмитрий Николаевич",
        specialty_name: "Офтальмология",
        free_tickets: 4,
      },
      {
        doctor_id: 32346,
        name: "Григорьева Ольга Павловна",
        specialty_name: "Эндокринология",
        free_tickets: 6,
      },
      {
        doctor_id: 32347,
        name: "Николаев Андрей Сергеевич",
        specialty_name: "Терапия",
        free_tickets: 0,
      },
    ],
  };

  // ── Константы шагов ────────────────────────────────────────

  /** @type {string[]} Короткие названия шагов для индикатора */
  var STEP_NAMES = ["пациент", "клиника", "врач", "подтв."];

  /** @type {string[]} Заголовки шагов */
  var STEP_TITLES = [
    "Выберите пациента",
    "Выберите поликлинику",
    "Выберите врача",
    "Подтверждение",
  ];

  /** @type {string[]} Описания шагов */
  var STEP_DESCRIPTIONS = [
    "Для кого записываемся на приём?",
    "В какой поликлинике искать слоты?",
    "К какому врачу хотите записаться?",
    "Проверьте выбранные данные",
  ];

  // ── Рендеринг индикатора ───────────────────────────────────

  /**
   * Рендерит HTML индикатора шагов в зависимости от выбранного стиля.
   *
   * @param {string} indicatorType — CSS-класс стиля индикатора
   * @param {number} currentStep — текущий шаг (0-based)
   * @returns {string} HTML индикатора
   */
  function renderIndicator(indicatorType, currentStep) {
    switch (indicatorType) {
      case "stepper-indicator--inline":
        return renderIndicatorInline(currentStep);
      case "stepper-indicator--cursor":
        return renderIndicatorCursor(currentStep);
      case "stepper-indicator--tabs":
        return renderIndicatorTabs(currentStep);
      case "stepper-indicator--dots":
        return renderIndicatorDots(currentStep);
      case "stepper-indicator--brackets":
        return renderIndicatorBrackets(currentStep);
      default:
        return renderIndicatorInline(currentStep);
    }
  }

  /**
   * Инлайн-терминал: всё в одной строке.
   *
   * @param {number} currentStep — текущий шаг
   * @returns {string} HTML
   */
  function renderIndicatorInline(currentStep) {
    var pct = Math.round((currentStep / (STEP_NAMES.length - 1)) * 100);
    var doneBlocks = "";
    var leftBlocks = "";
    var totalBlocks = 12;
    var doneCount = Math.round(
      (currentStep / (STEP_NAMES.length - 1)) * totalBlocks,
    );
    for (var i = 0; i < doneCount; i++) {
      doneBlocks += "\u2593";
    }
    for (var j = doneCount; j < totalBlocks; j++) {
      leftBlocks += "\u2591";
    }

    return (
      '<div class="stepper-term-inline">' +
      '<span class="tmi-prefix">></span>' +
      '<span class="tmi-label">step ' +
      (currentStep + 1) +
      "/" +
      STEP_NAMES.length +
      " : " +
      STEP_NAMES[currentStep] +
      "</span>" +
      '<span class="tmi-bar">' +
      '<span class="tmi-bar__done">' +
      doneBlocks +
      "</span>" +
      '<span class="tmi-bar__left">' +
      leftBlocks +
      "</span>" +
      "</span>" +
      '<span class="tmi-pct">' +
      pct +
      "%</span>" +
      "</div>"
    );
  }

  /**
   * Курсор-терминал: мигающий блочный курсор.
   *
   * @param {number} currentStep — текущий шаг
   * @returns {string} HTML
   */
  function renderIndicatorCursor(currentStep) {
    var doneBlocks = "";
    var leftBlocks = "";
    var totalBlocks = 12;
    var doneCount = Math.round(
      (currentStep / (STEP_NAMES.length - 1)) * totalBlocks,
    );
    for (var i = 0; i < doneCount; i++) {
      doneBlocks += "\u2593";
    }
    for (var j = doneCount; j < totalBlocks; j++) {
      leftBlocks += "\u2591";
    }

    return (
      '<div class="stepper-term-cursor">' +
      '<div class="tmc-line">' +
      '<span class="tmc-prefix">></span>' +
      '<span class="tmc-name">' +
      STEP_NAMES[currentStep] +
      "</span>" +
      '<span class="tmc-cursor">\u2588</span>' +
      "</div>" +
      '<div class="tmc-bar">' +
      '<span class="tmc-bar__done">' +
      doneBlocks +
      "</span>" +
      '<span class="tmc-bar__left">' +
      leftBlocks +
      "</span>" +
      '<span class="tmc-pos">' +
      (currentStep + 1) +
      "/" +
      STEP_NAMES.length +
      "</span>" +
      "</div>" +
      "</div>"
    );
  }

  /**
   * Терминал-табы: названия шагов как вкладки.
   *
   * @param {number} currentStep — текущий шаг
   * @returns {string} HTML
   */
  function renderIndicatorTabs(currentStep) {
    var html = '<div class="stepper-term-tabs">';
    for (var i = 0; i < STEP_NAMES.length; i++) {
      var cls = "tmt-tab";
      if (i < currentStep) cls += " tmt-tab--done";
      else if (i === currentStep) cls += " tmt-tab--current";
      else cls += " tmt-tab--future";
      html += '<span class="' + cls + '">' + STEP_NAMES[i] + "</span>";
    }
    html += "</div>";
    return html;
  }

  /**
   * Пиксельные точки: ряд из 4 квадратов.
   *
   * @param {number} currentStep — текущий шаг
   * @returns {string} HTML
   */
  function renderIndicatorDots(currentStep) {
    var html = '<div class="stepper-dots">';
    for (var i = 0; i < STEP_NAMES.length; i++) {
      var cls = "dot-step";
      if (i < currentStep) cls += " dot-step--done";
      else if (i === currentStep) cls += " dot-step--current";
      else cls += " dot-step--future";
      html += '<span class="' + cls + '"></span>';
    }
    html += "</div>";
    return html;
  }

  /**
   * Угловые скобки: минималистичная навигация в стиле кода.
   *
   * @param {number} currentStep — текущий шаг
   * @returns {string} HTML
   */
  function renderIndicatorBrackets(currentStep) {
    var html = '<div class="stepper-brackets">';
    html += '<span class="bracket-angle bracket-angle--open"><</span>';
    for (var i = 0; i < STEP_NAMES.length; i++) {
      var cls = "bracket-step";
      if (i < currentStep) cls += " bracket-step--done";
      else if (i === currentStep) cls += " bracket-step--current";
      else cls += " bracket-step--future";
      html += '<span class="' + cls + '">' + STEP_NAMES[i] + "</span>";
      if (i < STEP_NAMES.length - 1) {
        html += '<span class="bracket-sep">·</span>';
      }
    }
    html += '<span class="bracket-angle bracket-angle--close">/></span>';
    html += "</div>";
    return html;
  }

  // ── Рендеринг элементов списка ─────────────────────────────

  /**
   * Рендерит элемент списка пациентов.
   *
   * @param {object} patient — данные пациента
   * @param {number} index — индекс в массиве
   * @returns {string} HTML
   */
  function renderPatientItem(patient, index) {
    return (
      '<li class="list__item stepper-item" data-index="' +
      index +
      '">' +
      "<span>\u{1F9D1}</span>" +
      '<div class="list__item-content">' +
      '<div class="list__item-title">' +
      escapeHtml(patient.fio) +
      "</div>" +
      '<div class="list__item-subtitle">' +
      escapeHtml(patient.birthday) +
      " · ID: " +
      patient.patient_id +
      "</div>" +
      "</div>" +
      '<span class="list__item-arrow">\u203A</span>' +
      "</li>"
    );
  }

  /**
   * Рендерит элемент списка клиник.
   *
   * @param {object} clinic — данные клиники
   * @param {number} index — индекс в массиве
   * @returns {string} HTML
   */
  function renderClinicItem(clinic, index) {
    return (
      '<li class="list__item stepper-item" data-index="' +
      index +
      '">' +
      "<span>\u{1F3E5}</span>" +
      '<div class="list__item-content">' +
      '<div class="list__item-title">' +
      escapeHtml(clinic.short_name) +
      "</div>" +
      '<div class="list__item-subtitle">' +
      escapeHtml(clinic.city) +
      "</div>" +
      "</div>" +
      '<span class="list__item-arrow">\u203A</span>' +
      "</li>"
    );
  }

  /**
   * Рендерит элемент списка врачей.
   *
   * @param {object} doctor — данные врача
   * @param {number} index — индекс в массиве
   * @returns {string} HTML
   */
  function renderDoctorItem(doctor, index) {
    var ticketsHtml =
      doctor.free_tickets > 0
        ? '<span class="list__item-badge list__item-badge--success">' +
          doctor.free_tickets +
          " талонов</span>"
        : '<span class="list__item-badge list__item-badge--danger">нет талонов</span>';

    return (
      '<li class="list__item stepper-item" data-index="' +
      index +
      '">' +
      "<span>\u{1FA7A}</span>" +
      '<div class="list__item-content">' +
      '<div class="list__item-title">' +
      escapeHtml(doctor.name) +
      "</div>" +
      '<div class="list__item-subtitle">' +
      escapeHtml(doctor.specialty_name) +
      "</div>" +
      "</div>" +
      ticketsHtml +
      '<span class="list__item-arrow">\u203A</span>' +
      "</li>"
    );
  }

  /**
   * Рендерит блок подтверждения.
   *
   * @param {object} patient — выбранный пациент
   * @param {object} clinic — выбранная клиника
   * @param {object} doctor — выбранный врач
   * @returns {string} HTML
   */
  function renderConfirmContent(patient, clinic, doctor) {
    return (
      '<div class="stepper-confirm">' +
      '<div class="confirm-row">' +
      '<span class="confirm-label">Пациент</span>' +
      '<span class="confirm-value">' +
      escapeHtml(patient.fio) +
      "</span>" +
      "</div>" +
      '<div class="confirm-row">' +
      '<span class="confirm-label">Дата рождения</span>' +
      '<span class="confirm-value">' +
      escapeHtml(patient.birthday) +
      "</span>" +
      "</div>" +
      '<div class="confirm-row">' +
      '<span class="confirm-label">Поликлиника</span>' +
      '<span class="confirm-value">' +
      escapeHtml(clinic.short_name) +
      " (" +
      escapeHtml(clinic.city) +
      ")</span>" +
      "</div>" +
      '<div class="confirm-row">' +
      '<span class="confirm-label">Врач</span>' +
      '<span class="confirm-value">' +
      escapeHtml(doctor.name) +
      "</span>" +
      "</div>" +
      '<div class="confirm-row">' +
      '<span class="confirm-label">Специальность</span>' +
      '<span class="confirm-value">' +
      escapeHtml(doctor.specialty_name) +
      "</span>" +
      "</div>" +
      '<div class="confirm-row">' +
      '<span class="confirm-label">Свободных талонов</span>' +
      '<span class="confirm-value">' +
      doctor.free_tickets +
      "</span>" +
      "</div>" +
      "</div>"
    );
  }

  // ── Основной класс степпера ────────────────────────────────

  /**
   * Создаёт экземпляр интерактивного степпера.
   *
   * @param {HTMLElement} container — DOM-контейнер для рендеринга
   * @param {string} indicatorType — начальный стиль индикатора
   * @returns {object} объект управления степпером
   */
  function createLiveStepper(container, indicatorType) {
    /** @type {number} Текущий шаг (0-based) */
    var currentStep = 0;

    /** @type {Array} Выбранные значения */
    var selections = [];

    /** @type {string} Текущий стиль индикатора */
    var currentIndicatorType = indicatorType || "stepper-indicator--inline";

    /**
     * Рендерит степпер целиком.
     */
    function render() {
      // Шаг 3 (подтверждение) — особый рендеринг
      if (currentStep === 3) {
        renderConfirm();
        return;
      }

      var data = getStepData();
      var title = STEP_TITLES[currentStep];
      var description = STEP_DESCRIPTIONS[currentStep];
      var indicatorHtml = renderIndicator(currentIndicatorType, currentStep);
      var itemsHtml = renderItems(data, currentStep);

      var canGoBack = currentStep > 0;
      var backButtonHtml = canGoBack
        ? '<button class="btn btn--secondary" id="stepper-back">← Назад</button>'
        : '<button class="btn btn--danger" id="stepper-cancel">✕ Отмена</button>';

      container.innerHTML =
        '<div class="stepper">' +
        '<div class="stepper__progress">' +
        indicatorHtml +
        "</div>" +
        '<h2 class="stepper__title">' +
        escapeHtml(title) +
        "</h2>" +
        '<p class="stepper__description">' +
        escapeHtml(description) +
        "</p>" +
        '<div class="stepper__content">' +
        '<ul class="list">' +
        itemsHtml +
        "</ul>" +
        "</div>" +
        '<div class="stepper__actions">' +
        backButtonHtml +
        '<button class="btn btn--primary stepper__btn--next" id="stepper-next" disabled>Далее →</button>' +
        "</div>" +
        "</div>";

      bindEvents();
    }

    /**
     * Рендерит шаг подтверждения.
     */
    function renderConfirm() {
      var patient = selections[0];
      var clinic = selections[1];
      var doctor = selections[2];

      var indicatorHtml = renderIndicator(currentIndicatorType, currentStep);
      var confirmHtml = renderConfirmContent(patient, clinic, doctor);

      container.innerHTML =
        '<div class="stepper">' +
        '<div class="stepper__progress">' +
        indicatorHtml +
        "</div>" +
        '<h2 class="stepper__title">' +
        escapeHtml(STEP_TITLES[3]) +
        "</h2>" +
        '<p class="stepper__description">' +
        escapeHtml(STEP_DESCRIPTIONS[3]) +
        "</p>" +
        '<div class="stepper__content">' +
        confirmHtml +
        "</div>" +
        '<div class="stepper__actions">' +
        '<button class="btn btn--secondary" id="stepper-back">← Назад</button>' +
        '<button class="btn btn--primary" id="stepper-done">✓ Готово</button>' +
        "</div>" +
        "</div>";

      bindConfirmEvents();
    }

    /**
     * Возвращает данные для текущего шага.
     *
     * @returns {Array} массив элементов
     */
    function getStepData() {
      switch (currentStep) {
        case 0:
          return MOCK_PATIENTS;
        case 1:
          return MOCK_CLINICS;
        case 2: {
          var clinic = selections[1];
          return MOCK_DOCTORS[clinic.clinic_id] || [];
        }
        default:
          return [];
      }
    }

    /**
     * Рендерит элементы списка для текущего шага.
     *
     * @param {Array} data — данные
     * @param {number} stepIndex — индекс шага
     * @returns {string} HTML
     */
    function renderItems(data, stepIndex) {
      if (!data || data.length === 0) {
        return '<div class="empty-state"><div class="empty-state__icon">📭</div><p class="empty-state__text">Ничего не найдено</p></div>';
      }

      var html = "";
      for (var i = 0; i < data.length; i++) {
        switch (stepIndex) {
          case 0:
            html += renderPatientItem(data[i], i);
            break;
          case 1:
            html += renderClinicItem(data[i], i);
            break;
          case 2:
            html += renderDoctorItem(data[i], i);
            break;
        }
      }
      return html;
    }

    /**
     * Привязывает обработчики событий для шагов выбора.
     */
    function bindEvents() {
      // Кнопка «Назад»
      var backBtn = document.getElementById("stepper-back");
      if (backBtn) {
        backBtn.addEventListener("click", function () {
          if (currentStep > 0) {
            currentStep--;
            selections.pop();
            render();
          }
        });
      }

      // Кнопка «Отмена»
      var cancelBtn = document.getElementById("stepper-cancel");
      if (cancelBtn) {
        cancelBtn.addEventListener("click", function () {
          reset();
        });
      }

      // Выбор элемента списка — автопереход
      var items = container.querySelectorAll(".stepper-item");
      for (var i = 0; i < items.length; i++) {
        items[i].addEventListener(
          "click",
          (function (item) {
            return function () {
              // Снимаем выделение со всех
              var allItems = container.querySelectorAll(".stepper-item");
              for (var k = 0; k < allItems.length; k++) {
                allItems[k].classList.remove("stepper-item--selected");
              }
              // Выделяем текущий
              item.classList.add("stepper-item--selected");

              // Автопереход
              var idx = parseInt(item.getAttribute("data-index"), 10);
              if (!isNaN(idx)) {
                var data = getStepData();
                if (data[idx]) {
                  selections.push(data[idx]);
                  currentStep++;
                  render();
                }
              }
            };
          })(items[i]),
        );
      }
    }

    /**
     * Привязывает обработчики для шага подтверждения.
     */
    function bindConfirmEvents() {
      // Кнопка «Назад»
      var backBtn = document.getElementById("stepper-back");
      if (backBtn) {
        backBtn.addEventListener("click", function () {
          currentStep--;
          selections.pop();
          render();
        });
      }

      // Кнопка «Готово»
      var doneBtn = document.getElementById("stepper-done");
      if (doneBtn) {
        doneBtn.addEventListener("click", function () {
          var patient = selections[0];
          var clinic = selections[1];
          var doctor = selections[2];

          var message =
            "Пациент: " +
            patient.fio +
            "\n" +
            "Дата рождения: " +
            patient.birthday +
            "\n" +
            "Поликлиника: " +
            clinic.short_name +
            " (" +
            clinic.city +
            ")\n" +
            "Врач: " +
            doctor.name +
            "\n" +
            "Специальность: " +
            doctor.specialty_name +
            "\n" +
            "Свободных талонов: " +
            doctor.free_tickets;

          alert(message);
        });
      }
    }

    /**
     * Сбрасывает степпер в начальное состояние.
     */
    function reset() {
      currentStep = 0;
      selections = [];
      render();
    }

    // ── Публичный API ─────────────────────────────────────────

    /** @type {object} Экземпляр степпера */
    var instance = {
      /**
       * Меняет стиль индикатора и перерисовывает степпер.
       *
       * @param {string} newType — CSS-класс стиля индикатора
       */
      setIndicatorType: function (newType) {
        currentIndicatorType = newType;
        render();
      },

      /** Сбрасывает степпер */
      reset: reset,

      /** Возвращает текущие выбранные значения */
      getSelections: function () {
        return selections.slice();
      },
    };

    // Сохраняем ссылку на instance в контейнере для доступа из switcher.js
    container._stepperInstance = instance;

    // Первичный рендер
    render();

    return instance;
  }

  // ── Утилиты ────────────────────────────────────────────────

  /**
   * Экранирует HTML-символы.
   *
   * @param {string} text — исходный текст
   * @returns {string} экранированный текст
   */
  function escapeHtml(text) {
    var div = document.createElement("div");
    div.textContent = String(text);
    return div.innerHTML;
  }

  // ── Инициализация ──────────────────────────────────────────

  function init() {
    var container = document.getElementById("stepper-preview");
    if (!container) return;

    // Определяем начальный стиль индикатора
    var initialIndicator = "stepper-indicator--inline";
    try {
      var saved = localStorage.getItem("stepper-lab-indicator");
      if (saved) {
        initialIndicator = saved;
      }
    } catch (_) {
      /* игнорируем */
    }

    createLiveStepper(container, initialIndicator);
  }

  // Запуск после полной загрузки DOM
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
