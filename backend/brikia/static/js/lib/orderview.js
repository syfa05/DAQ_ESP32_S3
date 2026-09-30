// Carte d'un ordre de production, mise à jour sur place (sans reconstruire le DOM).
import { h } from './dom.js';
import { int } from './format.js';
import * as fmt from './format.js';
import { statusBadge } from './ui.js';

export function orderCard(order, { withProject = false } = {}) {
  const badgeHost = h('span');
  const totalText = h('span', { class: 'mono' });
  const totalFill = h('div', { class: 'fill' });
  const totalBar = h('div', { class: 'bar', role: 'progressbar', 'aria-valuemin': 0, 'aria-valuemax': 100 }, totalFill);
  const alarms = h('div');
  const times = h('p', { class: 'note' });
  const lineRefs = new Map();
  const linesGrid = h('div', { class: 'lines' });
  for (const l of order.lignes) {
    const fill = h('div', { class: 'fill' });
    const txt = h('span', { class: 'mono small' });
    lineRefs.set(l.code, { fill, txt });
    linesGrid.append(
      h('span', {}, h('span', { class: 'mono' }, l.code), ' ', h('span', { class: 'muted small' }, l.nom)),
      h('div', { class: 'bar' }, fill), txt);
  }
  const title = withProject
    ? h('h3', {}, h('a', { href: `/projets/${order.project_id}` }, order.project_nom))
    : h('h3', {}, 'Ordre de production');
  const node = h('article', { class: 'card', id: `order-${order.id}` },
    h('div', { class: 'order-head' }, title, h('span', { class: 'muted mono small' }, `lot ${order.lot_id.slice(0, 8)}`), badgeHost),
    totalBar, h('p', { class: 'note' }, totalText), linesGrid, alarms, times);

  function update(o) {
    badgeHost.replaceChildren(statusBadge(o.status));
    totalText.textContent = `${int(o.total_produit)} / ${int(o.total_cible)} blocs — ${o.progression_pct} %`;
    totalFill.style.width = `${o.progression_pct}%`; // CSSOM : autorisé par la CSP (pas d'attribut style)
    totalBar.setAttribute('aria-valuenow', o.progression_pct);
    totalBar.classList.toggle('done', o.status === 'termine');
    totalBar.classList.toggle('err', o.status === 'erreur');
    for (const l of o.lignes) {
      const r = lineRefs.get(l.code);
      if (!r) continue;
      r.fill.style.width = `${l.cible ? Math.floor((l.produite * 100) / l.cible) : 0}%`;
      r.txt.textContent = `${int(l.produite)} / ${int(l.cible)}`;
    }
    alarms.replaceChildren(...o.alarmes.map((a) => h('p', { class: 'warn', role: 'alert' }, `Alarme : ${a}`)));
    times.textContent = o.completed_at
      ? `Démarré le ${fmt.date(o.started_at)} — clôturé le ${fmt.date(o.completed_at)}`
      : `Démarré le ${fmt.date(o.started_at)}`;
  }
  update(order);
  return { node, update, id: order.id };
}
