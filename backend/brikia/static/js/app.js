// Comportements communs à toutes les pages.
import { post } from './lib/api.js';
import { showError } from './lib/ui.js';

document.getElementById('logout')?.addEventListener('click', async () => {
  try {
    await post('/api/auth/logout');
    location.href = '/connexion';
  } catch (e) { showError(e); }
});
