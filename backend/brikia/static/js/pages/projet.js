import { get, post, ApiError } from '../lib/api.js';
import { h, replace } from '../lib/dom.js';
import * as fmt from '../lib/format.js';
import { orderCard } from '../lib/orderview.js';
import { PIPELINE, STATUS_LABELS, busy, confirmDialog, openingLabel, showError, sourceBadge, statusBadge, toast } from '../lib/ui.js';
import { courseSummary, elevation, legend } from '../lib/elevation.js';
import { wallGrid } from '../lib/wallgrid.js';

const id = Number(document.querySelector('main').dataset.projectId);
const isChef = document.body.dataset.role === 'chef_projet';
const root = document.getElementById('project');
let pollTimer = null;

const notFound = (e) => (e instanceof ApiError && e.status === 404 ? null : Promise.reject(e));

async function load() {
  clearTimeout(pollTimer);
  let project;
  try { project = await get(`/api/projects/${id}`); } catch (e) {
    replace(root, h('div', { class: 'card' }, h('h1', {}, 'Projet introuvable'), h('p', {}, e.message)));
    return;
  }
  const st = project.status;
  const layout = ['a_valider', 'valide', 'en_production', 'termine'].includes(st)
    ? await get(`/api/projects/${id}/calepinage`).catch(notFound) : null;
  const order = ['en_production', 'termine'].includes(st)
    ? await get(`/api/projects/${id}/production`).catch(notFound) : null;
  const quote = isChef && layout ? await get(`/api/projects/${id}/devis`).catch(notFound) : null;
  render(project, layout, order, quote);
}

// Exécute une action métier puis recharge : l'état affiché est toujours celui
// du serveur, y compris quand l'action est refusée (409) car l'état a changé.
async function act(btn, fn, okMessage) {
  await busy(btn, async () => {
    try { await fn(); if (okMessage) toast(okMessage); } catch (e) { showError(e); }
    await load();
  });
}

function actionButton(label, cls, handler) {
  const btn = h('button', { class: `btn ${cls}`, type: 'button' }, label);
  btn.addEventListener('click', () => handler(btn));
  return btn;
}

function analyseHint(name) {
  const ext = (name || '').toLowerCase().split('.').pop();
  if (ext === 'ifc') return 'Le modèle IFC sera lu : murs (découpés en segments droits), ouvertures et niveaux.';
  if (ext === 'step' || ext === 'stp') return 'Le fichier STEP sera lu : les murs sont reconnus par leur forme (heuristique).';
  if (ext === 'dxf') return 'Le plan DXF sera lu : approximation 2D (hauteurs par défaut, un seul niveau).';
  return 'Un PDF n\'est pas lu : l\'analyse sera SIMULÉE (scénario de démonstration). Importez un IFC, STEP ou DXF pour une lecture réelle.';
}

function totalsSummary(layout) {
  const bom = layout.bom;
  return h('p', {}, `${fmt.int(bom.total_blocs)} blocs, durée estimée ${fmt.duration(bom.duree_estimee_min)} (indicative).`);
}

