// Client API : jeton CSRF sur les requêtes modifiantes, erreurs en français.
export class ApiError extends Error {
  constructor(message, status, code) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

const csrf = () => document.querySelector('meta[name="csrf-token"]')?.content || '';

export async function api(method, url, { json, form } = {}) {
  const headers = { Accept: 'application/json' };
  if (method !== 'GET') headers['X-CSRF-Token'] = csrf();
  let body;
  if (json !== undefined) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(json);
  } else if (form) {
    body = form;
  }
  let res;
  try {
    res = await fetch(url, { method, headers, body, credentials: 'same-origin' });
  } catch {
    throw new ApiError('Le serveur BrikIA est injoignable. Vérifiez la connexion au réseau local.', 0, 'reseau');
  }
  if (res.status === 204) { await res.arrayBuffer(); return null; } // draine le corps (évite un ERR_ABORTED)
  let data = null;
  try { data = await res.json(); } catch { /* corps non JSON */ }
  if (res.status === 401 && !url.startsWith('/api/auth/login')) {
    location.href = '/connexion?suivant=' + encodeURIComponent(location.pathname);
    throw new ApiError('Session expirée. Veuillez vous reconnecter.', 401, 'non_authentifie');
  }
  if (!res.ok) throw new ApiError(data?.detail || 'Une erreur est survenue.', res.status, data?.code);
  return data;
}

export const get = (url) => api('GET', url);
export const post = (url, json) => api('POST', url, json === undefined ? {} : { json });
export const put = (url, json) => api('PUT', url, { json });
export const patch = (url, json) => api('PATCH', url, { json });
export const del = (url) => api('DELETE', url);
