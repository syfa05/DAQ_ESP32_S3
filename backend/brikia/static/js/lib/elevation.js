// Élévation d'un mur ASSISE PAR ASSISE : chaque bloc posé est dessiné à l'échelle (en mm).
import { h, svg } from './dom.js';
import { CATEGORY_LABELS } from './ui.js';

const GUTTER = 520;      // marge gauche : numéros d'assises
const FOOT = 380;        // marge basse : cote de longueur

export function elevation(body) {
  const d = body.detail;
  const shapes = Object.fromEntries(body.formes.map((s) => [s.id, s]));
  const L = d.longueur_mm;
  const hc = d.hauteur_assise_mm;
  const H = d.assises * hc;
  const root = svg('svg', { class: 'elev-svg', viewBox: `0 0 ${L + GUTTER + 60} ${H + FOOT + 80}`,
    role: 'img', 'aria-label': `Élévation de ${body.wall_nom}, ${d.assises} assises` });
  root.append(svg('defs', {}, svg('pattern', { id: 'hatch', width: 120, height: 120, patternUnits: 'userSpaceOnUse',
    patternTransform: 'rotate(45)' }, svg('line', { x1: 0, y1: 0, x2: 0, y2: 120, class: 'el-hatch' }))));
  const g = svg('g', { transform: `translate(${GUTTER} 40)` });
  root.append(g);

  d.courses.forEach((runs, c) => {
    const y = (d.assises - 1 - c) * hc;
    for (const [x, shape, plen, n, cut] of runs) {
      if (shape === 0) {
        g.append(svg('rect', { class: 'el-void', x, y, width: plen, height: hc, fill: 'url(#hatch)' }));
        continue;
      }
      const s = shapes[shape] || { code: `#${shape}`, categorie: 'standard' };
      for (let i = 0; i < n; i++) {
        const r = svg('rect', { class: `el-block cat-${s.categorie}${cut ? ' el-cut' : ''}`,
          x: x + i * plen, y, width: plen, height: hc });
        r.append(svg('title', {}, `${s.code} · ${plen} mm${cut ? ' (coupé)' : ''} · assise ${c + 1}`));
        g.append(r);
      }
    }
    g.append(svg('text', { class: 'el-axis', x: -60, y: y + hc * 0.68, 'text-anchor': 'end' }, String(c + 1)));
  });
  for (const o of d.ouvertures) {
    g.append(svg('text', { class: 'el-label', x: o.x + o.largeur / 2, y: (d.assises - 1 - o.c0) * hc - (o.c1 - o.c0 - 1) * hc / 2 + hc * 0.15,
      'text-anchor': 'middle' }, `${o.type} ${o.largeur}×${o.hauteur}${o.position_estimee ? ' (position estimée)' : ''}`));
  }
  g.append(svg('line', { class: 'el-dim', x1: 0, y1: H + 150, x2: L, y2: H + 150 }),
    svg('text', { class: 'el-axis', x: L / 2, y: H + 330, 'text-anchor': 'middle' }, `${L} mm`));
  return h('div', { class: 'elev' }, root);
}

export function courseSummary(body) {
  const d = body.detail;
  const shapes = Object.fromEntries(body.formes.map((s) => [s.id, s]));
  return d.courses.map((runs, c) => {
    const count = {};
    const cuts = [];
    let voids = 0;
    for (const [, shape, plen, n, cut] of runs) {
      if (shape === 0) { voids += plen; continue; }
      const code = (shapes[shape] || {}).code || `#${shape}`;
      count[code] = (count[code] || 0) + n;
      if (cut) cuts.push(`${code} coupé à ${plen} mm`);
    }
    const parts = Object.entries(count).map(([k, v]) => `${v} × ${k}`);
    if (voids) parts.push(`vide ${voids} mm`);
    return { n: c + 1, from: c * d.hauteur_assise_mm, text: parts.join(' · '), cuts };
  }).reverse();
}

export function legend(body) {
  const cats = [...new Set(body.formes.map((s) => s.categorie))];
  return h('div', { class: 'elev-legend' }, cats.map((c) =>
    h('span', {}, h('span', { class: `sw cat-${c}` }), CATEGORY_LABELS[c] || c)),
  h('span', {}, h('span', { class: 'sw el-cut-sw' }), 'pièce coupée'),
  h('span', {}, h('span', { class: 'sw el-void-sw' }), 'ouverture'));
}