function actions(p, layout) {
  const st = p.status;
  const bar = h('div', { class: 'actionbar' });
  let hint = null;
  if (isChef && st === 'a_analyser') {
    bar.append(actionButton('Lancer l\'analyse', 'btn-primary', (b) => act(b,
      () => post(`/api/projects/${id}/analyse`), 'Analyse terminée : les murs ont été détectés.')));
    hint = analyseHint(p.plan_original_name);
  } else if (isChef && st === 'a_optimiser') {
    bar.append(actionButton('Lancer le calepinage IA', 'btn-primary', (b) => act(b,
      () => post(`/api/projects/${id}/calepinage`), 'Calepinage calculé.')));
    hint = 'Calepinage par moteur de règles déterministe (aucune IA externe).';
  } else if (isChef && st === 'a_valider') {
    bar.append(
      actionButton('Recalculer le calepinage', 'btn-secondary', (b) => act(b,
        () => post(`/api/projects/${id}/calepinage`), 'Calepinage recalculé.')),
      actionButton('Valider le projet', 'btn-moss', async (b) => {
        const ok = await confirmDialog({
          title: 'Valider ce projet ?',
          body: [totalsSummary(layout),
            layout.avertissements.length ? h('p', { class: 'warn' }, `${layout.avertissements.length} avertissement(s) sur le calepinage.`) : null,
            h('p', { class: 'muted' }, 'Une fois validé, le projet est figé et peut être lancé en production par un opérateur.')],
          confirmLabel: 'Valider' });
        if (ok) await act(b, () => post(`/api/projects/${id}/validation`), 'Projet validé.');
      }));
  } else if (!isChef && st === 'valide') {
    bar.append(actionButton('Lancer la production', 'btn-primary', async (b) => {
      const ok = await confirmDialog({
        title: 'Lancer la production ?',
        body: [totalsSummary(layout),
          h('p', { class: 'muted' }, 'Production simulée : aucune machine réelle n\'est pilotée en phase 1.')],
        confirmLabel: 'Lancer la production' });
      if (ok) await act(b, () => post(`/api/projects/${id}/production`), 'Production lancée.');
    }));
  } else if (isChef && st === 'valide') {
    hint = 'Projet validé : en attente du lancement de la production par un opérateur.';
  }
  if (st === 'en_production' || st === 'termine') {
    bar.append(h('a', { class: 'btn btn-secondary', href: '/production' }, 'Suivre la production'));
  }
  bar.append(h('a', { class: 'btn btn-secondary', href: `/api/projects/${id}/rapport.pdf`, target: '_blank', rel: 'noopener' },
    'Rapport PDF'));
  return h('section', { class: 'card', 'aria-label': 'Actions' }, bar, hint ? h('p', { class: 'note' }, hint) : null);
}

function stepper(st) {
  const idx = PIPELINE.indexOf(st);
  return h('ol', { class: 'stepper', 'aria-label': 'Avancement du projet' },
    ...PIPELINE.map((s, i) => h('li', {
      class: i < idx || (s === 'termine' && i === idx) ? (i === idx ? 'done current' : 'done') : i === idx ? 'current' : '',
      'aria-current': i === idx ? 'step' : null }, STATUS_LABELS[s])));
}

function analysisPanel(p) {
  if (!p.analysis_source) return null;
  const warn = p.analysis_source === 'simulated';
  const notes = (p.analysis_notes || []).map((n, i) =>
    h('li', { class: warn && i === 0 ? 'alert' : '' }, n));
  return h('section', { class: `card analysis ${warn ? 'warn' : ''}`, 'aria-labelledby': 'h-analysis' },
    h('div', { class: 'head' }, h('h2', { id: 'h-analysis', class: 'inline' }, 'Analyse du plan'), sourceBadge(p.analysis_source)),
    warn ? h('p', { role: 'alert' }, 'Ces murs ne proviennent PAS de votre plan : ils sont générés par le simulateur de démonstration.') : null,
    notes.length ? h('ul', { class: 'notes' }, notes) : null);
}

function wallsTable(walls) {
  let net = 0;
  const rows = walls.map((w) => {
    net += w.surface_nette_m2;
    return h('tr', {},
      h('td', {}, w.nom), h('td', { class: 'num mono' }, fmt.mm2m(w.longueur_mm)),
      h('td', { class: 'num mono' }, fmt.mm2m(w.hauteur_mm)), h('td', {}, w.is_corner ? 'Oui' : '—'),
      h('td', { class: 'small' }, w.openings.length
        ? w.openings.map((o) => h('div', {}, `${openingLabel(o.type)} ${fmt.mm2m(o.largeur_mm)} × ${fmt.mm2m(o.hauteur_mm)} m`))
        : '—'),
      h('td', { class: 'num mono' }, fmt.dec2(w.surface_brute_m2)),
      h('td', { class: 'num mono' }, fmt.dec2(w.surface_ouvertures_m2)),
      h('td', { class: 'num mono' }, fmt.dec2(w.surface_nette_m2)));
  });
  return h('section', { 'aria-labelledby': 'h-walls' }, h('h2', { id: 'h-walls' }, 'Murs analysés'),
    h('div', { class: `card table-card ${walls.length > 25 ? 'scroll' : ''}` }, h('table', {},
      h('thead', {}, h('tr', {}, ...['Mur', 'Long. (m)', 'Haut. (m)', 'Angle', 'Ouvertures', 'Brute (m²)', 'Ouv. (m²)', 'Nette (m²)']
        .map((t, i) => h('th', { class: i === 1 || i === 2 || i >= 5 ? 'num' : '' }, t)))),
      h('tbody', {}, rows),
      h('tfoot', {}, h('tr', {}, h('td', { colspan: 7 }, 'Surface nette totale'),
        h('td', { class: 'num mono' }, fmt.dec2(net)))))));
}

