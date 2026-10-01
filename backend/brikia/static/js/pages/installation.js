import { api } from '../lib/api.js';

const form = document.getElementById('setup-form');
const errorBox = document.getElementById('setup-error');

form.addEventListener('submit', async (ev) => {
  ev.preventDefault();
  errorBox.hidden = true;
  const fail = (m) => { errorBox.textContent = m; errorBox.hidden = false; };
  if (form.password.value !== form.confirm.value) return fail('Les mots de passe diffèrent.');
  const btn = form.querySelector('button');
  btn.disabled = true;
  try {
    await api('POST', '/api/setup', { json: {
      nom: form.nom.value.trim(), login: form.login.value.trim(), password: form.password.value } });
    location.href = '/';
  } catch (e) { fail(e.message); btn.disabled = false; }
});
