# Validation finale de la phase 1

Vérifications réalisées sur un **clone vierge** du dépôt (venv neuf, README suivi à la lettre),
Python 3.11.15, Linux. Les scripts de parcours (API et navigateur Chromium) ont été exécutés ponctuellement et ne
font pas partie du dépôt ; la suite `pytest` (263 tests) en fait partie.

## Résultats

| Vérification | Résultat |
|---|---|
| Installation depuis le README (venv neuf, `pip install -c constraints.txt -e ".[dev]"`) | OK, `pip check` propre |
| Migrations depuis une base vide (0001 → 0003) | OK ; `alembic check` : aucune dérive modèles/migrations ; clés étrangères cohérentes |
| Seed de démonstration | OK : 2 comptes, 6 projets (un par statut) |
| `pytest` complet | **263 passés**, 1 avertissement (dépréciation httpx/Starlette) |
| `pytest` sans réseau (`unshare -rn`, « Network is unreachable ») | 263 passés : aucun test ne dépend d'Internet |
| Parcours API — authentification, permissions opérateur/chef, machine d'états, transitions interdites | 32 contrôles OK |
| Parcours API — workflow complet, moules, lancement concurrent (4 requêtes → 1 ordre), progression, fin, ActionLog | 28 contrôles OK |
| Parcours navigateur (chef, opérateur, mobile 390 px) avec **DNS externe bloqué** | 31 étapes OK ; 0 erreur console, 0 violation CSP, 0 requête externe |
| Persistance après **redémarrage réel** du serveur | 9 contrôles OK (projets, murs, moules, journal, ordres, plans, intégrité SQLite) ; production en cours reprise, non remise à zéro |
| Sauvegarde à chaud puis restauration (`--yes` requis, copie de sécurité créée) | OK : la donnée ajoutée après la sauvegarde disparaît, les données d'origine restent |
| Écoute réseau : défaut local ; `BRIKIA_HOST=0.0.0.0` accessible par l'adresse LAN ; `BRIKIA_ALLOWED_HOSTS` refuse un hôte non autorisé (400) ; pas de CORS | OK |
| Logs : aucun mot de passe, hash, jeton de session ni traceback | OK |

## Definition of Done

| # | Critère | Preuve |
|---|---|---|
| 1-2 | Installation par le README ; dépendances déclarées | clone vierge ; `pyproject.toml` + `constraints.txt` |
| 3-4 | Base via migrations ; seed chargeable | migrations 0001-0003 ; `python -m brikia.cli seed` |
| 5-6 | Démarrage simple ; fonctionnement hors ligne | `python -m brikia.cli serve` ; DNS bloqué, tests sans réseau |
| 7-9 | Connexion chef et opérateur ; permissions côté backend | 10 actions interdites à l'opérateur refusées en 403 par appel direct ; chef refusé au lancement de production |
| 10-17 | Workflow chef : import, analyse, murs, calepinage, proposition, BOM, moules, validation | parcours API et navigateur |
| 18-22 | Workflow opérateur : projets validés, sélection, lancement, suivi, passage à `termine` | parcours API et navigateur |
| 23 | Persistance après redémarrage | redémarrage réel du serveur |
| 24 | Transition interdite rejetée | 9 refus 409 sur le serveur réel + matrice complète des 36 paires en test |
| 25 | Utilisateur sans permission → erreur appropriée | 401 (non connecté), 403 (mauvais rôle), 404 (projet hors périmètre) |
| 26 | Projet non validé ne peut pas entrer en production | opérateur : 404 sur projet non validé ; projet terminé/en production : 409 ; chef : 403 |
| 27 | Lancement répété ne crée pas plusieurs ordres | 4 lancements simultanés → 1 ordre ; index unique en base testé |
| 28-30 | Tests passent, `pytest` sans erreur, sans Internet | 263 passés, réseau coupé |
| 31-35 | README, utilisation, architecture, éléments simulés, phases futures | `README.md`, `docs/` |

## Anomalies trouvées pendant la validation

1. **Projet de démonstration « en production » éphémère** — la simulation avance en temps réel : à la
   cadence par défaut (40 blocs/s) ce projet est terminé ~2 minutes après le `seed`. Ce n'est pas un défaut du
   code mais une limite du jeu de démonstration : documenté dans le README (cadence lente au démarrage du serveur).
2. **Dépendances non figées** — `pip` aurait installé des versions non testées : ajout de `constraints.txt`.
3. Défauts de mes scripts de contrôle (comparaison tuples/listes, PID d'un sous-shell, contrôles trop permissifs),
   corrigés avant de conclure ; aucun n'était un défaut de BrikIA.

## Limites connues

Voir aussi [architecture.md](architecture.md#risques-et-limites-connus).

- Un seul processus serveur ; blocage anti-brute-force en mémoire.
- Deux recalculs de calepinage simultanés peuvent produire une erreur « base verrouillée » (non testé).
- Pas de reprise après une erreur de la ligne simulée (l'ordre reste en `erreur`, le projet `en_production`).
- Lot orphelin possible côté ligne si le commit échoue après l'envoi (sans effet avec le simulateur).
- Progression enregistrée à la consultation, pas par tâche de fond.
- Pas d'administration de comptes ni de changement de mot de passe dans l'interface.
- Contenu des plans non lu ; extension seule contrôlée.
- Non exécutés ici : commandes Windows du README, exemples de pare-feu / reverse proxy / service, essai sur un vrai poste industriel, navigateurs autres que Chromium.
- Règles de calepinage et cadences : **temporaires / de démonstration**.
