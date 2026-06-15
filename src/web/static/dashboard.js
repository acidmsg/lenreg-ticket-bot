// dashboard.js — sidebar: collapsible toggle + mobile overlay
document.addEventListener("DOMContentLoaded", () => {
  const sidebar = document.getElementById("sidebar");
  const toggleBtn = document.getElementById("sidebar-toggle-collapse");
  const hamburger = document.getElementById("sidebar-toggle-mobile");
  const overlay = document.getElementById("sidebar-overlay");
  const mobileQuery = window.matchMedia("(width <= 768px)");

  // ── Инициализация ──
  function init() {
    if (mobileQuery.matches) {
      // Мобильный: sidebar скрыт, hamburger видим, toggle скрыт
      sidebar.classList.remove("sidebar--collapsed");
      if (toggleBtn) toggleBtn.style.display = "none";
      if (hamburger) hamburger.style.display = "";
    } else {
      // Десктоп/планшет: hamburger скрыт, toggle видим
      if (hamburger) hamburger.style.display = "none";
      if (toggleBtn) toggleBtn.style.display = "";
      if (window.innerWidth <= 1024) {
        // Планшет: всегда collapsed при старте
        sidebar.classList.add("sidebar--collapsed");
      } else if (localStorage.getItem("sidebar-collapsed") === "1") {
        // Десктоп: восстановить состояние
        sidebar.classList.add("sidebar--collapsed");
      }
    }
    updateToggleAria();
  }

  // ── Toggle: свернуть/развернуть ──
  function updateToggleAria() {
    if (!toggleBtn) return;
    const collapsed = sidebar.classList.contains("sidebar--collapsed");
    toggleBtn.setAttribute("aria-expanded", String(!collapsed));
    toggleBtn.setAttribute(
      "aria-label",
      collapsed ? "Развернуть меню" : "Свернуть меню",
    );
  }

  toggleBtn?.addEventListener("click", () => {
    const collapsed = sidebar.classList.toggle("sidebar--collapsed");
    localStorage.setItem("sidebar-collapsed", collapsed ? "1" : "0");
    updateToggleAria();
  });

  // ── Mobile overlay ──
  function openOverlay() {
    document.body.classList.add("sidebar-open");
    hamburger?.setAttribute("aria-expanded", "true");
    sidebar.querySelector(".sidebar__link")?.focus();
  }

  function closeOverlay() {
    document.body.classList.remove("sidebar-open");
    hamburger?.setAttribute("aria-expanded", "false");
    hamburger?.focus();
  }

  hamburger?.addEventListener("click", () => {
    document.body.classList.contains("sidebar-open")
      ? closeOverlay()
      : openOverlay();
  });

  overlay?.addEventListener("click", closeOverlay);

  document.addEventListener("keydown", (e) => {
    if (
      e.key === "Escape" &&
      document.body.classList.contains("sidebar-open")
    ) {
      closeOverlay();
    }
  });

  // ── Resize: сброс при пересечении breakpoint'а ──
  mobileQuery.addEventListener("change", (e) => {
    if (e.matches) {
      // → мобильный
      sidebar.classList.remove("sidebar--collapsed");
      if (toggleBtn) toggleBtn.style.display = "none";
      if (hamburger) hamburger.style.display = "";
    } else {
      // → десктоп/планшет
      document.body.classList.remove("sidebar-open");
      if (hamburger) hamburger.style.display = "none";
      if (toggleBtn) toggleBtn.style.display = "";
      if (window.innerWidth <= 1024) {
        sidebar.classList.add("sidebar--collapsed");
      } else if (localStorage.getItem("sidebar-collapsed") === "1") {
        sidebar.classList.add("sidebar--collapsed");
      } else {
        sidebar.classList.remove("sidebar--collapsed");
      }
    }
    updateToggleAria();
  });

  init();
});
