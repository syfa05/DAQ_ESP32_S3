import { api } from '../lib/api.js';

const form = document.getElementById('project-form');
const errorBox = document.getElementById('form-error');
const maxBytes = Number(form.dataset.maxMb) * 1024 * 1024;
const allowed = form.dataset.ext.split(',');

function fail(msg) { errorBox.textContent = msg; errorBox.hidden = false; }

form.addEventListener('submit', async (ev) => {
  ev.preventDefault();
  errorBox.hidden = true;
  const file = form.fichier.files[0];
  if (!form.nom.value.trim()) return fail('Le nom du projet est obligatoire.');
  if (!file) return fail('Sélectionnez le fichier du plan.');
  const ext = '.' + file.name.split('.').pop().toLowerCase();
  if (!allowed.includes(ext)) return fail(`Format non accepté. Formats autorisés : ${allowed.join(', ')}.`);
  if (file.size > maxBytes) return fail(`Fichier trop volumineux (maximum ${form.dataset.maxMb} Mo).`);
  const btn = form.querySelector('button[type=submit]');
  btn.disabled = true;
  try {
    const project = await api('POST', '/api/projects', { form: new FormData(form) });
    location.href = `/projets/${project.id}`;
  } catch (e) { fail(e.message); btn.disabled = false; }
});
