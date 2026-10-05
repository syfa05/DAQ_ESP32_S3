import { del, get, patch, post, put } from '../lib/api.js';
import { h, replace } from '../lib/dom.js';
import { AUTO_CATEGORIES, CATEGORY_LABELS, busy, confirmDialog, showError, toast } from '../lib/ui.js';

const isChef = document.body.dataset.role === 'chef_projet';
const box = document.getElementById('molds');
let shapes = [];
let gammes = [];
let filter = '';
const keyOf = (s) => `${s.produit}|${s.largeur_mm ?? ''}`;

const dims = (s) => [s.longueur_mm, s.largeur_mm, s.hauteur_mm].every((v) => v == null) ? '—'
  : [s.longueur_mm, s.largeur_mm, s.hauteur_mm].map((v) => v ?? '?').join(' × ') + ' mm';

const money = (v) => (v == null ? '—' : `${Number(v).toLocaleString('fr-FR', { minimumFractionDigits: 2, maximumFractionDigits: 4 })} €`);
const weight = (g) => (g == null ? '—' : `${(g / 1000).toLocaleString('fr-FR', { maximumFractionDigits: 2 })} kg`);

async function reload() {
  try { [shapes, gammes] = await Promise.all([get('/api/moulds'), get('/api/moulds/gammes')]); drawChips(); draw(); }
  catch (e) { showError(e); }
}

function drawChips() {
  const box = document.getElementById('gammes');
  const chip = (key, label, title, cls = '') => {
    const b = h('button', { type: 'button', class: `chip ${cls}${filter === key ? ' on' : ''}`, title }, label);
    b.addEventListener('click', () => { filter = key; drawChips(); draw(); });
    return b;
  };
  replace(box, chip('', `Toutes (${shapes.length})`, 'Afficher tous les moules'),
    ...gammes.map((g) => chip(g.cle, `${g.produit.split(' ')[0]} ${g.largeur_mm ?? '?'} mm · ${g.nb_disponibles}`,
      g.complete ? 'Gamme complète' : `Fonctions absentes : ${g.manque.join(', ')}`, g.complete ? '' : 'warn')));
}

function draw() {
  const head = ['Code', 'Moule', 'Catégorie', 'Dimensions', 'Poids', 'Cadence'];
  if (isChef) head.push('Coût estimé');
  head.push('Disponibilité', isChef ? 'Actions' : 'Plan');
  replace(box, h('table', {},
    h('thead', {}, h('tr', {}, head.map((t) => h('th', {}, t)))),
    h('tbody', {}, shapes.filter((s) => !filter || keyOf(s) === filter).map(row))));
}

function row(s) {
  const avail = h('span', { class: `badge ${s.disponible ? 'st-valide' : 'st-a_analyser'}` },
    s.disponible ? 'Disponible' : 'Indisponible');
  const tr = h('tr', {},
    h('td', { class: 'mono' }, s.code), h('td', {}, s.nom, h('div', { class: 'muted small' }, s.produit)),
    h('td', { title: s.role || '' }, CATEGORY_LABELS[s.categorie] || s.categorie,
      h('div', { class: 'muted small' }, AUTO_CATEGORIES.has(s.categorie) ? 'calcul auto' : 'saisie manuelle')),
    h('td', { class: 'mono small' }, dims(s)), h('td', { class: 'mono small' }, weight(s.poids_g)),
    h('td', { class: 'mono small' }, s.cadence_par_heure ? `${s.cadence_par_heure} /h` : '—'),
    isChef ? h('td', { class: 'mono small num' }, money(s.cout_unitaire_eur)) : null,
    h('td', {}, avail));
  const plan = h('button', { class: 'btn btn-ghost btn-sm', type: 'button', onclick: () => openPlan(s) }, 'Plan 2D/3D');
  if (!isChef) tr.append(h('td', {}, plan));
  if (isChef) {
    const toggle = h('button', { class: 'btn btn-secondary btn-sm', type: 'button' }, s.disponible ? 'Désactiver' : 'Activer');
    toggle.addEventListener('click', () => busy(toggle, async () => {
      try { await patch(`/api/moulds/${s.id}/disponibilite`, { disponible: !s.disponible });
        toast(`Moule ${s.code} ${s.disponible ? 'désactivé' : 'activé'}.`); } catch (e) { showError(e); }
      await reload();
    }));
    const edit = h('button', { class: 'btn btn-ghost btn-sm', type: 'button', onclick: () => openForm(s) }, 'Modifier');
    const remove = h('button', { class: 'btn btn-danger btn-sm', type: 'button' }, 'Supprimer');
    remove.addEventListener('click', async () => {
      if (!await confirmDialog({ title: `Supprimer ${s.code} ?`, danger: true, confirmLabel: 'Supprimer',
        body: h('p', {}, `Le moule « ${s.nom} » sera définitivement supprimé. S'il est déjà utilisé, désactivez-le plutôt.`) })) return;
      await busy(remove, async () => {
        try { await del(`/api/moulds/${s.id}`); toast(`Moule ${s.code} supprimé.`); } catch (e) { showError(e); }
        await reload();
      });
    });
    tr.append(h('td', { class: 'nowrap' }, h('div', { class: 'actionbar' }, plan, toggle, edit, remove)));
  }
  return tr;
}

