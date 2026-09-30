# Architecture — BrikIA phase 1

Monolithe modulaire volontairement simple : un seul processus Python, une base SQLite, pas de
Redis / Celery / microservices. Le domaine ne dépend ni de FastAPI ni de SQLAlchemy ; les
technologies futures (STEP/IFC, Raspberry Pi, Modbus/OPC-UA) se branchent derrière des
interfaces sans toucher au pipeline.

## Couches

```
api/ + web/        HTTP : endpoints JSON, pages Jinja2 (coquilles), erreurs en français
   │
services/          cas d'usage transactionnels : auth, projects, analysis, layout,
   │               validation, production, molds, audit, storage
   ├── domain/     Python pur : machine d'états, erreurs métier, géométrie, BOM, types de calepinage
   ├── adapters/   implémentations interchangeables (voir « Interfaces »)
   └── models/     SQLAlchemy (SQLite aujourd'hui, PostgreSQL possible)
```

Règles de conception :

- **Le backend porte toute la logique.** Le frontend n'est jamais responsable d'une transition
  métier ni d'une permission.
- **Les services valident (`commit`) explicitement** ; `get_db` ferme la session et annule ce qui
  n'a pas été validé. Les opérations critiques sont transactionnelles avec rollback.
- **Point unique de choix des adaptateurs** : `main.py` (`app.state.plan_analyzer`,
  `layout_engine`, `production_gateway`), injectés par `deps.py`.

## Machine d'états

Source unique : `domain/states.py`. Seul `services.projects.transition` écrit `project.status`.

```
a_analyser → a_optimiser → a_valider → valide → en_production → termine
```

| Transition | Déclencheur | Rôle |
|---|---|---|
| a_analyser → a_optimiser | `POST /projects/{id}/analyse` | chef de projet |
| a_optimiser → a_valider | `POST /projects/{id}/calepinage` | chef de projet |
| a_valider → valide | `POST /projects/{id}/validation` | chef de projet |
| valide → en_production | `POST /projects/{id}/production` | opérateur |
| en_production → termine | fin de l'ordre (simulateur), détectée à la consultation | système |

Toute autre transition est refusée (409). La transition est un `UPDATE … WHERE status = <statut lu>` :
deux requêtes concurrentes ne peuvent pas appliquer la même transition. Le calepinage peut être
**recalculé** depuis `a_valider` (sans changement de statut) pour tenir compte d'un moule désactivé.
Après validation, le projet est figé.

## Modèle de données

