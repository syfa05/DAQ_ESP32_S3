// Représentation SCHÉMATIQUE d'un mur en grille de blocs colorés par forme.
// Ce n'est ni un rendu physique exact ni une simulation structurelle : la
// disposition est illustrative, les quantités qui font foi sont celles de
// la nomenclature.
import { h, svg } from './dom.js';
import { int, mm2m } from './format.js';

const CW = 10; // largeur d'une cellule (px)
const CH = 4;  // hauteur d'une cellule (px) ; ratio ~ bloc 240×90

const sillMm = (type) => (type === 'fenetre' ? 900 : type === 'vitrine' ? 800 : 0);

export function buildCells(wall, quantities, params) {
  const bl = params.block_length_mm || 240;
  const bh = params.block_height_mm || 90;
  const bearing = params.lintel_bearing_mm ?? 200;
  const cols = Math.max(1, Math.ceil(wall.longueur_mm / bl));
  const rows = Math.max(1, Math.ceil(wall.hauteur_mm / bh));
  const has = (cat) => quantities.some((q) => q.categorie === cat && q.quantite > 0);
  const qty = (cat) => quantities.filter((q) => q.categorie === cat).reduce((s, q) => s + q.quantite, 0);

  // grid[row][col] : 'open' | catégorie ; row 0 = haut du mur
  const grid = Array.from({ length: rows }, () => Array(cols).fill('standard'));
  const setCell = (r, c, v) => { if (r >= 0 && r < rows && c >= 0 && c < cols) grid[r][c] = v; };

  if (has('angle')) for (let r = 0; r < rows; r++) grid[r][0] = 'angle';
  if (has('chainage')) {
    const n = Math.max(1, Math.round(qty('chainage') / rows));
    for (let k = 0; k < n; k++) {
      const c = Math.round(((k + 1) * cols) / (n + 1));
      for (let r = 0; r < rows; r++) if (grid[r][c] === 'standard') grid[r][c] = 'chainage';
    }
  }
  const n = wall.openings.length;
  wall.openings.forEach((o, i) => {
    const wc = Math.max(1, Math.ceil(o.largeur_mm / bl));
    const hr = Math.max(1, Math.ceil(o.hauteur_mm / bh));
    const sill = Math.round(sillMm(o.type) / bh);
    const center = ((i + 1) / (n + 1)) * wall.longueur_mm;
    const c0 = Math.min(Math.max(0, Math.round(center / bl - wc / 2)), cols - wc);
    for (let k = 0; k < hr; k++) for (let c = c0; c < c0 + wc; c++) setCell(rows - 1 - (sill + k), c, 'open');
    if (has('linteau')) {
      const pad = Math.ceil(bearing / bl);
      for (let c = c0 - pad; c < c0 + wc + pad; c++) {
        const r = rows - 1 - (sill + hr);
        if (r >= 0 && c >= 0 && c < cols && grid[r][c] !== 'open') grid[r][c] = 'linteau';
      }
    }
  });
  return { grid, rows, cols };
}

export function wallGrid(wall, layoutWall, params, produitByCode, { bare = false } = {}) {
  const quantities = layoutWall?.quantites || [];
  const { grid, rows, cols } = buildCells(wall, quantities, params);
  const catProduct = {};
  for (const q of quantities) catProduct[q.categorie] = produitByCode[q.code] || '';

  const root = svg('svg', {
    viewBox: `0 0 ${cols * CW} ${rows * CH}`, preserveAspectRatio: 'xMinYMin meet',
    role: 'img', 'aria-label': `Schéma du mur ${wall.nom}`,
  });
  // Mise à l'échelle : proportionnelle à la longueur du mur, plafonnée à la largeur de la carte.
  // (CSSOM : autorisé par la CSP, contrairement à un attribut style.)
  root.style.width = '100%';
  root.style.maxWidth = `${cols * CW * 2.2}px`;
  grid.forEach((row, r) => row.forEach((cell, c) => {
    const cls = cell === 'open' ? 'cell-open'
      : `cat-${cell}${/parpaing/i.test(catProduct[cell] || '') ? ' parp' : ''}`;
    root.append(svg('rect', { x: c * CW, y: r * CH, width: CW - 1, height: CH - 1, class: cls }));
  }));

  const legend = h('ul', { class: 'legend' },
    ...quantities.map((q) => h('li', {},
      h('span', { class: `sw cat-${q.categorie}${/parpaing/i.test(produitByCode[q.code] || '') ? ' parp' : ''}` }),
      h('span', { class: 'mono' }, q.code), h('span', { class: 'mono' }, `× ${int(q.quantite)}`))),
    wall.openings.length ? h('li', {}, h('span', { class: 'sw cell-open-sw' }), 'ouverture (vide)') : null);

  if (bare) return h('div', {}, h('div', { class: 'svgwrap' }, root), legend);
  return h('article', { class: 'wallgrid' },
    h('header', {},
      h('strong', {}, wall.nom),
      h('span', { class: 'muted mono small' },
        `${mm2m(wall.longueur_mm)} × ${mm2m(wall.hauteur_mm)} m${wall.is_corner ? ' · angle' : ''} · ${int(layoutWall?.total || 0)} blocs`)),
    h('div', { class: 'svgwrap' }, root), legend);
}
