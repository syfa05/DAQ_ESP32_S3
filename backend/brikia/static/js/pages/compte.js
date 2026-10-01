import { api } from '../lib/api.js';
import { toast } from '../lib/ui.js';

const form = document.getElementById('pwd-form');
const errorBox = document.getElementById('pwd-error');

form.addEventListener('submit', async (ev) => {
  ev.preventDefault();
  errorBox.hidden = true;
  const fail = (m) => { errorBox.textContent = m; errorBox.hidden = false; };
  if (form.new.value !== form.confirm.value) return fail('Les mots de passe diffèrent.');
  const btn = form.querySelector('button');
  btn.disabled = true;
  try {
    await api('POST', '/api/auth/password', { json: {
      current_password: form.current.value, new_password: form.new.value } });
    form.reset();
    toast('Mot de passe modifié. Vos autres sessions ont été fermées.');
  } catch (e) { fail(e.message); } finally { btn.disabled = false; }
});
