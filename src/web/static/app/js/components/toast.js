/**
 * Глобальный компонент toast-уведомлений.
 * Экспортирует window.showToast при загрузке модуля.
 *
 * @module components/toast
 */

/**
 * Показывает toast-уведомление внизу экрана.
 * Доступен глобально как window.showToast с момента загрузки модуля.
 *
 * @param {string} message — текст уведомления
 */
function showToast(message) {
  // Удалить старый toast если есть
  const old = document.getElementById('stepper-toast');
  if (old) old.remove();

  const toast = document.createElement('div');
  toast.id = 'stepper-toast';
  toast.className = 'stepper-toast';
  toast.textContent = message;
  document.body.appendChild(toast);

  // Анимация появления
  requestAnimationFrame(() => toast.classList.add('stepper-toast--visible'));

  // Авто-скрытие через 4 секунды
  setTimeout(() => {
    toast.classList.remove('stepper-toast--visible');
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// Экспорт в глобальную область видимости — немедленно при загрузке модуля
window.showToast = showToast;
