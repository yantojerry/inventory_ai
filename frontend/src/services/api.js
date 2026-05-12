export const API = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8010';
const TOKEN_KEY = 'inventory_ai_token';

export function getAuthToken() {
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setAuthToken(token) {
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearAuthToken() {
  window.localStorage.removeItem(TOKEN_KEY);
}

export async function apiFetch(path, options = {}) {
  const token = getAuthToken();
  const response = await fetch(`${API}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers || {}),
    },
    ...options,
  });
  if (!response.ok) {
    const text = await response.text();
    let payload = {};
    if (text) {
      try {
        payload = JSON.parse(text);
      } catch {
        payload = { detail: text };
      }
    }
    const detail = payload.detail;
    const message = Array.isArray(detail)
      ? detail.map((entry) => (typeof entry === 'string' ? entry : entry?.msg || JSON.stringify(entry))).join('; ')
      : typeof detail === 'object' && detail !== null
        ? detail.message || JSON.stringify(detail)
        : detail || text || `API error ${response.status}`;
    throw new Error(message);
  }
  return response.status === 204 ? null : response.json();
}
