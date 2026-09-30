import { get } from '../lib/api.js';
import { h, replace } from '../lib/dom.js';
import * as fmt from '../lib/format.js';
import { showError } from '../lib/ui.js';

const PAGE = 50;
const ACTIONS = {
  'project.validate': 'Validation de projet',
  'production.start': 'Lancement de production',
  'production.complete': 'Fin de production',
  'production.error': 'Erreur de production',
};
const TARGETS = { project: 'Projet', production_order: 'Ordre de production' };
const box = document.getElementById('audit');
const more = document.getElementById('more');
let offset = 0;
const rows = [];

const detailText = (d) => (d ? Object.entries(d).map(([k, v]) =>
  `${k} : ${typeof v === 'object' ? JSON.stringify(v) : v}`).join(' · ') : '—');

function draw() {
  replace(box, rows.length ? h('table', {},
    h('thead', {}, h('tr', {}, ...['Date', 'Utilisateur', 'Action', 'Cible', 'Détails'].map((t) => h('th', {}, t)))),
    h('tbody', {}, rows.map((r) => h('tr', {},
      h('td', { class: 'mono small' }, fmt.date(r.created_at)), h('td', {}, r.utilisateur),
      h('td', {}, ACTIONS[r.action] || r.action),
      h('td', { class: 'mono' }, `${TARGETS[r.target_type] || r.target_type} #${r.target_id ?? '—'}`),
      h('td', { class: 'mono small' }, detailText(r.details)))))) : h('p', { class: 'muted pad' }, 'Aucune entrée pour le moment.'));
}

async function load() {
  try {
    const page = await get(`/api/audit?limit=${PAGE}&offset=${offset}`);
    rows.push(...page);
    offset += page.length;
    more.hidden = page.length < PAGE;
    draw();
  } catch (e) { showError(e); }
}
more.addEventListener('click', load);
load();
