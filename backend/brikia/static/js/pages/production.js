import { get } from '../lib/api.js';
import { h, replace } from '../lib/dom.js';
import * as fmt from '../lib/format.js';
import { orderCard } from '../lib/orderview.js';
import { showError } from '../lib/ui.js';

const ordersBox = document.getElementById('orders');
const readyBox = document.getElementById('ready');
let views = new Map();
let timer = null;

function sameSet(orders) {
  return orders.length === views.size && orders.every((o) => views.has(o.id));
}

async function refresh() {
  clearTimeout(timer);
  try {
    const [orders, projects] = await Promise.all([get('/api/production'), get('/api/projects')]);
    const ready = projects.filter((p) => p.status === 'valide');
    replace(readyBox, ready.length ? ready.map((p) => h('a', { class: 'pcard st-valide', href: `/projets/${p.id}` },
      h('div', { class: 't' }, p.nom), h('div', { class: 'm' }, 'Validé — ouvrir pour lancer la production'),
      h('div', { class: 'm mono' }, `#${p.id} · ${fmt.date(p.validated_at)}`)))
      : h('p', { class: 'empty' }, 'Aucun projet validé en attente.'));

    if (!sameSet(orders)) {
      views = new Map(orders.map((o) => [o.id, orderCard(o, { withProject: true })]));
      replace(ordersBox, orders.length ? [...views.values()].map((v) => v.node)
        : h('p', { class: 'empty' }, 'Aucun ordre de production pour le moment.'));
    } else {
      for (const o of orders) views.get(o.id).update(o);
    }
    // Suivi en direct tant qu'un ordre est en cours (ou qu'un projet vient d'être lancé).
    if (orders.some((o) => o.status === 'en_cours')) timer = setTimeout(refresh, 2000);
    else timer = setTimeout(refresh, 10000);
  } catch (e) { showError(e); timer = setTimeout(refresh, 10000); }
}
refresh();
