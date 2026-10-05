// Éditeur de mur : corrige l'analyse (dimensions, extrémités, jonctions, ouvertures).
import { del, get, post, put } from './api.js';
import { h } from './dom.js';
import { busy, confirmDialog, showError, toast } from './ui.js';

export const END_LABELS = {
  '': 'Non précisé', libre: 'Bout libre', angle: 'Angle — pose le bloc d\'angle',
  butee: 'Angle — en butée', te: 'Contre un autre mur (T)', suite: 'Prolongement d\'un mur',
};
export const END_SHORT = { libre: 'libre', angle: 'angle', butee: 'butée', te: 'T', suite: 'suite' };
const TYPES = { porte: 'Porte', fenetre: 'Fenêtre', vitrine: 'Vitrine', portail: 'Portail' };

const field = (label, name, value, attrs = {}) => h('div', {}, h('label', { for: `w-${name}` }, label),
  h('input', { id: `w-${name}`, name, value: value ?? '', ...attrs }));
const select = (label, name, options, value) => h('div', {}, h('label', { for: `w-${name}` }, label),
  h('select', { id: `w-${name}`, name }, Object.entries(options).map(([v, l]) =>
    h('option', { value: v, selected: v === (value ?? '') }, l))));
const num = (v) => (v === '' || v == null ? null : Number(v));

