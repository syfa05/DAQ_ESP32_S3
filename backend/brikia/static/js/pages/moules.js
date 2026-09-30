import { del, get, patch, post, put } from '../lib/api.js';
import { h, replace } from '../lib/dom.js';
import { CATEGORY_LABELS, busy, confirmDialog, showError, toast } from '../lib/ui.js';

const isChef = document.body.dataset.role === 'chef_projet';
const box = document.getElementById('molds');
let shapes = [];

const dims = (s) => [s.longueur_mm, s.largeur_mm, s.hauteur_mm].every((v) => v == null) ? '—'
  : [s.longueur_mm, s.largeur_mm, s.hauteur_mm].map((v) => v ?? '?').join(' × ') + ' mm';

async function reload() {
  try { shapes = await get('/api/moulds'); draw(); } catch (e) { showError(e); }
}

function draw() {
  const head = ['Code', 'Nom', 'Produit', 'Catégorie', 'Rôle', 'Dimensions', 'Disponibilité'];
  if (isChef) head.push('Actions');
  replace(box, h('table', {},
    h('thead', {}, h('tr', {}, head.map((t) => h('th', {}, t)))),
    h('tbody', {}, shapes.map(row))));
}

function row(s) {
  const avail = h('span', { class: `badge ${s.disponible ? 'st-valide' : 'st-a_analyser'}` },
    s.disponible ? 'Disponible' : 'Indisponible');
  const tr = h('tr', {},
    h('td', { class: 'mono' }, s.code), h('td', {}, s.nom), h('td', { class: 'muted' }, s.produit),
    h('td', {}, CATEGORY_LABELS[s.categorie] || s.categorie), h('td', { class: 'small' }, s.role || '—'),
    h('td', { class: 'mono small' }, dims(s)), h('td', {}, avail));
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
    tr.append(h('td', { class: 'nowrap' }, h('div', { class: 'actionbar' }, toggle, edit, remove)));
  }
  return tr;
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
    h('p', { class: 'note' }, 'Les dimensions sont facultatives tant qu\'elles ne sont pas confirmées.'),
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
      longueur_mm: num('longueur_mm'), largeur_mm: num('largeur_mm'), hauteur_mm: num('hauteur_mm') };
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
