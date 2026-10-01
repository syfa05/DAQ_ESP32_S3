const nf0 = new Intl.NumberFormat('fr-FR');
const nf2 = new Intl.NumberFormat('fr-FR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const dtf = new Intl.DateTimeFormat('fr-FR', { dateStyle: 'medium', timeStyle: 'short' });

export const int = (n) => nf0.format(n);
export const dec2 = (n) => nf2.format(n);
export const mm2m = (mm) => nf2.format(mm / 1000);
export const date = (iso) => (iso ? dtf.format(new Date(iso)) : '—');
export const shortHash = (s) => (s ? s.slice(0, 10) : '—');

export function bytes(n) {
  if (n == null) return '—';
  if (n < 1024) return `${n} o`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1).replace('.', ',')} Ko`;
  return `${(n / 1024 / 1024).toFixed(1).replace('.', ',')} Mo`;
}

export function duration(min) {
  if (min == null) return '—';
  const h = Math.floor(min / 60);
  const m = min % 60;
  return h ? `${h} h ${String(m).padStart(2, '0')} min` : `${m} min`;
}
