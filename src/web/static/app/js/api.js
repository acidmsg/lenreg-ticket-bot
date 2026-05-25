/**
 * Модуль API-клиента Mini App.
 * Обёртка над fetch() с автоматическим добавлением заголовка X-Telegram-InitData.
 *
 * @module api
 */

import { getInitData } from './auth.js';

const BASE_PATH = '/api/user';

/**
 * Выполняет GET-запрос к API.
 *
 * @param {string} path — путь относительно /api/user (например, '/doctors')
 * @returns {Promise<any>} распарсенный JSON-ответ
 * @throws {Error} при ошибке сети или API
 */
export async function apiGet(path) {
  const initData = getInitData();
  const headers = {
    'Content-Type': 'application/json',
    'X-Requested-With': 'XMLHttpRequest'
  };
  if (initData) {
    headers['X-Telegram-InitData'] = initData;
  }

  const response = await fetch(`${BASE_PATH}${path}`, {
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
    // Извлекаем сообщение из поля detail (FastAPI формат) или message
    const message = data.detail || data.message || `Ошибка ${response.status}`;
    throw new Error(message);
  }

  return data;
}