function openPlan(s) {
  const url = `/api/moulds/${s.id}/plan.svg`;
  const img = h('img', { src: url, alt: `Plan du moule ${s.code}` });
  const note = h('p', { class: 'form-error', hidden: true });
  img.addEventListener('error', async () => {
    img.hidden = true;
    try { await get(url); } catch (e) { note.textContent = e.message; }
    note.hidden = false;
  });
  const dlg = h('dialog', { class: 'mold-plan', 'aria-label': `Plan ${s.code}` }, img, note,
    h('div', { class: 'actions' },
      h('a', { class: 'btn btn-secondary', href: url, target: '_blank', rel: 'noopener' }, 'Ouvrir / imprimer'),
      h('button', { class: 'btn btn-primary', type: 'button', onclick: () => dlg.close() }, 'Fermer')));
  dlg.addEventListener('close', () => dlg.remove());
  document.body.append(dlg);
  dlg.showModal();
}

function field(label, name, value, attrs = {}) {
  return h('div', {}, h('label', { for: `f-${name}` }, label),
    h('input', { id: `f-${name}`, name, value: value ?? '', ...attrs }));
}

function openForm(existing) {
  const s = existing || {};
  const error = h('p', { class: 'form-error', role: 'alert', hidden: true });
  const cat = h('select', { id: 'f-categorie', name: 'categorie' },
    Object.entries(CATEGORY_LABELS).map(([v, l]) => h('option', { value: v, selected: v === (s.categorie || 'standard') }, l)));
  const form = h('form', { novalidate: true },
    h('h2', {}, existing ? `Modifier ${s.code}` : 'Nouveau moule'),
    existing ? null : field('Code (lettres, chiffres, _ . -)', 'code', '', { required: true, maxlength: 40 }),
    field('Nom', 'nom', s.nom, { required: true, maxlength: 120 }),
    field('Produit', 'produit', s.produit, { required: true, maxlength: 120 }),
    h('label', { for: 'f-categorie' }, 'Catégorie fonctionnelle'), cat,
    field('Rôle', 'role', s.role, { maxlength: 255 }),
    h('div', { class: 'three-cols' },
      field('Longueur (mm)', 'longueur_mm', s.longueur_mm, { type: 'number', min: 1 }),
      field('Largeur (mm)', 'largeur_mm', s.largeur_mm, { type: 'number', min: 1 }),
      field('Hauteur (mm)', 'hauteur_mm', s.hauteur_mm, { type: 'number', min: 1 })),
    h('div', { class: 'three-cols' },
      field('Poids (g)', 'poids_g', s.poids_g, { type: 'number', min: 1 }),
      field('Cadence (blocs/h)', 'cadence_par_heure', s.cadence_par_heure, { type: 'number', min: 1 }),
      isChef ? field('Coût de revient (€/bloc)', 'cout_unitaire_eur', s.cout_unitaire_eur, { type: 'number', min: 0, step: '0.01' }) : null),
    h('p', { class: 'note' }, 'Dimensions, poids, cadence et coût sont des valeurs estimatives, modifiables à tout moment. Les dimensions pilotent le calepinage et les plans.'),
    error,
    h('div', { class: 'actions' },
      h('button', { class: 'btn btn-ghost', type: 'button', onclick: () => dlg.close() }, 'Annuler'),
      h('button', { class: 'btn btn-primary', type: 'submit' }, existing ? 'Enregistrer' : 'Créer')));
  const dlg = h('dialog', {}, form);
  dlg.addEventListener('close', () => dlg.remove());
  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    error.hidden = true;
    const val = (n) => form.elements[n]?.value.trim();
    const num = (n) => (val(n) ? Number(val(n)) : null);
    const body = { nom: val('nom'), produit: val('produit'), role: val('role') || '', categorie: cat.value,
      longueur_mm: num('longueur_mm'), largeur_mm: num('largeur_mm'), hauteur_mm: num('hauteur_mm'),
      poids_g: num('poids_g'), cadence_par_heure: num('cadence_par_heure'), cout_unitaire_eur: val('cout_unitaire_eur') || null };
    const btn = form.querySelector('button[type=submit]');
    await busy(btn, async () => {
      try {
        if (existing) await put(`/api/moulds/${s.id}`, body);
        else await post('/api/moulds', { ...body, code: val('code') });
        dlg.close();
        toast(existing ? 'Moule modifié.' : 'Moule créé.');
        await reload();
      } catch (e) { error.textContent = e.message; error.hidden = false; }
    });
  });
  document.body.append(dlg);
  dlg.showModal();
}

document.getElementById('new-mold')?.addEventListener('click', () => openForm(null));
reload();