function bomTable(layout) {
  const bom = layout.bom;
  return h('div', { class: 'card table-card' }, h('table', {},
    h('thead', {}, h('tr', {}, h('th', {}, 'Code'), h('th', {}, 'Forme'), h('th', {}, 'Produit'),
      h('th', { class: 'num' }, 'Quantité'), h('th', {}, 'Par mur'))),
    h('tbody', {}, bom.lignes.map((l) => h('tr', {},
      h('td', { class: 'mono' }, l.code), h('td', {}, l.nom), h('td', { class: 'muted' }, l.produit),
      h('td', { class: 'num mono' }, fmt.int(l.quantite_totale)),
      h('td', {}, h('details', {}, h('summary', {}, `${l.par_mur.length} mur(s)`),
        ...l.par_mur.map((m) => h('div', { class: 'small mono' }, `${m.wall_nom} : ${fmt.int(m.quantite)}`))))))),
    h('tfoot', {}, h('tr', {}, h('td', { colspan: 3 }, 'Total projet'),
      h('td', { class: 'num mono' }, fmt.int(bom.total_blocs)), h('td', {}, '')))));
}

const eur = (v) => `${Number(v).toLocaleString('fr-FR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} €`;
const fcfa = (v) => `${Number(v).toLocaleString('fr-FR', { maximumFractionDigits: 0 })} FCFA`;

function quoteSection(q) {
  const p = q.parametres;
  const rows = q.lignes.map((l) => h('tr', {}, h('td', { class: 'mono' }, l.code),
    h('td', { class: 'num mono' }, fmt.int(l.quantite)),
    h('td', { class: 'num mono' }, l.chiffre ? eur(l.prix_unitaire_eur) : 'n/c'),
    h('td', { class: 'num mono' }, l.chiffre ? eur(l.total_eur) : 'n/c'),
    h('td', { class: 'num mono' }, l.chiffre ? fcfa(l.prix_unitaire_fcfa) : 'n/c'),
    h('td', { class: 'num mono' }, l.chiffre ? fcfa(l.total_fcfa) : 'n/c')));
  const tot = (label, key, cls = '') => h('tr', { class: cls }, h('td', { colspan: 3 }, label),
    h('td', { class: 'num mono' }, eur(q.eur[key])), h('td', {}, ''), h('td', { class: 'num mono' }, fcfa(q.fcfa[key])));
  return h('section', { 'aria-labelledby': 'h-quote' },
    h('h2', { id: 'h-quote' }, 'Chiffrage estimatif ',
      h('span', { class: `badge ${q.fige ? 'frozen' : 'live'}` }, q.fige ? 'Figé à la validation' : 'Indicatif (tarif du jour)')),
    h('p', { class: 'note' }, `Marge ${p.marge_pct} % · TVA ${p.tva_pct} % · 1 EUR = ${p.taux_fcfa_par_eur} FCFA. Valeurs estimatives : modifiables dans la page Tarifs.`),
    q.avertissements.length ? h('div', { class: 'warn', role: 'alert' }, h('ul', {}, q.avertissements.map((a) => h('li', {}, a)))) : null,
    h('div', { class: 'card table-card' }, h('table', {},
      h('thead', {}, h('tr', {}, ['Moule', 'Qté', 'PU EUR', 'Total EUR', 'PU FCFA', 'Total FCFA'].map((t) => h('th', {}, t)))),
      h('tbody', {}, rows),
      h('tfoot', {}, tot('Matériel HT', 'materiel_ht'), tot('Frais fixes', 'frais_fixes'), tot('Total HT', 'total_ht'),
        tot('TVA', 'tva'), tot('Total TTC', 'total_ttc', 'quote-total')))));
}

