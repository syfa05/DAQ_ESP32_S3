import { get } from '../lib/api.js';
import { h, replace } from '../lib/dom.js';
import * as fmt from '../lib/format.js';
import { PIPELINE, SOURCE_SHORT, STATUS_LABELS, showError, statusBadge } from '../lib/ui.js';

const isChef = document.body.dataset.role === 'chef_projet';
const COLUMNS = isChef ? PIPELINE : ['valide', 'en_production', 'termine'];
const board = document.getElementById('board');

function card(p) {
  return h('a', { class: `pcard st-${p.status}`, href: `/projets/${p.id}` },
    h('div', { class: 't' }, p.nom),
    h('div', { class: 'm' }, [p.ville, p.architecte].filter(Boolean).join(' · ') || '—'),
    h('div', { class: 'm mono' }, `#${p.id} · ${fmt.date(p.created_at)}`,
      p.analysis_source ? h('span', { class: `tag src-${p.analysis_source}` }, SOURCE_SHORT[p.analysis_source] || p.analysis_source) : null));
}

function render(projects) {
  replace(board, ...COLUMNS.map((status) => {
    const items = projects.filter((p) => p.status === status);
    return h('section', { class: 'col', 'aria-label': STATUS_LABELS[status] },
      h('header', {}, h('h2', {}, statusBadge(status)), h('span', { class: 'count' }, items.length)),
      items.length ? items.map(card) : h('p', { class: 'empty' }, 'Aucun projet'));
  }));
}

async function refresh() {
  try {
    const projects = await get('/api/projects');
    render(projects);
    // Une production en cours peut se terminer : on garde la vue à jour.
    if (projects.some((p) => p.status === 'en_production')) setTimeout(refresh, 5000);
  } catch (e) { showError(e); }
}
refresh();