export async function openWallEditor({ projectId, wall, status, onDone }) {
  let gammes = [];
  try { gammes = await get('/api/moulds/gammes'); } catch { /* la liste reste vide : choix automatique seul */ }
  const GAMMES = { '': 'Automatique (selon l\'épaisseur)' };
  for (const g of gammes) GAMMES[g.cle] = `${g.produit} ${g.largeur_mm ?? '?'} mm${g.complete ? '' : ' (incomplète)'}`;
  const w = wall || { nom: '', longueur_mm: '', hauteur_mm: 2700, openings: [], junctions_mm: [] };
  const error = h('p', { class: 'form-error', role: 'alert', hidden: true });
  const rows = [];
  const body = h('tbody');
  const addRow = (o = {}) => {
    const r = {
      type: h('select', { 'aria-label': 'Type' }, Object.entries(TYPES).map(([v, l]) => h('option', { value: v, selected: v === (o.type || 'fenetre') }, l))),
      l: h('input', { type: 'number', min: 100, value: o.largeur_mm ?? '', 'aria-label': 'Largeur (mm)' }),
      hh: h('input', { type: 'number', min: 100, value: o.hauteur_mm ?? '', 'aria-label': 'Hauteur (mm)' }),
      x: h('input', { type: 'number', min: 0, value: o.x_mm ?? '', placeholder: 'auto', 'aria-label': 'Position (mm)' }),
      s: h('input', { type: 'number', min: 0, value: o.sill_mm ?? '', placeholder: 'auto', 'aria-label': 'Allège (mm)' }),
    };
    const rm = h('button', { class: 'btn btn-ghost btn-sm', type: 'button', 'aria-label': 'Retirer l\'ouverture' }, '×');
    const tr = h('tr', {}, h('td', {}, r.type), h('td', {}, r.l), h('td', {}, r.hh), h('td', {}, r.x), h('td', {}, r.s), h('td', {}, rm));
    rm.addEventListener('click', () => { rows.splice(rows.indexOf(r), 1); tr.remove(); });
    rows.push(r);
    body.append(tr);
  };
  (w.openings || []).forEach(addRow);

  const form = h('form', { novalidate: true, class: 'wall-editor' },
    h('h2', {}, wall ? `Modifier « ${w.nom} »` : 'Ajouter un mur'),
    status === 'a_valider' ? h('p', { class: 'warn' }, 'Modifier un mur annule le calepinage : le projet repassera à « à optimiser » et il faudra le recalculer.') : null,
    field('Nom', 'nom', w.nom, { required: true, maxlength: 120 }),
    h('div', { class: 'three-cols' },
      field('Longueur (mm)', 'longueur_mm', w.longueur_mm, { type: 'number', min: 300, required: true }),
      field('Hauteur (mm)', 'hauteur_mm', w.hauteur_mm, { type: 'number', min: 500, required: true }),
      field('Épaisseur (mm)', 'thickness_mm', w.thickness_mm, { type: 'number', min: 40, placeholder: 'facultatif' })),
    h('div', { class: 'two-cols' },
      select('Extrémité du début', 'start_kind', END_LABELS, w.start_kind),
      select('Extrémité de fin', 'end_kind', END_LABELS, w.end_kind)),
    select('Gamme de moules', 'gamme', GAMMES, w.gamme),
    h('p', { class: 'note' }, 'Automatique : la gamme dont la largeur est la plus proche de l\'épaisseur du mur (écart toléré 40 mm, sinon avertissement). Imposer une gamme force tous les moules de ce mur.'),
    h('p', { class: 'note' }, 'Un angle n\'a qu\'un propriétaire : choisissez « Angle » sur un seul des deux murs qui se rejoignent, « en butée » sur l\'autre. « Non précisé » : l\'ancien comportement (mur d\'angle = une pile au début).'),
    h('div', { class: 'two-cols' },
      field('Jonctions en T sur ce mur (mm depuis le début, séparées par des virgules)', 'junctions', (w.junctions_mm || []).join(', '), { placeholder: 'ex. 3000, 5200' }),
      h('div', {}, h('label', { for: 'w-is_corner' }, 'Mur d\'angle (si extrémités non précisées)'),
        h('input', { id: 'w-is_corner', name: 'is_corner', type: 'checkbox', checked: !!w.is_corner }))),
    h('h3', {}, 'Ouvertures'),
    h('p', { class: 'note' }, 'Position et allège vides = placées automatiquement (portes au sol, fenêtres à 900 mm).'),
    h('div', { class: 'card table-card' }, h('table', {},
      h('thead', {}, h('tr', {}, ['Type', 'Largeur', 'Hauteur', 'Position', 'Allège', ''].map((t) => h('th', {}, t)))), body)),
    h('button', { class: 'btn btn-ghost btn-sm', type: 'button', onclick: () => addRow() }, '+ Ajouter une ouverture'),
    error,
    h('div', { class: 'actions' },
      wall ? h('button', { class: 'btn btn-danger', type: 'button', id: 'w-del' }, 'Supprimer le mur') : null,
      h('button', { class: 'btn btn-ghost', type: 'button', onclick: () => dlg.close() }, 'Annuler'),
      h('button', { class: 'btn btn-primary', type: 'submit' }, 'Enregistrer')));
  const dlg = h('dialog', { class: 'wall-dialog' }, form);
  dlg.addEventListener('close', () => dlg.remove());

  const payload = () => {
    const el = form.elements;
    rows.forEach((r, i) => {
      if (!num(r.l.value) || !num(r.hh.value)) {
        throw new Error(`Ouverture n°${i + 1} : la largeur et la hauteur sont obligatoires (ou retirez la ligne avec ×).`);
      }
    });
    if (!el.nom.value.trim()) throw new Error('Le nom du mur est obligatoire.');
    if (!num(el.longueur_mm.value) || !num(el.hauteur_mm.value)) throw new Error('La longueur et la hauteur du mur sont obligatoires.');
    const kinds = { start_kind: el.start_kind.value || null, end_kind: el.end_kind.value || null };
    return {
      nom: el.nom.value.trim(), longueur_mm: num(el.longueur_mm.value), hauteur_mm: num(el.hauteur_mm.value),
      thickness_mm: num(el.thickness_mm.value), gamme: el.gamme.value || null, ...kinds,
      is_corner: el.is_corner.checked,
      junctions_mm: el.junctions.value.split(/[;,\s]+/).filter(Boolean).map(Number),
      openings: rows.map((r) => ({ type: r.type.value, largeur_mm: num(r.l.value), hauteur_mm: num(r.hh.value),
        x_mm: num(r.x.value), sill_mm: num(r.s.value) })),
    };
  };

  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    error.hidden = true;
    const btn = form.querySelector('button[type=submit]');
    await busy(btn, async () => {
      try {
        const data = payload();
        if (wall) await put(`/api/projects/${projectId}/murs/${wall.id}`, data);
        else await post(`/api/projects/${projectId}/murs`, data);
        dlg.close();
        toast(wall ? 'Mur modifié. Recalculez le calepinage.' : 'Mur ajouté. Recalculez le calepinage.');
        await onDone();
      } catch (e) { error.textContent = e.message; error.hidden = false; }
    });
  });
  form.querySelector('#w-del')?.addEventListener('click', async () => {
    if (!await confirmDialog({ title: `Supprimer « ${w.nom} » ?`, danger: true, confirmLabel: 'Supprimer',
      body: h('p', {}, 'Le mur est retiré du projet et le calepinage est annulé.') })) return;
    try { await del(`/api/projects/${projectId}/murs/${wall.id}`); dlg.close(); toast('Mur supprimé.'); await onDone(); }
    catch (e) { showError(e); }
  });
  document.body.append(dlg);
  dlg.showModal();
}