function wallElevation(body) {
  const d = body.detail;
  const rows = courseSummary(body);
  const openings = d.ouvertures.length ? h('ul', { class: 'small' }, d.ouvertures.map((o) => h('li', {},
    `${o.type} ${o.largeur} × ${o.hauteur} mm à ${o.x} mm du début, allège ${o.allege} mm — assises ${o.c0 + 1} à ${o.c1}`
    + (o.position_estimee ? ' (position estimée : plan non lu en détail)' : '')))) : null;
  return h('div', {},
    elevation(body), legend(body),
    h('p', { class: 'small muted' }, `${d.assises} assises de ${d.hauteur_assise_mm} mm · ${d.coupes} pièce(s) coupée(s) · chutes ${fmt.int(d.chutes_mm)} mm`
      + ' · quantités à produire = pose + marge de casse.'),
    d.notes.length ? h('div', { class: 'warn' }, h('ul', {}, d.notes.map((n) => h('li', {}, n)))) : null,
    openings,
    h('details', {}, h('summary', {}, 'Détail des assises (de haut en bas)'),
      h('div', { class: 'card table-card' }, h('table', { class: 'course-table' },
        h('thead', {}, h('tr', {}, ['Assise', 'Cote basse', 'Blocs posés', 'Coupes'].map((t) => h('th', {}, t)))),
        h('tbody', {}, rows.map((r) => h('tr', {}, h('td', { class: 'num mono' }, String(r.n)),
          h('td', { class: 'mono' }, `${fmt.int(r.from)} mm`), h('td', { class: 'mono small' }, r.text),
          h('td', { class: 'small' }, r.cuts.join(' ; ') || '—'))))))));
}

function layoutSection(project, layout) {
  const bom = layout.bom;
  const produitByCode = Object.fromEntries(bom.lignes.map((l) => [l.code, l.produit]));
  const wallsById = Object.fromEntries(project.walls.map((w) => [w.id, w]));
  return h('section', { 'aria-labelledby': 'h-layout' },
    h('h2', { id: 'h-layout' }, layout.detail_disponible ? 'Calepinage assise par assise' : 'Calepinage — estimation'),
    h('p', { class: 'temp' }, 'Calcul à partir des dimensions des moules de la bibliothèque et de règles temporaires (marges, parts de demi-blocs et de chaînage) à valider avec le fournisseur. Durée = estimation indicative sur les cadences des moules.'),
    layout.avertissements.length ? h('div', { class: 'warn', role: 'alert' }, h('strong', {}, 'Avertissements'),
      h('ul', {}, layout.avertissements.map((a) => h('li', {}, a)))) : null,
    h('h3', {}, 'Nomenclature'),
    bomTable(layout),
    h('p', { class: 'note' }, `Durée de production estimée : ${fmt.duration(bom.duree_estimee_min)} (indicatif, d'après les cadences des moules).`),
    h('h3', {}, layout.detail_disponible ? 'Pose assise par assise' : 'Schéma des murs'),
    h('p', { class: 'note' }, layout.detail_disponible
      ? 'Chaque bloc est posé rang par rang (joints décalés, ouvertures, linteaux, appuis, chaînages, angles). Ouvrez un mur pour voir son élévation à l\'échelle. Les quantités à produire = pose + marge de casse ; une coupe consomme un bloc entier.'
      : 'Représentation schématique : elle aide à comprendre le calepinage mais n\'est pas un rendu physique exact ni une simulation structurelle. Les quantités font foi.'),
    wallGridsSection(project, layout, produitByCode, wallsById));
}

