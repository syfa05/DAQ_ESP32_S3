import { h } from './dom.js';

export const STATUS_LABELS = {
  a_analyser: 'À analyser', a_optimiser: 'À optimiser', a_valider: 'À valider',
  valide: 'Validé', en_production: 'En production', termine: 'Terminé',
  en_cours: 'En cours', erreur: 'Erreur',
};
export const PIPELINE = ['a_analyser', 'a_optimiser', 'a_valider', 'valide', 'en_production', 'termine'];
export const OPENING_LABELS = { fenetre: 'fenêtre', porte: 'porte', vitrine: 'vitrine', portail: 'portail' };
export const openingLabel = (t) => OPENING_LABELS[t] || t;
export const SOURCE_LABELS = {
  ifc: 'Lecture réelle — IFC', step: 'Lecture réelle — STEP (heuristique)',
  dxf: 'Lecture réelle — DXF (approximation 2D)', simulated: 'Analyse SIMULÉE',
};
export const SOURCE_SHORT = { ifc: 'IFC', step: 'STEP', dxf: 'DXF', simulated: 'simulé' };
export const sourceBadge = (src) => h('span', { class: `badge src-${src}` }, SOURCE_LABELS[src] || src);
export const CATEGORY_LABELS = { standard: 'Standard', angle: 'Angle', chainage: 'Chaînage', linteau: 'Linteau' };

export const statusBadge = (status) =>
  h('span', { class: `badge st-${status}` }, STATUS_LABELS[status] || status);

export function toast(message, kind = 'ok') {
  const box = document.getElementById('toasts');
  if (!box) return;
  const t = h('div', { class: `toast ${kind === 'ok' ? '' : kind}`.trim() }, message);
  box.append(t);
  setTimeout(() => t.remove(), kind === 'error' ? 8000 : 4500);
}

export const showError = (err) => toast(err?.message || 'Une erreur est survenue.', 'error');

// Dialogue modal natif <dialog> ; résout true (confirmé) ou false (annulé).
export function confirmDialog({ title, body, confirmLabel = 'Confirmer', danger = false }) {
  return new Promise((resolve) => {
    let result = false;
    const dlg = h('dialog', { 'aria-labelledby': 'dlg-title' },
      h('h2', { id: 'dlg-title' }, title),
      h('div', {}, body),
      h('div', { class: 'actions' },
        h('button', { class: 'btn btn-ghost', type: 'button', onclick: () => dlg.close() }, 'Annuler'),
        h('button', { class: `btn ${danger ? 'btn-danger' : 'btn-primary'}`, type: 'button',
          onclick: () => { result = true; dlg.close(); } }, confirmLabel)));
    dlg.addEventListener('close', () => { dlg.remove(); resolve(result); });
    document.body.append(dlg);
    dlg.showModal();
  });
}

// Désactive le bouton pendant l'appel : protège du double clic.
export async function busy(button, fn) {
  if (button.disabled) return undefined;
  button.disabled = true;
  try { return await fn(); } finally { button.disabled = false; }
}
