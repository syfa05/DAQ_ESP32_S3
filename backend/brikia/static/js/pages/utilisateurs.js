import { api, get } from '../lib/api.js';
import { h, replace } from '../lib/dom.js';
import { busy, confirmDialog, showError, toast } from '../lib/ui.js';

const ROLES = { chef_projet: 'Chef de projet', operateur: 'Opérateur' };
const box = document.getElementById('users');
const form = document.getElementById('user-form');
const errorBox = document.getElementById('user-error');
const me = document.body.dataset.login;

async function toggle(u, btn) {
  const ok = await confirmDialog({
    title: u.actif ? 'Désactiver ce compte ?' : 'Réactiver ce compte ?',
    body: u.actif ? `« ${u.login} » ne pourra plus se connecter et sera déconnecté.`
      : `« ${u.login} » pourra de nouveau se connecter.`,
    confirmLabel: u.actif ? 'Désactiver' : 'Réactiver', danger: u.actif });
  if (!ok) return;
  await busy(btn, async () => {
    try { await api('POST', `/api/users/${u.id}/actif`, { json: { actif: !u.actif } }); await load(); }
    catch (e) { showError(e); }
  });
}

async function resetPassword(u, btn) {
  const input = h('input', { type: 'password', autocomplete: 'new-password', 'aria-label': 'Nouveau mot de passe' });
  const ok = await confirmDialog({
    title: `Nouveau mot de passe pour « ${u.login} »`,
    body: h('div', {}, h('p', { class: 'muted' }, '8 caractères minimum. Ses sessions ouvertes seront fermées.'), input),
    confirmLabel: 'Réinitialiser' });
  if (!ok) return;
  await busy(btn, async () => {
    try {
      await api('POST', `/api/users/${u.id}/mot-de-passe`, { json: { password: input.value } });
      toast(`Mot de passe de « ${u.login} » réinitialisé.`);
    } catch (e) { showError(e); }
  });
}

function draw(users) {
  replace(box, h('table', {},
    h('thead', {}, h('tr', {}, ...['Nom', 'Identifiant', 'Rôle', 'Statut', ''].map((t) => h('th', {}, t)))),
    h('tbody', {}, users.map((u) => {
      const t = h('button', { class: 'btn btn-ghost btn-sm', type: 'button' }, u.actif ? 'Désactiver' : 'Réactiver');
      t.addEventListener('click', () => toggle(u, t));
      const r = h('button', { class: 'btn btn-ghost btn-sm', type: 'button' }, 'Mot de passe');
      r.addEventListener('click', () => resetPassword(u, r));
      return h('tr', {}, h('td', {}, u.nom), h('td', { class: 'mono' }, u.login),
        h('td', {}, ROLES[u.role] || u.role),
        h('td', {}, u.actif ? 'Actif' : 'Désactivé'),
        h('td', {}, u.login === me ? h('span', { class: 'muted' }, 'vous') : [t, r]));
    }))));
}

async function load() {
  try { draw(await get('/api/users')); } catch (e) { showError(e); }
}

form.addEventListener('submit', async (ev) => {
  ev.preventDefault();
  errorBox.hidden = true;
  const btn = form.querySelector('button[type=submit]');
  btn.disabled = true;
  try {
    await api('POST', '/api/users', { json: {
      nom: form.nom.value.trim(), login: form.login.value.trim(),
      role: form.role.value, password: form.password.value } });
    toast(`Compte « ${form.login.value.trim().toLowerCase()} » créé.`);
    form.reset();
    await load();
  } catch (e) { errorBox.textContent = e.message; errorBox.hidden = false; }
  finally { btn.disabled = false; }
});
load();