// Les schémas (plusieurs milliers de rectangles SVG par mur) ne sont construits qu'à l'ouverture
// du mur : un bâtiment de 300 murs reste fluide. Petit projet (<= 8 murs) : tout est ouvert.
function wallGridsSection(project, layout, produitByCode, wallsById) {
  const eager = layout.murs.length <= 8;
  const items = layout.murs.filter((m) => wallsById[m.wall_id]).map((m) => {
    const wall = wallsById[m.wall_id];
    const body = h('div');
    const exact = layout.detail_disponible;
    const det = h('details', { class: 'wallgrid', 'data-name': m.wall_nom.toLowerCase() },
      h('summary', {}, h('strong', {}, m.wall_nom),
        h('span', { class: 'muted mono small' }, `${fmt.mm2m(wall.longueur_mm)} × ${fmt.mm2m(wall.hauteur_mm)} m${wall.is_corner ? ' · angle' : ''} · ${fmt.int(m.total)} blocs`)),
      body);
    const build = async () => {
      if (body.firstChild) return;
      if (!exact) { body.append(wallGrid(wall, m, layout.parametres, produitByCode, { bare: true })); return; }
      body.append(h('p', { class: 'muted pad' }, 'Chargement…'));
      try { body.replaceChildren(wallElevation(await get(`/api/projects/${id}/calepinage/murs/${m.wall_id}`))); }
      catch (e) { body.replaceChildren(h('p', { class: 'form-error' }, e.message)); }
    };
    det.addEventListener('toggle', () => { if (det.open) build(); });
    if (eager) { det.open = true; build(); }
    return det;
  });
  const holder = h('div', { class: 'wallgrids' }, items);
  const filter = h('input', { type: 'search', placeholder: 'Filtrer les murs (nom, niveau)…', 'aria-label': 'Filtrer les murs' });
  filter.addEventListener('input', () => {
    const q = filter.value.trim().toLowerCase();
    for (const d of items) d.hidden = q !== '' && !d.dataset.name.includes(q);
  });
  return h('div', {},
    items.length > 8 ? h('div', { class: 'toolbar' }, filter, h('span', { class: 'muted small' }, `${items.length} murs — ouvrez un mur pour voir son schéma.`)) : null,
    holder);
}

function render(project, layout, order, quote) {
  const st = project.status;
  const planLine = project.plan_original_name
    ? `${project.plan_original_name} (${fmt.bytes(project.plan_size)}) · SHA-256 ${fmt.shortHash(project.plan_sha256)}…` : '—';
  let orderView = null;
  const nodes = [
    h('div', { class: 'proj-head' },
      h('div', {}, h('h1', {}, project.nom),
        h('div', { class: 'meta' },
          h('span', {}, `Ville : ${project.ville || '—'}`), h('span', {}, `Architecte : ${project.architecte || '—'}`),
          h('span', { class: 'mono' }, `Créé le ${fmt.date(project.created_at)}`),
          project.validated_at ? h('span', { class: 'mono' }, `Validé le ${fmt.date(project.validated_at)}`) : null,
          project.completed_at ? h('span', { class: 'mono' }, `Terminé le ${fmt.date(project.completed_at)}`) : null),
        h('div', { class: 'meta' }, h('span', { class: 'mono' }, `Plan : ${planLine}`))),
      statusBadge(st)),
    stepper(st),
    actions(project, layout),
    analysisPanel(project),
  ];
  if (order) {
    orderView = orderCard(order);
    nodes.push(h('section', { 'aria-labelledby': 'h-prod' }, h('h2', { id: 'h-prod' }, 'Production'),
      h('p', { class: 'sim-banner' }, 'Production simulée — aucune machine réelle connectée.'), orderView.node));
  }
  if (project.walls.length) nodes.push(wallsTable(project.walls));
  if (layout) nodes.push(layoutSection(project, layout));
  if (quote) nodes.push(quoteSection(quote));
  replace(root, ...nodes);
  document.title = `${project.nom} — BrikIA`;

  if (orderView && order.status === 'en_cours') {
    const poll = async () => {
      try {
        const o = await get(`/api/production/${order.id}`);
        orderView.update(o);
        if (o.status === 'en_cours') pollTimer = setTimeout(poll, 2000);
        else { toast(o.status === 'termine' ? 'Production terminée.' : 'La ligne a signalé une erreur.', o.status === 'termine' ? 'ok' : 'error'); load(); }
      } catch (e) { showError(e); pollTimer = setTimeout(poll, 5000); }
    };
    pollTimer = setTimeout(poll, 1500);
  }
}

load();
