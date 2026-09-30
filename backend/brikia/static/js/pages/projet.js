import { get, post, ApiError } from '../lib/api.js';
import { h, replace } from '../lib/dom.js';
import * as fmt from '../lib/format.js';
import { orderCard } from '../lib/orderview.js';
import { PIPELINE, STATUS_LABELS, busy, confirmDialog, openingLabel, showError, statusBadge, toast } from '../lib/ui.js';
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
  render(project, layout, order);
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
    hint = 'En phase 1, le contenu du plan n\'est pas lu : l\'analyse produit un scénario de démonstration déterministe.';
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
  return h('section', { class: 'card', 'aria-label': 'Actions' }, bar, hint ? h('p', { class: 'note' }, hint) : null);
}

function stepper(st) {
  const idx = PIPELINE.indexOf(st);
  return h('ol', { class: 'stepper', 'aria-label': 'Avancement du projet' },
    ...PIPELINE.map((s, i) => h('li', {
      class: i < idx || (s === 'termine' && i === idx) ? (i === idx ? 'done current' : 'done') : i === idx ? 'current' : '',
      'aria-current': i === idx ? 'step' : null }, STATUS_LABELS[s])));
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
    h('div', { class: 'card table-card' }, h('table', {},
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

function layoutSection(project, layout) {
  const bom = layout.bom;
  const produitByCode = Object.fromEntries(bom.lignes.map((l) => [l.code, l.produit]));
  const wallsById = Object.fromEntries(project.walls.map((w) => [w.id, w]));
  return h('section', { 'aria-labelledby': 'h-layout' },
    h('h2', { id: 'h-layout' }, 'Calepinage IA — proposition'),
    h('p', { class: 'temp' }, 'Règles de calcul temporaires (brique jointée du prototype) : le système autobloquant mâle-femelle définitif sera validé avec le fournisseur des moules. Durée = estimation indicative sur cadences de démonstration.'),
    layout.avertissements.length ? h('div', { class: 'warn', role: 'alert' }, h('strong', {}, 'Avertissements'),
      h('ul', {}, layout.avertissements.map((a) => h('li', {}, a)))) : null,
    h('h3', {}, 'Nomenclature'),
    bomTable(layout),
    h('p', { class: 'note' }, `Durée de production estimée : ${fmt.duration(bom.duree_estimee_min)} (indicatif, valeurs de démonstration).`),
    h('h3', {}, 'Schéma des murs'),
    h('p', { class: 'note' }, 'Représentation schématique : elle aide à comprendre le calepinage mais n\'est pas un rendu physique exact ni une simulation structurelle. Les quantités font foi.'),
    h('div', { class: 'wallgrids' }, layout.murs.map((m) =>
      wallsById[m.wall_id] ? wallGrid(wallsById[m.wall_id], m, layout.parametres, produitByCode) : null)));
}

function render(project, layout, order) {
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
  ];
  if (order) {
    orderView = orderCard(order);
    nodes.push(h('section', { 'aria-labelledby': 'h-prod' }, h('h2', { id: 'h-prod' }, 'Production'),
      h('p', { class: 'sim-banner' }, 'Production simulée — aucune machine réelle connectée.'), orderView.node));
  }
  if (project.walls.length) nodes.push(wallsTable(project.walls));
  if (layout) nodes.push(layoutSection(project, layout));
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
