import { get, put } from '../lib/api.js';
import { h, replace } from '../lib/dom.js';
import * as fmt from '../lib/format.js';
import { CATEGORY_LABELS, busy, showError, toast } from '../lib/ui.js';

const form = document.getElementById('rates-form');
const errorBox = document.getElementById('rates-error');
const info = document.getElementById('rates-info');
const box = document.getElementById('costs');
let shapes = [];
const previews = [];

const rates = () => ({ taux: Number(form.taux_fcfa_par_eur.value) || 0, marge: Number(form.marge_pct.value) || 0 });

function updatePreviews() {
  const { taux, marge } = rates();
  for (const { input, eur, fcfa } of previews) {
    const c = Number(input.value);
    if (input.value === '' || Number.isNaN(c)) { eur.textContent = '—'; fcfa.textContent = '—'; continue; }
    const unit = c * (1 + marge / 100);
    eur.textContent = `${unit.toFixed(2).replace('.', ',')} €`;
    fcfa.textContent = `${fmt.int(Math.round(unit * taux))} FCFA`;
  }
}

function drawCosts() {
  previews.length = 0;
  replace(box, h('table', {},
    h('thead', {}, h('tr', {}, ['Code', 'Moule', 'Poids', 'Coût de revient (€/bloc)', 'Prix de vente HT (aperçu)', ''].map((t) => h('th', {}, t)))),
    h('tbody', {}, shapes.map((s) => {
      const input = h('input', { class: 'cost-input', type: 'number', min: 0, step: '0.01', value: s.cout_unitaire_eur ?? '', 'aria-label': `Coût ${s.code}` });
      const eur = h('span', { class: 'mono' }), fcfa = h('span', { class: 'mono muted' });
      previews.push({ input, eur, fcfa });
      input.addEventListener('input', updatePreviews);
      const save = h('button', { class: 'btn btn-secondary btn-sm', type: 'button' }, 'Enregistrer');
      save.addEventListener('click', () => busy(save, async () => {
        try {
          await put(`/api/moulds/${s.id}`, { cout_unitaire_eur: input.value === '' ? null : input.value });
          s.cout_unitaire_eur = input.value === '' ? null : input.value;
          toast(`Coût de ${s.code} enregistré.`);
        } catch (e) { showError(e); }
      }));
      return h('tr', {}, h('td', { class: 'mono' }, s.code),
        h('td', {}, s.nom, h('div', { class: 'muted small' }, CATEGORY_LABELS[s.categorie] || s.categorie)),
        h('td', { class: 'mono small' }, s.poids_g ? `${(s.poids_g / 1000).toLocaleString('fr-FR')} kg` : '—'),
        h('td', {}, input), h('td', {}, eur, ' · ', fcfa), h('td', {}, save));
    }))));
  updatePreviews();
}

async function load() {
  try {
    const t = await get('/api/tarifs');
    for (const k of ['taux_fcfa_par_eur', 'marge_pct', 'tva_pct', 'frais_fixes_eur']) form[k].value = t[k];
    info.textContent = `Dernière modification : ${fmt.date(t.updated_at)}`;
    shapes = await get('/api/moulds');
    drawCosts();
  } catch (e) { showError(e); }
}

form.addEventListener('input', updatePreviews);
form.addEventListener('submit', async (ev) => {
  ev.preventDefault();
  errorBox.hidden = true;
  const btn = form.querySelector('button[type=submit]');
  await busy(btn, async () => {
    try {
      await put('/api/tarifs', { taux_fcfa_par_eur: form.taux_fcfa_par_eur.value, marge_pct: form.marge_pct.value,
        tva_pct: form.tva_pct.value, frais_fixes_eur: form.frais_fixes_eur.value });
      toast('Paramètres enregistrés.');
      await load();
    } catch (e) { errorBox.textContent = e.message; errorBox.hidden = false; }
  });
});
load();
