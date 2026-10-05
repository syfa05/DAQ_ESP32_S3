import { api } from '../lib/api.js';

const form = document.getElementById('login-form');
const errorBox = document.getElementById('login-error');

// Ne redirige que vers un chemin interne (pas de redirection ouverte).
function nextUrl() {
  const s = new URLSearchParams(location.search).get('suivant') || '/';
  return s.startsWith('/') && !s.startsWith('//') ? s : '/';
}

form.addEventListener('submit', async (ev) => {
  ev.preventDefault();
  errorBox.hidden = true;
  const btn = form.querySelector('button');
  btn.disabled = true;
  try {
    await api('POST', '/api/auth/login', { json: {
      login: form.login.value.trim(), password: form.password.value } });
    location.href = nextUrl();
  } catch (e) {
    errorBox.textContent = e.message;
    errorBox.hidden = false;
    form.password.value = '';
    form.password.focus();
  } finally { btn.disabled = false; }
});
