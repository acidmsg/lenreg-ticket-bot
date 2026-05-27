/**
 * Модуль API-клиента Mini App.
 * Обёртка над fetch() с автоматическим добавлением заголовка X-Telegram-InitData.
 *
 * @module api
 */

import { getInitData, getInitDataError } from './auth.js';

const BASE_PATH = '/api/user';

/**
 * Проверяет наличие initData и выбрасывает ошибку с понятным сообщением.
 *
 * @throws {Error} если initData пуст в Telegram-окружении
 */
function requireInitData() {
  const error = getInitDataError();
  if (error) {
    throw new Error(error);
  }
}

/**
 * Выполняет GET-запрос к API.
 *
 * @param {string} path — путь относительно /api/user (например, '/doctors')
 * @param {object} [params={}] — query-параметры (например, { clinic_id: 123 })
 * @returns {Promise<any>} распарсенный JSON-ответ
 * @throws {Error} при ошибке сети или API
 */
export async function apiGet(path, params = {}) {
  requireInitData();

  const initData = getInitData();
  const headers = {
    'Content-Type': 'application/json',
    'X-Requested-With': 'XMLHttpRequest'
  };
  if (initData) {
    headers['X-Telegram-InitData'] = initData;
  }

  // Собираем query-строку из params
  const queryParts = [];
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null) {
      queryParts.push(
        `${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`
      );
    }
  }
  const queryString = queryParts.length > 0 ? `?${queryParts.join('&')}` : '';

  const response = await fetch(`${BASE_PATH}${path}${queryString}`, {
    method: 'GET',
    headers
  });

  return handleResponse(response);
}

/**
 * Выполняет POST-запрос к API.
 *
 * @param {string} path — путь относительно /api/user (например, '/doctors/add')
 * @param {object} [body={}] — тело запроса (сериализуется в JSON)
 * @returns {Promise<any>} распарсенный JSON-ответ
 * @throws {Error} при ошибке сети или API
 */
export async function apiPost(path, body = {}) {
  requireInitData();

  const initData = getInitData();
  const headers = {
    'Content-Type': 'application/json',
    'X-Requested-With': 'XMLHttpRequest'
  };
  if (initData) {
    headers['X-Telegram-InitData'] = initData;
  }

  const response = await fetch(`${BASE_PATH}${path}`, {
    method: 'POST',
    headers,
    body: JSON.stringify(body)
  });

  return handleResponse(response);
}

/**
 * Выполняет DELETE-запрос к API.
 *
 * @param {string} path — путь относительно /api/user (например, '/doctors/123_456')
 * @returns {Promise<any>} распарсенный JSON-ответ
 * @throws {Error} при ошибке сети или API
 */
export async function apiDelete(path) {
  requireInitData();

  const initData = getInitData();
  const headers = {
    'Content-Type': 'application/json',
    'X-Requested-With': 'XMLHttpRequest'
  };
  if (initData) {
    headers['X-Telegram-InitData'] = initData;
  }

  const response = await fetch(`${BASE_PATH}${path}`, {
    method: 'DELETE',
    headers
  });

  return handleResponse(response);
}

/**
 * Обрабатывает ответ от сервера: парсит JSON, выбрасывает ошибку при неуспехе.
 *
 * @param {Response} response — объект ответа fetch
 * @returns {Promise<any>} распарсенный JSON
 * @throws {Error} с сообщением из response.json().detail или текстом статуса
 */
async function handleResponse(response) {
  let data;
  try {
    data = await response.json();
  } catch {
    // Ответ не является JSON (например, HTML-ошибка)
    if (!response.ok) {
      throw new Error(
        `Ошибка сервера: ${response.status} ${response.statusText}`
      );
    }
    return null;
  }

  if (!response.ok) {
    // Извлекаем читаемое сообщение из поля detail (FastAPI формат) или message
    let message = `Ошибка ${response.status}`;
    if (Array.isArray(data.detail)) {
      // FastAPI validation errors: массив объектов [{msg, ...}, ...]
      message = data.detail.map((e) => e.msg || JSON.stringify(e)).join('; ');
    } else if (typeof data.detail === 'string') {
      message = data.detail;
    } else if (data.message) {
      message = data.message;
    }
    throw new Error(message);
  }

  return data;
}