| Table | Contenu |
|---|---|
| `users` | nom, login unique, hash argon2, rôle, actif |
| `user_sessions` | hash du jeton (jamais le jeton), jeton CSRF, expiration |
| `projects` | nom, ville, architecte, métadonnées du plan (chemin, nom, taille, SHA-256), statut, dates |
| `walls` / `openings` | murs (mm entiers, `is_corner`) et ouvertures (table dédiée, FK, cascade) |
| `brick_shapes` | bibliothèque de moules (code unique, produit, **catégorie** standard/angle/chainage/linteau, dimensions optionnelles, disponible) |
| `layout_runs` | un calcul de calepinage : moteur, règles utilisées (JSON d'audit), avertissements, durée estimée |
| `wall_assignments` | quantité d'une forme pour un mur d'un calepinage (contrainte d'unicité) |
| `production_orders` | `lot_id` (identifiant transmis à la ligne), statut, dates, message d'alarme |
| `production_order_lines` | cible / produit par forme, `CHECK (0 <= produit <= cible)` |
| `action_logs` | traçabilité : utilisateur (NULL = système), action, cible, détails JSON, horodatage |

Choix justifiés :

- **Dimensions en millimètres entiers** : pas d'erreur d'arrondi flottant, calculs déterministes.
- **Quantités de production en table relationnelle** (et non en JSON) : contraintes d'intégrité
  (produit ≤ cible), requêtes de suivi simples, clés étrangères vers les moules.
- **Énumérations en texte + CHECK** : portables SQLite / PostgreSQL.
- **Un seul ordre actif par projet** : index unique partiel
  `production_orders(project_id) WHERE status = 'en_cours'` — garde-fou en base contre le double
  lancement (double clic, rejeu HTTP, requêtes concurrentes).
- **Moules référencés = non supprimables** (FK RESTRICT + message) : on les désactive.

## Interfaces remplaçables

| Interface | Phase 1 | Contrat |
|---|---|---|
| `PlanAnalyzer` | `SimulatedPlanAnalyzer` | `analyse(PlanFile) -> ProjectGeometry` |
| `LayoutEngine` | `DefaultRuleBasedLayoutEngine` | `calculate(walls, brick_shapes) -> LayoutResult` |
| `ProductionGateway` | `SimulatedProductionGateway` | `send_order(OrderPayload)` / `get_status(lot_id)` |

- Le résultat d'un moteur est **revalidé** avant écriture (murs couverts, quantités ≥ 0, moules
  connus) : un moteur défaillant ne peut pas corrompre la base.
- `ProductionGateway` reprend le contrat futur BrikIA → Raspberry Pi (`lot_id`,
  `quantites_par_forme`, état/progression) et l'envoi est **idempotent par `lot_id`**.
  Il ne transporte aucune commande de sécurité.

## Sécurité applicative

- **Authentification** : session serveur ; cookie `HttpOnly`, `SameSite=Strict`, `Secure` si HTTPS ;
  jeton de session stocké haché ; expiration ; mots de passe argon2 ; 5 échecs / 60 s par identifiant
  → blocage temporaire (compteur en mémoire du processus).
- **CSRF** : en-tête `X-CSRF-Token` obligatoire sur POST/PUT/PATCH/DELETE authentifiés.
- **Autorisations** : `require_role(...)` sur **chaque** endpoint protégé ; les pages HTML ne sont
  que des coquilles (l'autorisation réelle est celle de l'API). Un projet hors périmètre d'un
  opérateur répond 404 (pas de fuite d'existence).
- **Fichiers importés** : extensions autorisées, taille plafonnée (50 Mo), écriture atomique,
  SHA-256, nom client jamais utilisé comme chemin.
- **En-têtes** : CSP stricte (`default-src 'self'`, ni script ni style inline), `X-Frame-Options: DENY`,
  `nosniff`, pas de CORS (même origine), contrôle de l'en-tête Host configurable.
- **Erreurs** : réponses JSON françaises, jamais de traceback ni de SQL ; détails dans les logs techniques.
- **Logs** : `data/logs/brikia.log` (techniques, rotation) distincts de l'`ActionLog` métier ; ni mot
  de passe ni jeton n'y figurent (vérifié par test).

## Endpoints et permissions

CP = chef de projet, OP = opérateur, Auth = tout utilisateur connecté.
« Filtré » : un opérateur ne voit que les projets `valide`, `en_production`, `termine` (404 sinon).

| Endpoint | Rôle |
|---|---|
| `POST /api/auth/login` | public |
| `POST /api/auth/logout`, `GET /api/auth/me` | Auth |
| `POST /api/projects` (multipart : nom, ville, architecte, fichier) | CP |
| `GET /api/projects`, `GET /api/projects/{id}` | Auth (filtré) |
| `PATCH /api/projects/{id}` (avant validation) | CP |
| `POST /api/projects/{id}/analyse` | CP |
| `POST /api/projects/{id}/calepinage` | CP |
| `GET /api/projects/{id}/calepinage`, `GET /api/projects/{id}/bom` | Auth (filtré) |
| `POST /api/projects/{id}/validation` | CP |
| `POST /api/projects/{id}/production` | **OP uniquement** |
| `GET /api/projects/{id}/production`, `GET /api/production`, `GET /api/production/{id}` | Auth |
| `GET /api/moulds`, `GET /api/moulds/{id}` | Auth |
| `POST /api/moulds`, `PUT /api/moulds/{id}`, `PATCH /api/moulds/{id}/disponibilite`, `DELETE /api/moulds/{id}` | CP |
| `GET /api/audit` | CP |
| `GET /api/health` | public |

Pages : `/connexion`, `/`, `/projets/nouveau` (CP), `/projets/{id}`, `/moules`, `/production`, `/journal` (CP).

## Migrations

Alembic est le **seul** moyen de faire évoluer le schéma (`create_all()` n'est jamais utilisé).
`0001` schéma initial · `0002` catégorie des moules + bibliothèque initiale (insérée une fois) ·
`0003` message d'alarme des ordres. Mode batch activé (SQLite). Un test vérifie qu'il n'y a aucune
dérive entre modèles et migrations. SQLite : clés étrangères activées, mode WAL, `busy_timeout`.

## Stockage

`data/brikia.db` (base) · `data/uploads/<projet>/<uuid>.<ext>` (plans) · `data/backups/` ·
`data/logs/`. Voir [sauvegarde.md](sauvegarde.md).

## Stratégie de tests

`pytest`, base SQLite temporaire migrée par Alembic, aucun accès réseau. Couvre : authentification,
RBAC (chaque endpoint refusé au mauvais rôle), matrice complète de la machine d'états (36 paires),
projets et fichiers, analyse déterministe, moteur de calepinage (valeurs calculées à la main),
moules, validation, production (double lancement, lancement concurrent par threads, panne de ligne,
reprise après redémarrage), ActionLog, seed, pages et absence de ressource externe.

## Risques et limites connus

- **Un seul processus** : SQLite n'a qu'un écrivain et le blocage des connexions est en mémoire ;
  `serve` lance donc un seul worker.
- **Écritures concurrentes rares** : deux recalculs de calepinage simultanés peuvent produire une
  erreur « base verrouillée » (le lancement de production, lui, est protégé et testé).
- **Progression de production** : calculée par le simulateur en continu, mais enregistrée en base
  à la prochaine consultation (pas de tâche de fond).
- **Ordre en `erreur`** : le projet reste `en_production` ; aucune reprise n'est prévue en phase 1.
- **Lot orphelin** : l'ordre est envoyé à la ligne avant le commit en base (pour tout annuler si la
  ligne refuse). Sans effet avec le simulateur ; la passerelle réelle devra prévoir une annulation.
- **Pas d'écran d'administration des comptes** : création par CLI (`create-user`), pas de changement
  de mot de passe dans l'interface.
- **Contenu des plans non lu** (phase 2) : seule l'extension est contrôlée, pas la signature du fichier.
